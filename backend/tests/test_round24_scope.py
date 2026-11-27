"""Round 24 (extra): rule scope corrections — ip_token rules are per LINK,
auto escalations never overwrite each other, and manual rules are not rewritten.

These are behaviour fixes, deliberately kept out of the threshold-migration PR.
"""
import asyncio
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.ip_control import IpControl
from app.services import security_engine as sec


@pytest.fixture
def db(monkeypatch):
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    factory = sessionmaker(bind=eng)
    monkeypatch.setattr("app.database.SessionLocal", factory)
    session = factory()
    yield session
    session.close()


def _rule(**kw):
    base = dict(subject_type="ip", ip="9.9.9.9", token=None, user_id=None, action="block",
                scope="transfer", direction="both", delay_ms=0, upload_kbps=None,
                download_kbps=None, auto=False)
    base.update(kw)
    return base


# ------------------------------------------------------- ip_token is per link

def test_ip_token_rule_only_affects_its_own_link(monkeypatch):
    monkeypatch.setattr(sec, "_active_rules", lambda: [
        _rule(subject_type="ip_token", token="linkAAA", direction="down", scope="transfer"),
    ])
    blocked, *_ = sec.match_rules("9.9.9.9", None, False, True, True, token="linkAAA")
    assert blocked is True
    # the same address downloading a DIFFERENT shared link must be untouched
    other, *_ = sec.match_rules("9.9.9.9", None, False, True, True, token="linkBBB")
    assert other is False


def test_unknown_link_fails_closed(monkeypatch):
    """When the middleware cannot tell which link is meant, the rule still
    applies: narrowing the scope must not silently weaken protection."""
    monkeypatch.setattr(sec, "_active_rules", lambda: [
        _rule(subject_type="ip_token", token="linkAAA", direction="down", scope="transfer"),
    ])
    assert sec.match_rules("9.9.9.9", None, False, True, True, token=None)[0] is True
    # and a non-share path is still unaffected
    assert sec.match_rules("9.9.9.9", None, False, True, False, token=None)[0] is False


def test_ip_token_rules_do_not_leak_across_directions(monkeypatch):
    monkeypatch.setattr(sec, "_active_rules", lambda: [
        _rule(subject_type="ip_token", token="linkAAA", action="block", direction="up",
              scope="transfer"),
    ])
    up = sec.match_rules("9.9.9.9", None, True, False, True, token="linkAAA")
    down = sec.match_rules("9.9.9.9", None, False, True, True, token="linkAAA")
    assert up[0] is True and down[0] is False


# ------------------------------------------------- auto rules: no clobbering

def test_auto_rules_are_separate_per_direction(db, monkeypatch):
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: None)
    r = object()
    assert sec._ensure_auto_rule(r, {"ip": "7.7.7.7"}, "slow", "transfer", "up", 1) is True
    assert sec._ensure_auto_rule(r, {"ip": "7.7.7.7"}, "slow", "transfer", "down", 1) is True
    rows = db.query(IpControl).all()
    assert len(rows) == 2
    assert {row.direction for row in rows} == {"up", "down"}
    # a second upload escalation merges into the up row, never the down one
    assert sec._ensure_auto_rule(r, {"ip": "7.7.7.7"}, "block", "transfer", "up", 1) is True
    db.expire_all()
    up = db.query(IpControl).filter_by(direction="up").one()
    down = db.query(IpControl).filter_by(direction="down").one()
    assert up.action == "block" and down.action == "slow"


def test_auto_rule_does_not_rewrite_manual_rule(db, monkeypatch):
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: None)
    db.add(IpControl(subject_type="ip", ip="8.8.8.8", action="slow", scope="transfer",
                     direction="both", delay_ms=1234, upload_kbps=99, download_kbps=99,
                     reason="manual", auto=False, expires_at=datetime.utcnow() + timedelta(hours=6)))
    db.commit()
    changed = sec._ensure_auto_rule(object(), {"ip": "8.8.8.8"}, "block", "transfer", "both", 1)
    db.expire_all()
    rows = db.query(IpControl).filter_by(ip="8.8.8.8").all()
    assert len(rows) == 2, "auto escalation must add its own row, not edit the manual one"
    manual = [r for r in rows if not r.auto][0]
    assert manual.delay_ms == 1234 and manual.action == "slow"
    assert changed is True


def test_ladder_upgrades_one_row_in_place(db, monkeypatch):
    """Scope is NOT part of the merge key: transfer/slow -> full/block must
    upgrade the same row, and a terminal block stays terminal for every stage."""
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: None)
    sec._ensure_auto_rule(object(), {"ip": "9.9.9.10"}, "slow", "transfer", "both", 1)
    sec._ensure_auto_rule(object(), {"ip": "9.9.9.10"}, "block", "full", "both", 6)
    db.expire_all()
    assert db.query(IpControl).count() == 1
    row = db.query(IpControl).one()
    assert (row.action, row.scope) == ("block", "full")
    # a later slow escalation (any scope) must not downgrade the timed block
    assert sec._ensure_auto_rule(object(), {"ip": "9.9.9.10"}, "slow", "transfer", "both", 1) is False


def test_auto_rule_merges_into_same_auto_row(db, monkeypatch):
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: None)
    assert sec._ensure_auto_rule(object(), {"user_id": 3, "username": "u3"}, "slow", "transfer", "up", 1)
    db.expire_all()
    first = db.query(IpControl).one()
    first_id = first.id
    assert sec._ensure_auto_rule(object(), {"user_id": 3, "username": "u3"}, "block", "transfer", "up", 3)
    db.expire_all()
    assert db.query(IpControl).count() == 1
    row = db.query(IpControl).one()
    assert row.id == first_id and row.action == "block"


