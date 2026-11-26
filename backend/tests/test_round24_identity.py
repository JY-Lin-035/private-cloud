"""Round 24 (PR①): rejection events must name the account that triggered them.

Attribution rules under test:
  * protected routes  -> the session identity SessionMiddleware verified
  * public routes     -> only what Throttle independently verified (observed),
                         which never authorises and never renews
  * anything else     -> 本請求未驗證帳號 (never a guess from ipActors/body)

Client-visible behaviour stays a generic 429.
"""
import asyncio
import json

import pytest
from fastapi import Depends, FastAPI, Request
from starlette.testclient import TestClient

from app.api.dependencies import get_redis
from app.api.rate_limit import rate_limit
from app.middleware.session_middleware import SessionMiddleware
from app.middleware.throttle import ThrottleMiddleware
from app.services import security_engine as sec
from app.utils.session_auth import (has_session_cookie, parse_session_cookie,
                                    resolve_session_identity)
from app.utils.security_log import write_event

UNVERIFIED = sec.UNVERIFIED_ACTOR
# The autouse conftest isolation swaps these out per test; capture the real
# implementations at import time so unit tests can exercise them.
REAL = {name: getattr(sec, name) for name in
        ("record_event", "flood_exceeded", "should_log_reject", "match_rules", "match_rules_detail")}


class _FakeRedis:
    """Enough Redis for session verification, counters and scoring."""

    def __init__(self, mapping=None, count=99, ttl=60):
        self.mapping = dict(mapping or {})
        self.count = count
        self.ttl = ttl
        self.touched: list[str] = []

    def get(self, key):
        return self.mapping.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.mapping:
            return None
        self.mapping[key] = value
        return True

    def setex(self, key, seconds, value):
        self.mapping[key] = value
        return True

    def incr(self, key, amount=1):
        self.mapping[key] = int(self.mapping.get(key) or 0) + amount
        return self.mapping[key]

    def expire(self, key, seconds):
        self.touched.append(f"expire:{key}:{seconds}")
        return True

    def delete(self, *keys):
        for k in keys:
            self.mapping.pop(k, None)
        return True

    def ttl_seconds(self, key):
        return self.ttl

    def pipeline(self):
        outer = self

        class _P:
            def incr(self, key):
                return self

            def incrby(self, key, amount):
                outer.incr(key, amount)
                return self

            def expire(self, key, seconds):
                outer.expire(key, seconds)
                return self

            def ttl(self, key):
                return self

            def execute(self):
                return [outer.count, outer.ttl]

        return _P()


# ------------------------------------------------------------------ unit: identity

def test_resolve_session_identity_requires_verified_cookie():
    uid = 7
    r = _FakeRedis({
        f"session:{uid}": f"{uid}|abc",
        f"session_data:{uid}": json.dumps({"user_id": uid, "username": "alice",
                                           "email": "a@x.com", "identity": "user"}),
    })
    assert resolve_session_identity(r, f"session={uid}|abc") == {"user_id": uid, "username": "alice"}


def test_resolve_session_identity_forged_prefix_is_anonymous():
    uid = 7
    r = _FakeRedis({f"session:{uid}": f"{uid}|abc",
                    f"session_data:{uid}": json.dumps({"user_id": uid, "username": "alice"})})
    # attacker keeps a valid *other* account's id in the prefix but a junk token
    assert resolve_session_identity(r, "session=7|nope") is None


def test_resolve_session_identity_rejects_duplicate_cookies():
    uid = 7
    r = _FakeRedis({f"session:{uid}": f"{uid}|abc",
                    f"session_data:{uid}": json.dumps({"user_id": uid, "username": "alice"})})
    assert resolve_session_identity(r, f"session={uid}|abc; session={uid}|abc") is None


def test_resolve_session_identity_rejects_inconsistent_account_blob():
    # session:8 matches the cookie, but the stored account blob is for user 9
    r = _FakeRedis({"session:8": "8|abc", "session_data:8": json.dumps({"user_id": 9, "username": "bob"})})
    assert resolve_session_identity(r, "session=8|abc") is None


