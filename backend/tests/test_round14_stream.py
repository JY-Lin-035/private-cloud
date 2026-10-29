"""Round14: independent stream control — precedence, fallback, API validation."""
import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import security_engine as sec
from app.api.v1 import ipcontrol as api
from app.models.base import Base
from tests.test_ipcontrol import admin_req  # reuse helper


@pytest.fixture
def db():
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _rule(**kw):
    base = dict(subject_type="ip", ip="9.9.9.9", token=None, user_id=None, action="slow",
                scope="transfer", direction="down", delay_ms=0, upload_kbps=None,
                download_kbps=None)
    base.update(kw)
    return base


class TestMatchRulesStream:
    def test_stream_rule_wins_and_transfer_down_ignored(self, monkeypatch):
        rules = [
            _rule(scope="stream", download_kbps=300),
            _rule(scope="transfer", direction="down", download_kbps=50),
        ]
        monkeypatch.setattr(sec, "_active_rules", lambda: rules)
        b, d, up, dn = sec.match_rules("9.9.9.9", None, False, True, False, is_stream=True)
        assert (b, dn) == (False, 300)          # stream knob, no double-pacer
        # same subject: plain downloads still governed by transfer rule
        b2, d2, up2, dn2 = sec.match_rules("9.9.9.9", None, False, True, False, is_stream=False)
        assert dn2 == 50

    def test_stream_falls_back_to_transfer_when_no_stream_rule(self, monkeypatch):
        monkeypatch.setattr(sec, "_active_rules",
                            lambda: [_rule(scope="transfer", direction="down", download_kbps=64)])
        b, d, up, dn = sec.match_rules("9.9.9.9", None, False, True, False, is_stream=True)
        assert dn == 64                          # escalation ladder still bites streams

    def test_stream_block(self, monkeypatch):
        monkeypatch.setattr(sec, "_active_rules",
                            lambda: [_rule(scope="stream", action="block")])
        b, *_ = sec.match_rules("9.9.9.9", None, False, True, False, is_stream=True)
        assert b is True
        b2, *_ = sec.match_rules("9.9.9.9", None, False, True, False, is_stream=False)
        assert b2 is False                       # download unaffected by stream-only block

    def test_upload_unaffected_by_stream_rule(self, monkeypatch):
        monkeypatch.setattr(sec, "_active_rules",
                            lambda: [_rule(scope="stream", action="block")])
        b, *_ = sec.match_rules("9.9.9.9", None, True, False, False, is_stream=False)
        assert b is False

    def test_full_still_overrides_everything(self, monkeypatch):
        rules = [_rule(scope="stream", download_kbps=999), _rule(scope="full", action="block")]
        monkeypatch.setattr(sec, "_active_rules", lambda: rules)
        b, *_ = sec.match_rules("9.9.9.9", None, False, True, False, is_stream=True)
        assert b is True


class TestIpControlStreamScope:
    def test_create_scope_stream_normalizes_direction(self, db, monkeypatch):
        db = db  # session from conftest? fallback below if fixture missing
        rid = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="203.0.113.88",
                                      action="slow", scope="stream", direction="both",
                                      download_kbps=256),
            request=admin_req(), db=db))["id"]
        row = db.get(api.IpControl, rid)
        assert row.scope == "stream" and row.direction == "down"

    def test_invalid_scope_rejected(self, db):
        with pytest.raises(HTTPException):
            asyncio.run(api.admin_create(
                payload=api.ControlCreate(subject_type="ip", ip="203.0.113.89",
                                          action="slow", scope="bogus"),
                request=admin_req(), db=db))


class TestSubjectScopeUniqueness:
    def test_same_ip_different_scope_allowed(self, db):
        rid1 = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="203.0.113.91", scope="transfer"),
            request=admin_req(), db=db))["id"]
        rid2 = asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="203.0.113.91", scope="stream"),
            request=admin_req(), db=db))["id"]
        assert rid1 != rid2

    def test_same_ip_same_scope_rejected(self, db):
        asyncio.run(api.admin_create(
            payload=api.ControlCreate(subject_type="ip", ip="203.0.113.92", scope="stream"),
            request=admin_req(), db=db))
        with pytest.raises(HTTPException) as ex:
            asyncio.run(api.admin_create(
                payload=api.ControlCreate(subject_type="ip", ip="203.0.113.92", scope="stream"),
                request=admin_req(), db=db))
        assert ex.value.status_code == 400