# ------------------------------------------------ middleware link extraction

class _FakeSec:
    pass


def _scope(path, method="POST", query=b"", body=b"", ctype="application/json", ip="9.9.9.9"):
    msgs = [{"type": "http.request", "body": body, "more_body": False}]
    idx = {"i": 0}

    async def receive():
        if idx["i"] < len(msgs):
            m = msgs[idx["i"]]
            idx["i"] += 1
            return m
        return {"type": "http.disconnect"}

    headers = [(b"cf-connecting-ip", ip.encode()), (b"content-type", ctype.encode()),
               (b"content-length", str(len(body)).encode())]
    return ({"type": "http", "path": path, "method": method, "query_string": query,
             "headers": headers, "client": ("10.0.0.1", 1)}, receive)


def _run(mw, scope, receive):
    out = {}

    async def send(message):
        out.setdefault("messages", []).append(message)

    async def app(s, r, snd):
        body = b""
        while True:
            m = await r()
            if m["type"] != "http.request":
                break
            body += m.get("body", b"")
            if not m.get("more_body", False):
                break
        out["body"] = body
        out["seen_token"] = s.get("state", {}).get("share_token")
        await snd({"type": "http.response.start", "status": 200, "headers": []})
        await snd({"type": "http.response.body", "body": b"ok"})

    mw.app = app
    asyncio.run(mw(scope, receive, send))
    return out


@pytest.fixture
def mw(monkeypatch):
    from app.middleware.throttle import ThrottleMiddleware
    monkeypatch.setattr(sec, "flood_exceeded", lambda *a, **k: False)
    monkeypatch.setattr(sec, "match_rules_detail", lambda *a, **k: (False, 0, None, None, []))
    monkeypatch.setattr(sec, "_client", lambda: _FakeSec())
    from app.services import security_policy
    from app.utils import session_auth
    monkeypatch.setattr(session_auth, "resolve_session_identity", lambda *a, **k: None)
    monkeypatch.setattr(security_policy, "current",
                        lambda force=False: security_policy.Snapshot(0, {}))
    return ThrottleMiddleware(app=None)


def test_link_is_read_from_query(mw, monkeypatch):
    calls = []
    monkeypatch.setattr(sec, "match_rules_detail",
                        lambda *a, **k: calls.append(a) or (False, 0, None, None, []))
    out = _run(mw, *_scope("/api/share/downloadFile", method="GET", body=b"",
                           query=b"link=linkAAA&ticket=t"))
    assert out["messages"][0]["status"] == 200
    assert calls[0][-1] == "linkAAA"
    assert out["seen_token"] == "linkAAA"


def test_link_is_read_from_json_body_and_body_is_replayed(mw, monkeypatch):
    calls = []
    monkeypatch.setattr(sec, "match_rules_detail",
                        lambda *a, **k: calls.append(a) or (False, 0, None, None, []))
    body = json.dumps({"link": "linkBBB", "password": "x"}).encode()
    out = _run(mw, *_scope("/api/share/verifyPassword", body=body))
    assert out["body"] == body, "the application must receive the body untouched"
    assert calls[0][-1] == "linkBBB"
    assert out["seen_token"] == "linkBBB"


def test_chunked_json_body_is_reassembled_and_replayed(mw, monkeypatch):
    seen = []
    monkeypatch.setattr(sec, "match_rules_detail", lambda *a, **k: (False, 0, None, None, []))
    payload = json.dumps({"link": "linkCCC", "paths": ["a" * 40 for _ in range(30)]}).encode()
    half = len(payload) // 2

    msgs = [{"type": "http.request", "body": payload[:half], "more_body": True},
            {"type": "http.request", "body": payload[half:], "more_body": False}]
    idx = {"i": 0}

    async def receive():
        if idx["i"] < len(msgs):
            m = msgs[idx["i"]]
            idx["i"] += 1
            return m
        return {"type": "http.disconnect"}

    scope = {"type": "http", "path": "/api/share/downloadItems", "method": "POST",
             "query_string": b"", "client": ("10.0.0.1", 1),
             "headers": [(b"cf-connecting-ip", b"9.9.9.9"),
                         (b"content-type", b"application/json"),
                         (b"content-length", str(len(payload)).encode())]}

    async def app(s, r, snd):
        body = b""
        while True:
            m = await r()
            if m["type"] != "http.request":
                break
            body += m.get("body", b"")
            if not m.get("more_body", False):
                break
        seen.append(body)
        await snd({"type": "http.response.start", "status": 200, "headers": []})
        await snd({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        pass

    mw.app = app
    asyncio.run(mw(scope, receive, send))
    assert seen == [payload]


def test_oversized_body_is_not_sniffed_and_still_forwarded(mw, monkeypatch):
    calls = []
    monkeypatch.setattr(sec, "match_rules_detail",
                        lambda *a, **k: calls.append(a) or (False, 0, None, None, []))
    big = b'{"link":"linkDDD","junk":"' + b"x" * (300 * 1024) + b'"}'
    scope, receive = _scope("/api/share/downloadItems", body=big)
    out = _run(mw, scope, receive)
    assert out["body"] == big                       # nothing lost
    assert calls[0][-1] is None                     # unknown link -> fail closed