def test_resolve_session_identity_without_username_falls_back_to_id():
    uid = 4
    r = _FakeRedis({f"session:{uid}": f"{uid}|t",
                    f"session_data:{uid}": json.dumps({"user_id": uid})})
    assert resolve_session_identity(r, f"session={uid}|t") == {"user_id": uid, "username": None}


def test_shared_cookie_marker_used_by_parser_and_guard():
    assert has_session_cookie("session = 1|abc") and parse_session_cookie("session = 1|abc") == "1|abc"
    assert not has_session_cookie("a=1")
    assert has_session_cookie("session=1|a; session=2|b")
    assert parse_session_cookie("session=1|a; session=2|b") is None


# ------------------------------------------------------------------ integration

@pytest.fixture
def fake_redis():
    return _FakeRedis(count=99, ttl=60)


def _build_app(redis: _FakeRedis):
    app = FastAPI()

    @app.post("/api/accounts/login", dependencies=[Depends(rate_limit(5, 30))])
    async def login():
        return {"ok": True}

    @app.post("/api/files/tus", dependencies=[Depends(rate_limit(30, 300))])
    async def tus_create():
        return {"ok": True}

    app.add_middleware(SessionMiddleware, redis_client=redis)
    app.add_middleware(ThrottleMiddleware)
    app.dependency_overrides[get_redis] = lambda: redis
    return app


@pytest.fixture
def captured_events(fake_redis, monkeypatch):
    """Intercept every audit event while Throttle/Session see `fake_redis`."""
    events = []

    def _capture(kind, ip, actor=None, target=None, detail="",
                 actor_display=None, extra=None, score=True):
        events.append({"kind": kind, "actor": actor, "target": target,
                       "detail": detail, "actor_display": actor_display,
                       "extra": extra, "score": score})

    monkeypatch.setattr(sec, "record_event", _capture)
    monkeypatch.setattr(sec, "flood_exceeded", lambda *a, **k: False)
    monkeypatch.setattr(sec, "match_rules_detail", lambda *a, **k: (False, 0, None, None, []))
    monkeypatch.setattr(sec, "track_actor", lambda *a, **k: None)
    monkeypatch.setattr(sec, "count_upload", lambda *a, **k: None)
    monkeypatch.setattr(sec, "count_download", lambda *a, **k: None)
    monkeypatch.setattr(sec, "_client", lambda: fake_redis)
    return events


def _client(app):
    return TestClient(app, base_url="https://app.example")


def _cf(headers):
    return {"cf-connecting-ip": "203.0.113.9", **headers}


def _session_blob(uid, username=None):
    data = {"user_id": uid, "identity": "user", "email": f"{uid}@x.com"}
    if username:
        data["username"] = username
    return json.dumps(data)


def test_public_route_names_observed_verified_account(captured_events, fake_redis):
    uid = 7
    fake_redis.mapping.update({
        f"session:{uid}": f"{uid}|abc",
        f"session_data:{uid}": _session_blob(uid, "alice"),
    })
    resp = _client(_build_app(fake_redis)).post(
        "/api/accounts/login", headers=_cf({"cookie": f"session={uid}|abc"}))
    assert resp.status_code == 429
    assert resp.json()["detail"] == "請求過多，請稍後再試"  # generic contract kept

    ev = captured_events[-1]
    assert ev["actor_display"] == "alice"
    assert ev["actor"] is None          # observed != sanction-eligible
    assert ev["target"] == "/api/accounts/login"
    assert ev["extra"]["身分來源"] == "observed_session"
    assert ev["extra"]["拒絕來源"] == "端點限流"
    assert ev["extra"]["門檻"] == "5/30s"
    assert ev["extra"]["HTTP方法"] == "POST"
    # observation must not slide the session window
    assert not [t for t in fake_redis.touched if t.startswith(f"expire:session:{uid}:")]


