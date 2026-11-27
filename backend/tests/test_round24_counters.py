"""Round 24 (PR②): throttling policy must not punish legitimate batches.

Two invariants:
  * every rejected request is still counted and audited, but one window of
    continuous overage costs exactly ONE violation score (workers included)
  * account upload volume is booked at the creation boundary only — a TUS
    session's HEAD/PATCH/cancel must not look like 20 uploads
"""
import asyncio
import json

import pytest
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from app.api.dependencies import get_redis
from app.api.rate_limit import rate_limit
from app.middleware.session_middleware import SessionMiddleware
from app.middleware.throttle import DOWNLOAD_PREFIXES, UPLOAD_PREFIXES, ThrottleMiddleware
from app.services import security_engine as sec
from tests.test_round24_identity import REAL, _FakeRedis, _cf


class _CountingRedis(_FakeRedis):
    """Real SETNX semantics over an in-memory dict (single process)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.counts = {}

    def pipeline(self):
        outer = self

        class _P:
            key = None

            def incr(self_inner, key):
                self_inner.key = key
                return self_inner

            def ttl(self_inner, key):
                return self_inner

            def execute(self_inner):
                outer.counts[self_inner.key] = outer.counts.get(self_inner.key, 0) + 1
                return [outer.counts[self_inner.key], outer.ttl]

            def incrby(self_inner, key, amount):
                outer.counts[key] = outer.counts.get(key, 0) + amount
                return self_inner

            def expire(self_inner, key, seconds):
                return self_inner

        return _P()

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.mapping:
            return None
        self.mapping[key] = value
        return True

    def get(self, key):
        return self.mapping.get(key)


@pytest.fixture
def engine(monkeypatch):
    redis = _CountingRedis(count=0, ttl=300)
    events = []

    def _capture(kind, ip, actor=None, target=None, detail="",
                 actor_display=None, extra=None, score=True):
        events.append({"kind": kind, "target": target, "detail": detail,
                       "actor_display": actor_display, "extra": extra, "score": score})

    monkeypatch.setattr(sec, "record_event", _capture)
    monkeypatch.setattr(sec, "_client", lambda: redis)
    monkeypatch.setattr(sec, "flood_exceeded", lambda *a, **k: False)
    monkeypatch.setattr(sec, "match_rules_detail", lambda *a, **k: (False, 0, None, None, []))
    monkeypatch.setattr(sec, "track_actor", lambda *a, **k: None)
    monkeypatch.setattr(sec, "count_download", lambda *a, **k: None)
    redis.events = events
    return redis


def _app(redis, max_requests=3, window=300):
    app = FastAPI()

    @app.post("/api/files/tus", dependencies=[Depends(rate_limit(max_requests, window))])
    async def tus():
        return {"ok": True}

    app.add_middleware(SessionMiddleware, redis_client=redis)
    app.add_middleware(ThrottleMiddleware)
    app.dependency_overrides[get_redis] = lambda: redis
    return app


def _post(client):
    return client.post("/api/files/tus", headers=_cf({}))


# ------------------------------------------------- endpoint scoring once per window

def test_burst_rejected_every_time_but_scored_once(engine):
    client = TestClient(_app(engine), base_url="https://app.example")
    statuses = [_post(client).status_code for _ in range(6)]
    assert statuses == [200, 200, 200, 429, 429, 429]

    events = [e for e in engine.events if e["kind"] == "rate_limit"]
    assert len(events) == 3                       # every rejection is audited
    assert [e["score"] for e in events] == [True, False, False]
    assert events[0]["extra"]["違規計分"] == "是"
    assert "重複" in events[1]["extra"]["違規計分"]
    # the bucket still counted every single request
    assert engine.counts["rate_limit:203.0.113.9:/api/files/tus"] == 6


def test_marker_is_atomic_and_shared_across_workers(engine):
    """Two 'workers' evaluating the same rejection: exactly one claims the score."""
    claims = [REAL["should_log_reject"]("rate_limit", "1.2.3.4", "/x", 300) for _ in range(5)]
    assert claims == [True, False, False, False, False]


def test_new_window_can_score_again(engine):
    client = TestClient(_app(engine), base_url="https://app.example")
    for _ in range(5):
        _post(client)
    assert sum(1 for e in engine.events if e["score"]) == 1
    engine.mapping.clear()          # window expired -> buckets and marker gone
    engine.counts.clear()
    for _ in range(5):
        _post(client)
    assert sum(1 for e in engine.events if e["score"]) == 2


# ------------------------------------------------- upload volume at creation only

def test_upload_prefixes_are_still_classified_for_pacing():
    assert "/api/files/tus" in UPLOAD_PREFIXES or any("/api/files/tus".startswith(p) for p in UPLOAD_PREFIXES)
    assert any("/api/files/tus/abc".startswith(p) for p in UPLOAD_PREFIXES)


def test_throttle_no_longer_books_upload_volume(engine, monkeypatch):
    booked = []
    monkeypatch.setattr(sec, "count_upload", lambda *a, **k: booked.append(a))
    calls = []
    monkeypatch.setattr(ThrottleMiddleware, "_record_rule_block",
                        lambda self, *a, **k: calls.append(a))

    app = FastAPI()

    @app.post("/api/files/tus/{upload_id}")
    async def patch(upload_id: str):
        return {"ok": True}

    app.add_middleware(SessionMiddleware, redis_client=engine)
    app.add_middleware(ThrottleMiddleware)
    client = TestClient(app, base_url="https://app.example")
    for _ in range(4):
        assert client.post("/api/files/tus/abc-123", headers=_cf({})).status_code == 200
    assert booked == []   # chunk traffic is not 'uploads'


def test_tus_creation_books_exactly_one_upload(monkeypatch):
    from app.api.v1 import files as files_api
    booked = []
    monkeypatch.setattr(sec, "count_upload",
                        lambda uid, ip, username=None, snapshot=None: booked.append((uid, ip, username)))
    monkeypatch.setattr(files_api.FileService, "create_tus_upload",
                        lambda self, uid, parent, name, size: {"upload_id": "u-1"})
    monkeypatch.setattr(files_api.FileService, "append_tus_chunk",
                        lambda self, uid, off, body, user_id=None: {"offset": off + len(body)})

    req = _FakeRequest(cookie_user=("alice", 5))
    asyncio.run(files_api.tus_create_upload(
        request=req,
        upload_metadata="filename " + _b64("a.txt"),
        upload_length="5",
        tus_resumable="1.0.0",
        x_parent_folder_uuid=None,
        db=None, redis=None, user_id=5))
    assert booked == [(5, "203.0.113.7", "alice")]


def test_multipart_upload_books_one_upload(monkeypatch, tmp_path):
    from app.api.v1 import files as files_api
    booked = []
    monkeypatch.setattr(sec, "count_upload",
                        lambda uid, ip, username=None, snapshot=None: booked.append((uid, username)))
    monkeypatch.setattr(files_api.FileService, "upload_file",
                        lambda self, uid, parent, f, size: {"stateCode": 200, "uuid": "f-1"})

    class _Up:
        filename = "b.txt"
        sent = False

        async def read(self, n=-1):
            if self.sent:
                return b""
            self.sent = True
            return b"hello"

    asyncio.run(files_api.upload_file(
        request=_FakeRequest(), file=_Up(), parent_folder_uuid=None, relative_path=None,
        db=None, redis=None, user_id=7))
    assert booked == [(7, None)]


class _FakeRequest:
    """Minimal stand-in for starlette Request (headers/state/body/stream)."""
    client = type("c", (), {"host": "203.0.113.7"})()

    def __init__(self, cookie_user=None):
        self.headers = {"cf-connecting-ip": "203.0.113.7"}
        self.state = type("S", (), {})()
        if cookie_user:
            username, uid = cookie_user
            self.state.user = {"username": username, "user_id": uid}

    async def body(self):
        return b""

    def url_for(self, *a, **k):
        return "/api/files/tus"

    async def stream(self):
        if False:
            yield b''


def _b64(s):
    import base64
    return base64.b64encode(s.encode()).decode()


# ------------------------------------------------- stage maths / lowered thresholds

def test_transfer_stage_survives_lowered_threshold():
    assert sec.transfer_stage(10, 100) == 0
    assert sec.transfer_stage(101, 100) == 1
    assert sec.transfer_stage(201, 100) == 2
    # admin lowers 100 -> 5 while the counter already sits at 120: the old
    # `n == limit + 1` test would never fire again, this one escalates at once
    assert sec.transfer_stage(120, 5) == 2
    assert sec.transfer_stage(8, 5) == 1


def test_claim_stage_once_per_window():
    r = _CountingRedis()
    assert sec.claim_stage(r, "xfer:up:u1:s1", 3600) is True
    assert sec.claim_stage(r, "xfer:up:u1:s1", 3600) is False
    assert sec.claim_stage(r, "xfer:up:u1:s2", 3600) is True


def test_count_upload_escalates_once_and_invalidates_cache(monkeypatch):
    r = _CountingRedis()
    monkeypatch.setattr(sec, "_client", lambda: r)
    monkeypatch.setattr(sec, "_incr_windowed", lambda *a, **k: 601)  # over the 600 limit
    rules, invalidations, alerts = [], [], []
    monkeypatch.setattr(sec, "_ensure_auto_rule",
                        lambda *a, **k: rules.append(a[1:]) or True)
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: invalidations.append(1))
    monkeypatch.setattr(sec, "_alert", lambda *a, **k: alerts.append(a))
    sec.count_upload(3, "1.2.3.4", "alice")
    sec.count_upload(3, "1.2.3.4", "alice")
    assert len(rules) == 1 and rules[0][1] == "slow"
    assert invalidations and alerts
    assert alerts[0][2] == "alice" and "601" in alerts[0][4]


def test_auto_slow_rule_from_scoring_invalidates_cache(monkeypatch):
    """The score-driven slow lane must be visible immediately, not after the
    60s rules cache TTL (admin UI and this worker would disagree)."""
    r = _CountingRedis()
    monkeypatch.setattr(sec, "_client", lambda: r)
    monkeypatch.setattr(sec, "write_event", lambda *a: None)
    monkeypatch.setattr(sec, "_incr_ttl", lambda *a, **k: sec.settings.SEC_SCORE_SLOW_THRESHOLD)
    invalidations = []
    monkeypatch.setattr(sec, "_ensure_auto_rule", lambda *a, **k: True)
    monkeypatch.setattr(sec, "invalidate_rules_cache", lambda: invalidations.append(1))
    monkeypatch.setattr(sec, "_alert", lambda *a, **k: None)
    REAL["record_event"]("rate_limit", "1.2.3.4", None, "/api/x", "限流")
    assert invalidations


def test_unscored_event_never_moves_the_score(monkeypatch):
    r = _CountingRedis()
    touched = []
    monkeypatch.setattr(sec, "_client", lambda: r)
    monkeypatch.setattr(sec, "write_event", lambda *a: None)
    monkeypatch.setattr(sec, "_incr_ttl",
                        lambda rr, key, amount, ttl: touched.append((key, amount)) or 0)
    REAL["record_event"]("rate_limit", "1.2.3.4", None, "/api/x", "限流", score=False)
    assert touched == []
