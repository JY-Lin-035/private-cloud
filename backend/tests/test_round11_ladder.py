"""Round 11: auth-pool routing, strike ladder 1/3/6/12/24/72/permanent,
terminal-rule guards, attested-account disabling."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.ip_control import IpControl
from app.services import security_engine as sec
import app.database as database

RECORD = sec.record_event  # capture before autouse conftest swaps it for a noop


@pytest.fixture
def Session(monkeypatch):
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng)
    monkeypatch.setattr(database, "SessionLocal", S)
    return S


class FakeR:
    def __init__(self, incr_start=1):
        self.n = incr_start - 1
        self.keys = {}
        self.incrcalls = []
        self.deleted = []

    def incr(self, k):
        self.n += 1
        self.incrcalls.append((k, self.n))
        return self.n

    def expire(self, *a, **k): pass
    def delete(self, *a, **k): self.deleted.extend(a)
    def setex(self, k, t, v): self.keys[k] = v
    def get(self, k): return self.keys.get(k)


@pytest.fixture
def quiet(monkeypatch):
    alerts = []
    monkeypatch.setattr(sec, "_alert", lambda *a, **k: alerts.append(a))
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: None)
    return alerts


def _rule_for(Session, ip):
    db = Session()
    try:
        return db.query(IpControl).filter(IpControl.ip == ip, IpControl.auto.is_(True)).first()
    finally:
        db.close()


class TestStrikeLadder:
    def test_ladder_hours(self, Session, quiet):
        r = FakeR()
        hours_seq = []
        for i in range(1, 7):
            sec._escalate_to_block(r, "203.0.113.10", None, "rate_limit", 20, "d")
            rule = _rule_for(Session, "203.0.113.10")
            hours_seq.append(round((rule.expires_at - datetime.utcnow()).total_seconds() / 3600))
        assert hours_seq == [1, 3, 6, 12, 24, 72]

    def test_seventh_strike_is_permanent(self, Session, quiet):
        r = FakeR()
        for _ in range(7):
            sec._escalate_to_block(r, "203.0.113.11", None, "rate_limit", 20, "d")
        rule = _rule_for(Session, "203.0.113.11")
        assert rule.expires_at is None
        assert any("永久" in a[-1] for a in quiet)

    def test_permanent_is_terminal_no_realert(self, Session, quiet):
        r = FakeR()
        for _ in range(7):
            sec._escalate_to_block(r, "203.0.113.12", None, "rate_limit", 20, "d")
        n_alerts = len(quiet)
        sec._escalate_to_block(r, "203.0.113.12", None, "rate_limit", 20, "d")  # 8th
        assert len(quiet) == n_alerts  # duplicate alert suppressed
        assert _rule_for(Session, "203.0.113.12").expires_at is None

    def test_cannot_downgrade_permanent_to_slow(self, Session, quiet):
        r = FakeR()
        for _ in range(7):
            sec._escalate_to_block(r, "203.0.113.13", None, "rate_limit", 20, "d")
        changed = sec._ensure_auto_rule(r, {"ip": "203.0.113.13"}, "slow", "transfer", "both", 1)
        assert changed is False
        rule = _rule_for(Session, "203.0.113.13")
        assert rule.action == "block" and rule.expires_at is None

    def test_cannot_downgrade_timed_block_to_slow(self, Session, quiet):
        r = FakeR()
        sec._escalate_to_block(r, "203.0.113.14", None, "rate_limit", 20, "d")  # strike1 -> block 1h
        changed = sec._ensure_auto_rule(r, {"ip": "203.0.113.14"}, "slow", "transfer", "both", 1)
        assert changed is False
        assert _rule_for(Session, "203.0.113.14").action == "block"


    def test_escalation_resets_scores_once_per_episode(self, Session, quiet):
        r = FakeR()
        sec._escalate_to_block(r, "203.0.113.30", None, "login_fail", 18, "d")
        assert "secScoreA:203.0.113.30" in r.deleted and "secScore:203.0.113.30" in r.deleted


class TestPoolRouting:
    @pytest.fixture
    def spy(self, monkeypatch):
        calls = []
        def fake_incr(r, key, w, ttl):
            calls.append(key)
            return 1
        monkeypatch.setattr(sec, "_incr_ttl", fake_incr)
        monkeypatch.setattr(sec, "_escalate_to_block", lambda *a, **k: None)
        monkeypatch.setattr(sec, "_client", lambda: MagicMock())
        monkeypatch.setattr(sec, "_ensure_auto_rule", lambda *a, **k: False)
        monkeypatch.setattr(sec, "_alert", lambda *a, **k: None)
        monkeypatch.setattr(sec, "write_event", lambda *a, **k: None)
        return calls

    def test_login_fail_goes_auth_pool(self, spy):
        RECORD("login_fail", "1.2.3.4", actor="x", detail="no such user")
        assert spy[-1].startswith("secScoreA:")

    def test_rate_limit_on_auth_endpoint_goes_auth_pool(self, spy):
        RECORD("rate_limit", "1.2.3.4", target="/api/accounts/login", detail="5/30")
        assert spy[-1].startswith("secScoreA:")

    def test_rate_limit_on_transfer_endpoint_goes_general_pool(self, spy):
        RECORD("rate_limit", "1.2.3.4", target="/api/files/uploadFile", detail="30/300")
        assert spy[-1].startswith("secScore:")

    def test_pw_fail_share_stays_general(self, spy):
        RECORD("pw_fail", "1.2.3.4", target="abcd1234", detail="bad share pw")
        assert spy[-1].startswith("secScore:")


class TestTerminalDisable:
    def test_admin_probe_attributable_account_disabled_at_cap(self, Session, quiet, monkeypatch):
        db = Session()
        v = Account(name="sneaky", password="p", email="s@x.io", identity=Identity.USER, enable=True)
        v.id = 42
        db.add(v); db.commit(); db.close()
        monkeypatch.setattr(sec, "_client", lambda: FakeR())
        monkeypatch.setattr(sec, "write_event", lambda *a, **k: None)
        r = FakeR()
        for _ in range(7):
            sec._escalate_to_block(r, "203.0.113.20", "sneaky", "admin_probe", 21, "probe")
        db = Session()
        assert db.query(Account).filter(Account.name == "sneaky").first().enable is False
        db.close()
        assert any("停用帳號 sneaky" in a[-1] for a in quiet)

    def test_login_fail_never_disaccounts_victim(self, Session, quiet, monkeypatch):
        db = Session()
        v = Account(name="realuser", password="p", email="r@x.io", identity=Identity.USER, enable=True)
        v.id = 43
        db.add(v); db.commit(); db.close()
        monkeypatch.setattr(sec, "_client", lambda: FakeR())
        monkeypatch.setattr(sec, "write_event", lambda *a, **k: None)
        r = FakeR()
        for _ in range(9):
            sec._escalate_to_block(r, "203.0.113.21", "realuser", "login_fail", 21, "guessing")
        db = Session()
        assert db.query(Account).filter(Account.name == "realuser").first().enable is True
        db.close()