def test_public_route_is_not_authorized_by_observed_identity(captured_events, fake_redis):
    """`checkSession`-style public routes keep their own contract: Throttle's
    observation must not leak into request.state.user."""
    uid = 7
    fake_redis.mapping.update({
        f"session:{uid}": f"{uid}|abc",
        f"session_data:{uid}": _session_blob(uid, "alice"),
    })
    seen = {}

    app = FastAPI()

    @app.get("/api/share/status", dependencies=[Depends(rate_limit(1, 30))])
    async def status(request: Request):
        seen["user"] = getattr(request.state, "user", "absent")
        return {"ok": True}

    app.add_middleware(SessionMiddleware, redis_client=fake_redis)
    app.add_middleware(ThrottleMiddleware)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    fake_redis.count = 1
    resp = _client(app).get("/api/share/status", headers=_cf({"cookie": f"session={uid}|abc"}))
    assert resp.status_code == 200
    assert seen["user"] == "absent"


def test_public_route_without_session_is_marked_unverified(captured_events, fake_redis):
    resp = _client(_build_app(fake_redis)).post("/api/accounts/login", headers=_cf({}))
    assert resp.status_code == 429
    ev = captured_events[-1]
    assert ev["actor_display"] == UNVERIFIED
    assert ev["actor"] is None
    assert ev["extra"]["身分來源"] == "none"


def test_expired_session_is_not_attributed(captured_events, fake_redis):
    # nothing in Redis: the cookie claims an id, verification fails
    resp = _client(_build_app(fake_redis)).post(
        "/api/accounts/login", headers=_cf({"cookie": "session=7|gone"}))
    assert resp.status_code == 429
    assert captured_events[-1]["actor_display"] == UNVERIFIED


def test_duplicate_cookies_are_not_attributed(captured_events, fake_redis):
    uid = 7
    fake_redis.mapping.update({
        f"session:{uid}": f"{uid}|abc",
        f"session_data:{uid}": _session_blob(uid, "alice"),
    })
    resp = _client(_build_app(fake_redis)).post(
        "/api/accounts/login",
        headers=_cf({"cookie": f"session={uid}|abc; session={uid}|abc"}))
    assert resp.status_code == 429
    assert captured_events[-1]["actor_display"] == UNVERIFIED


def test_protected_route_attributes_verified_account(captured_events, fake_redis):
    uid = 11
    fake_redis.mapping.update({
        f"session:{uid}": f"{uid}|tok",
        f"session_data:{uid}": _session_blob(uid, "carol"),
    })
    resp = _client(_build_app(fake_redis)).post(
        "/api/files/tus", headers=_cf({"cookie": f"session={uid}|tok"}))
    assert resp.status_code == 429
    ev = captured_events[-1]
    assert ev["actor_display"] == "carol"
    assert ev["actor"] == "carol"
    assert ev["extra"]["身分來源"] == "verified_session"
    assert ev["target"] == "/api/files/tus"


def test_protected_route_without_display_name_uses_id(captured_events, fake_redis):
    uid = 12
    fake_redis.mapping.update({
        f"session:{uid}": f"{uid}|tok",
        f"session_data:{uid}": _session_blob(uid),
    })
    resp = _client(_build_app(fake_redis)).post(
        "/api/files/tus", headers=_cf({"cookie": f"session={uid}|tok"}))
    assert resp.status_code == 429
    assert captured_events[-1]["actor_display"] == "#12"


def test_two_accounts_same_ip_attribute_separately(captured_events, fake_redis):
    for uid, name in ((21, "u21"), (22, "u22")):
        fake_redis.mapping.update({
            f"session:{uid}": f"{uid}|t{uid}",
            f"session_data:{uid}": _session_blob(uid, name),
        })
    client = _client(_build_app(fake_redis))
    for uid, name in ((21, "u21"), (22, "u22")):
        resp = client.post("/api/accounts/login", headers=_cf({"cookie": f"session={uid}|t{uid}"}))
        assert resp.status_code == 429
        assert captured_events[-1]["actor_display"] == name
    assert [e["actor_display"] for e in captured_events] == ["u21", "u22"]


