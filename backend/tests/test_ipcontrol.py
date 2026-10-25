"""Tests for ip_control matching/merge + API validation (R15)."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.ip_control import IpControl
from app.api.v1 import ipcontrol as api
from app.services import security_engine as sec


@pytest.fixture
def db():
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    a = Account(name="target", password="p", email="t@x.io", identity=Identity.USER)
    a.id = 5
    adm = Account(name="boss", password="p", email="b@x.io", identity=Identity.ADMIN)
    adm.id = 1
    s.add_all([a, adm]); s.commit()
    yield s
    s.close()


def admin_req():
    r = MagicMock()
    r.state.user = {"identity": Identity.ADMIN, "id": 1, "username": "boss"}
    return r


def user_req():
    r = MagicMock()
    r.state.user = {"identity": Identity.USER, "id": 5, "username": "target"}
    r.url.path = "/api/ipcontrol/admin"
    return r


class TestApi:
    def test_non_admin_forbidden(self, db):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_create(
                payload=api.ControlCreate(subject_type="user", username="target"),
                request=user_req(), db=db))
        assert exc.value.status_code == 403

    def test_create_user_rule_validates_subject(self, db):
        with pytest.raises(HTTPException):
            asyncio.run(api.admin_create(
                payload=api.ControlCreate(subject_type="user", username="ghost"),
                request=admin_req(), db=db))

    def test_create_ip_masks_everywhere(self, db):
        rid = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="203.0.113.7", reason="r"),
            request=admin_req(), db=db))["id"]
        d = asyncio.run(api.admin_list(request=admin_req(), db=db))
        mine = next(x for x in d["rules"] if x["id"] == rid)
        assert mine["ip_masked"] == "203.xx.xx.7"
        assert "203.0.113.7" not in str(d)

    def test_duplicate_rejected(self, db):
        asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="198.51.100.1"),
            request=admin_req(), db=db))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_create(
                payload=api.ControlCreate(subject_type="ip", ip="198.51.100.1"),
                request=admin_req(), db=db))
        assert exc.value.status_code == 400

    def test_escalate_and_release(self, db):
        rid = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="198.51.100.2"),
            request=admin_req(), db=db))["id"]
        asyncio.run(api.admin_update(rid, api.ControlUpdate(action="block", scope="full"),
                                      request=admin_req(), db=db))
        rule = db.get(IpControl, rid)
        assert rule.action == "block" and rule.scope == "full"
        asyncio.run(api.admin_delete(rid, request=admin_req(), db=db))
        assert db.get(IpControl, rid) is None

    def test_cannot_suspend_admin(self, db):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_suspend_account(
                payload=api.SuspendRequest(username="boss"), request=admin_req(), db=db))
        assert exc.value.status_code == 403

    def test_suspend_user(self, db):
        asyncio.run(api.admin_suspend_account(
            payload=api.SuspendRequest(username="target"), request=admin_req(), db=db))
        assert db.query(Account).filter(Account.name == "target").first().enable is False


class TestMatchRules:
    def _rule(self, **kw):
        base = dict(subject_type="ip", ip="9.9.9.9", token=None, user_id=None, action="slow",
                    scope="transfer", direction="both", delay_ms=2000, upload_kbps=256,
                    download_kbps=512, auto=True)
        base.update(kw)
        return base

    def test_direction_isolation(self, monkeypatch):
        monkeypatch.setattr(sec, "_active_rules", lambda: [self._rule(direction="up")])
        b, d, uk, dk = sec.match_rules("9.9.9.9", None, is_upload=True, is_download=False, is_share=False)
        assert (b, d, uk, dk) == (False, 2000, 256, None)
        b2, d2, uk2, dk2 = sec.match_rules("9.9.9.9", None, is_upload=False, is_download=True, is_share=False)
        assert d2 == 0 and dk2 is None  # 下載方向不該被 up-only 規則擋

    def test_share_scope_for_ip_token(self, monkeypatch):
        rules = [dict(self._rule(subject_type="ip_token"), direction="down", upload_kbps=None, download_kbps=64)]
        monkeypatch.setattr(sec, "_active_rules", lambda: rules)
        b, d, uk, dk = sec.match_rules("9.9.9.9", None, False, True, True)
        assert b is False and dk == 64
        b2, d2, _, dk2 = sec.match_rules("9.9.9.9", None, False, True, False)
        assert dk2 is None  # 非 share 路徑不受 ip_token 規則影響

    def test_manual_overrides_merge(self, monkeypatch):
        monkeypatch.setattr(sec, "_active_rules", lambda: [
            self._rule(auto=True, download_kbps=512),
            dict(self._rule(auto=False, action="block", user_id=None)),
        ])
        b, d, uk, dk = sec.match_rules("9.9.9.9", None, True, True, False)
        assert b is True

    def test_mask_ip(self):
        assert sec.mask_ip("122.116.64.99") == "122.xx.xx.99"
        assert "xx" in sec.mask_ip("fd7a:115c:a1e0::1234")


class TestAlertPrivacy:
    def test_alert_body_has_no_storage_hints(self, monkeypatch):
        sent = {}
        def cap(subject, body):
            sent['subject'] = subject; sent['body'] = body
        monkeypatch.setattr(sec, "_send_alert", cap)
        # bypass 10-min cooldown
        from unittest.mock import patch
        real_client = sec._client
        fake = MagicMock()
        fake.get.return_value = None
        fake.incr.return_value = 0
        fake.delete.return_value = 1
        fake.setex.return_value = True
        sec._redis = fake
        try:
            sec._alert("pw_lock", "1.2.3.4", "someuser", "tgt", "detail", "全站 429")
        finally:
            sec._redis = None
        body = sent.get('body', '')
        for banned in ('security.log', 'log', '伺服器', 'server', 'IP Management'):
            assert banned not in body, f'alert body 不应包含 {banned}'
        assert '1.2.3.4' not in body  # full IP must never appear
        assert '1.xx.xx.4' in sent['subject'] or '1.2.3.4' not in sent['subject']

class TestToggleEnableKick:
    def test_disable_kills_session(self, db):
        import asyncio as _a
        from app.api.v1 import accounts as acc
        t = db.query(Account).filter(Account.name == "target").first()
        t.enable = True
        db.commit()
        req = MagicMock()
        req.state.user = {"identity": Identity.ADMIN, "id": 1}
        req.state.user_id = 1
        req.client.host = "9.9.9.9"
        redis = MagicMock()
        r = _a.run(acc.admin_toggle_enable(request=req, user_id=5, db=db, redis_client=redis))
        assert r["enabled"] is False
        redis.delete.assert_any_call("session:5")
        redis.delete.assert_any_call("session_data:5")


class TestDirectionBandwidthHygiene:
    def test_create_down_drops_upload_kbps(self, db):
        rid = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="198.51.100.5",
                                      direction="down", upload_kbps=999, download_kbps=321),
            request=admin_req(), db=db))["id"]
        rule = db.get(IpControl, rid)
        assert rule.upload_kbps is None and rule.download_kbps == 321

    def test_update_direction_clears_stale_kbps(self, db):
        rid = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="198.51.100.6",
                                      direction="both", upload_kbps=100, download_kbps=200),
            request=admin_req(), db=db))["id"]
        assert db.get(IpControl, rid).download_kbps == 200
        asyncio.run(api.admin_update(rid, api.ControlUpdate(direction="up"), request=admin_req(), db=db))
        rule = db.get(IpControl, rid)
        assert rule.direction == "up" and rule.download_kbps is None and rule.upload_kbps == 100