def test_session_renewal_contract_preserved(captured_events, fake_redis):
    """A real interaction under the limit still succeeds and slides the window."""
    uid = 31
    fake_redis.mapping.update({
        f"session:{uid}": f"{uid}|tok",
        f"session_data:{uid}": _session_blob(uid, "dave"),
    })
    fake_redis.count = 1
    resp = _client(_build_app(fake_redis)).post(
        "/api/files/tus", headers=_cf({"cookie": f"session={uid}|tok"}))
    assert resp.status_code == 200
    assert f"expire:session:{uid}:{sec.settings.TOKEN_EXPIRE_TIME * 60}" in fake_redis.touched


def test_no_cookie_on_protected_route_still_hits_the_limiter(captured_events, fake_redis):
    """Rate limiting is not authorisation: an over-limit anonymous request stays
    a generic 429 and is explicitly marked as unverified."""
    resp = _client(_build_app(fake_redis)).post("/api/files/tus", headers=_cf({}))
    assert resp.status_code == 429
    assert captured_events[-1]["actor_display"] == UNVERIFIED


def test_normal_traffic_emits_no_event(captured_events, fake_redis):
    fake_redis.count = 1
    resp = _client(_build_app(fake_redis)).post("/api/accounts/login", headers=_cf({}))
    assert resp.status_code == 200
    assert captured_events == []


# ------------------------------------------------------------------ audit rendering

def test_write_event_uses_display_actor_column(monkeypatch):
    lines = []
    import app.utils.security_log as slog

    class _L:
        def info(self, msg):
            lines.append(msg)

    monkeypatch.setattr(slog, "get_security_logger", lambda: _L())
    write_event("rate_limit", "1.2.3.4", "alice", "/api/files/tus", "限流 30/300s")
    write_event("rate_limit", "1.2.3.4", UNVERIFIED, "/api/files/tus", "限流 30/300s")
    assert lines[0].split(" | ")[2] == "alice"
    assert lines[1].split(" | ")[2] == UNVERIFIED


def test_alert_body_shares_event_source_and_identity(monkeypatch):
    sent = {}
    monkeypatch.setattr(sec, "_send_alert", lambda subject, body: sent.update(subject=subject, body=body))
    sec._alert("rate_limit", "1.2.3.4", None, "/api/files/tus", "限流 30/300s 觸發（第 31 次）",
               actor_display="alice",
               extra={"HTTP方法": "POST", "拒絕來源": "端點限流", "門檻": "30/300s",
                      "規則範圍": "endpoint", "處分": "HTTP 429"})
    assert "觸發帳號: alice" in sent["body"]
    assert "拒絕來源: 端點限流" in sent["body"]
    assert "HTTP方法: POST" in sent["body"]
    assert "alice@x.com" not in sent["body"]
    sec._alert("rate_limit", "1.2.3.4", None, "/api/x", "x")
    assert f"觸發帳號: {UNVERIFIED}" in sent["body"]


def test_record_event_appends_context_to_audit_line(monkeypatch):
    written = []
    monkeypatch.setattr(sec, "record_event", REAL["record_event"])
    monkeypatch.setattr(sec, "write_event", lambda *a: written.append(a))
    monkeypatch.setattr(sec, "_client", lambda: _FakeRedis())
    sec.record_event("rate_limit", "1.2.3.4", None, "/api/files/tus", "限流 30/300s",
                     actor_display="alice", extra={"拒絕來源": "端點限流", "處分": "HTTP 429"})
    kind, ip, actor, target, detail = written[0]
    assert actor == "alice"
    assert "拒絕來源=端點限流" in detail and "處分=HTTP 429" in detail


def test_escalation_keeps_original_route_in_alert(monkeypatch):
    alerts = []
    monkeypatch.setattr(sec, "_send_alert", lambda subject, body: alerts.append(body))
    monkeypatch.setattr(sec, "_ensure_auto_rule", lambda *a, **k: True)
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: None)
    sec._escalate_to_block(_FakeRedis(), "1.2.3.4", None, "rate_limit", 40, "限流 /api/files/tus",
                           target="/api/files/tus", actor_display="alice")
    assert "目標: /api/files/tus" in alerts[0]
    assert "觸發帳號: alice" in alerts[0]


def test_rule_block_event_is_log_only_and_deduplicated(monkeypatch):
    calls = []
    monkeypatch.setattr(sec, "record_event", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(sec, "should_log_reject", lambda *a, **k: True)
    mw = ThrottleMiddleware.__new__(ThrottleMiddleware)
    asyncio.run(mw._record_rule_block("1.2.3.4", "POST", "/api/files/tus", "alice", ["rule#5(full)"]))
    (kind, ip, actor, target, detail), kwargs = calls[0]
    assert kind == "rule_block" and actor is None
    assert kwargs["actor_display"] == "alice"
    assert kwargs["extra"]["規則範圍"] == "rule#5(full)"
    assert kind not in sec.WEIGHTS  # log only, never scored

    calls.clear()
    monkeypatch.setattr(sec, "should_log_reject", lambda *a, **k: False)
    asyncio.run(mw._record_rule_block("1.2.3.4", "POST", "/api/files/tus", "alice", ["rule#5(full)"]))
    assert calls == []


def test_flood_event_names_the_request_account(monkeypatch):
    calls = []
    monkeypatch.setattr(sec, "record_event", lambda *a, **k: calls.append((a, k)))
    r = _FakeRedis()
    monkeypatch.setattr(sec, "_client", lambda: r)
    monkeypatch.setattr(sec, "_incr_ttl", lambda *a, **k: sec.settings.SEC_GLOBAL_HOURLY_LIMIT + 1)
    monkeypatch.setattr(sec, "flood_exceeded", REAL["flood_exceeded"])
    assert sec.flood_exceeded("1.2.3.4", "alice", "/api/files/tus") is True
    (kind, ip, actor, target, detail), kwargs = calls[0]
    assert kind == "flood" and target == "/api/files/tus"
    assert kwargs["actor_display"] == "alice"
    assert kwargs["extra"]["拒絕來源"] == "全站 flood"


def test_should_log_reject_marks_once_per_window(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(sec, "_client", lambda: r)
    monkeypatch.setattr(sec, "should_log_reject", REAL["should_log_reject"])
    assert REAL["should_log_reject"]("rule_block", "1.2.3.4", "/api/files/tus") is True
    assert REAL["should_log_reject"]("rule_block", "1.2.3.4", "/api/files/tus") is False
    assert REAL["should_log_reject"]("rule_block", "1.2.3.4", "/api/files/stream") is True


# ------------------------------------------------- ipActors stay a separate signal

def test_recent_ip_actors_is_correlation_only(monkeypatch):
    import time
    now = int(time.time())
    r = _FakeRedis({
        "ipActors:203.0.113.9": {"7": str(now), "8": str(now - 60)},
        "session_data:7": json.dumps({"user_id": 7, "username": "alice"}),
    })
    monkeypatch.setattr(sec, "_client", lambda: r)
    r.hgetall = lambda key: sec._client().mapping.get(key, {})
    out = sec.recent_ip_actors("203.0.113.9")
    assert [a["user_id"] for a in out] == [7, 8]
    assert out[0]["username"] == "alice" and out[1]["username"] == "#8"  # no blob -> id
    assert out[0]["last_seen"] and "email" not in json.dumps(out)


def test_admin_ipactors_endpoint_masks_and_requires_admin(monkeypatch):
    from unittest.mock import MagicMock
    from app.api.v1 import ipcontrol as api
    monkeypatch.setattr(sec, "recent_ip_actors",
                        lambda ip, limit=20: [{"user_id": 7, "username": "alice", "last_seen": "x"}])
    req = MagicMock()
    from app.constants import Identity
    req.state.user = {"identity": Identity.ADMIN, "id": 1, "username": "boss"}
    resp = asyncio.run(api.admin_ip_actors(req, ip="203.0.113.9"))
    assert resp["ip"] == sec.mask_ip("203.0.113.9")
    assert resp["accounts"][0]["username"] == "alice"
