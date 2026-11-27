"""Round 24 (PR③): the risk-threshold registry, its versioned storage and the
生效邊界 rules (one snapshot per request, windows never retroactively changed,
thresholds never silently disabled when the database is unavailable)."""
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base
from app.models.security_policy import SecurityPolicyVersion
from app.services import security_engine as sec
from app.services import security_policy as sp
from tests.test_round24_identity import REAL


@pytest.fixture
def sqlite(monkeypatch):
    """Back the version table with SQLite; reset every process cache."""
    eng = create_engine("sqlite://", echo=False)
    SecurityPolicyVersion.__table__.create(bind=eng)
    factory = sessionmaker(bind=eng)
    monkeypatch.setattr("app.database.SessionLocal", factory)
    sp._snapshot = None
    sp._fetched_at = 0.0
    yield factory
    sp._snapshot = None
    sp._fetched_at = 0.0


@pytest.fixture
def fake_clock(monkeypatch):
    """Deterministic time for the refresh TTL (no sleeps)."""
    t = {"now": 1000.0}
    monkeypatch.setattr(sp.time, "monotonic", lambda: t["now"])
    return t


# ------------------------------------------------------------------ registry

EXPECTED_DEFAULTS = {
    "global.flood_requests_per_ip": 5000,
    "global.flood_window_seconds": 3600,
    "score.slow_threshold": 20,
    "score.auth_block_threshold": 15,
    "score.escalated_block_threshold": 40,
    "volume.uploads_per_hour_per_account": 600,
    "volume.downloads_per_hour_per_account": 300,
    "volume.anon_share_downloads_per_hour": 150,
    "slow.upload_delay_ms": 2000,
    "slow.download_delay_ms": 0,
    "slow.upload_kbps": 256,
    "slow.download_kbps": 512,
    "share.password_failures_per_window": 10,
    "share.password_window_seconds": 900,
    "collab.room_max_connections": 50,
    "collab.ws_messages_per_minute": 1200,
    "endpoint.accounts_register": 5,
    "endpoint.accounts_login": 5,
    "endpoint.accounts_get_code": 1,
    "endpoint.accounts_reset_pw": 2,
    "endpoint.files_tus_create": 30,
    "endpoint.files_multipart": 30,
    "endpoint.files_create": 20,
    "endpoint.files_content_read": 60,
    "endpoint.files_content_write": 30,
    "endpoint.files_stream": 300,
    "endpoint.preview_token": 30,
    "endpoint.preview_raw": 120,
    "endpoint.share_verify_password": 5,
    "endpoint.share_download_items": 10,
    "endpoint.collab_ws_ticket": 30,
    "endpoint.collab_add_collaborator": 15,
}


def test_registry_defaults_match_migrated_behaviour():
    for pid, value in EXPECTED_DEFAULTS.items():
        assert sp.REGISTRY[pid].default == value, pid


def test_settings_still_agree_with_registry_defaults():
    """Deployment values (env) must keep working: the registry mirrors them."""
    pairs = {
        "global.flood_requests_per_ip": "SEC_GLOBAL_HOURLY_LIMIT",
        "score.slow_threshold": "SEC_SCORE_SLOW_THRESHOLD",
        "score.auth_block_threshold": "SEC_SCORE_BLOCK_THRESHOLD",
        "volume.uploads_per_hour_per_account": "SEC_UPLOAD_HOURLY_LIMIT",
        "volume.downloads_per_hour_per_account": "SEC_DOWNLOAD_HOURLY_LIMIT",
        "volume.anon_share_downloads_per_hour": "SEC_ANON_DOWNLOAD_HOURLY_LIMIT",
        "slow.upload_delay_ms": "SEC_DEFAULT_UPLOAD_DELAY_MS",
        "slow.download_delay_ms": "SEC_DEFAULT_DOWNLOAD_DELAY_MS",
        "slow.upload_kbps": "SEC_DEFAULT_UPLOAD_KBPS",
        "slow.download_kbps": "SEC_DEFAULT_DOWNLOAD_KBPS",
        "collab.room_max_connections": "MAX_ROOM_CONNECTIONS",
        "collab.ws_messages_per_minute": "WS_MSG_PER_MIN",
    }
    for pid, attr in pairs.items():
        assert getattr(settings, attr) == sp.REGISTRY[pid].default


def test_effective_precedence_override_then_deployment_then_code(sqlite, monkeypatch):
    assert sp.value("global.flood_requests_per_ip") == 5000
    monkeypatch.setattr(settings, "SEC_GLOBAL_HOURLY_LIMIT", 7000, raising=False)
    sp.invalidate_cache()
    assert sp.value("global.flood_requests_per_ip") == 7000          # deployment
    sp.commit({"global.flood_requests_per_ip": 1234}, actor="boss", expected_version=0)
    assert sp.value("global.flood_requests_per_ip") == 1234          # admin wins


def test_describe_reports_source(sqlite, monkeypatch):
    row = sp.describe("global.flood_requests_per_ip")
    assert row["source"] == "程式預設"
    monkeypatch.setattr(settings, "SEC_GLOBAL_HOURLY_LIMIT", 7000, raising=False)
    assert sp.describe("global.flood_requests_per_ip")["source"] == "部署設定"
    sp.commit({"global.flood_requests_per_ip": 1234}, actor="boss", expected_version=0)
    row = sp.describe("global.flood_requests_per_ip")
    assert row["source"] == "管理員覆寫" and row["value"] == 1234
    assert row["unit"] == "次" and row["action"] and row["subject"]
    assert "活動續期" in row["window"]      # semantics are spelled out, not implied


def test_endpoint_windows_are_displayed_but_pinned_to_route():
    row = sp.describe("endpoint.files_tus_create")
    assert row["window_editable"] is False and row["window_seconds"] == 300
    assert row["route"] == "/api/files/tus" and row["method"] == "POST"


def test_content_read_and_write_share_one_bucket_in_ui():
    for pid in ("endpoint.files_content_read", "endpoint.files_content_write"):
        assert "共用" in sp.REGISTRY[pid].depends


def test_no_unbounded_or_zero_disabling_values():
    for p in sp.REGISTRY.values():
        assert p.max_value > p.min_value
        if not p.allow_zero:
            assert p.min_value >= 1, p.id


# ------------------------------------------------------------------ validation

@pytest.mark.parametrize("changes,frag", [
    ({"nope.nope": 5}, "未知政策"),
    ({"global.flood_requests_per_ip": 0}, "不可小於"),
    ({"global.flood_requests_per_ip": 10_000_001}, "不可大於"),
    ({"global.flood_requests_per_ip": "5000"}, "整數"),
    ({"score.slow_threshold": 50, "score.escalated_block_threshold": 30}, "必須大於"),
])
def test_invalid_values_rejected(sqlite, changes, frag):
    with pytest.raises(sp.PolicyError) as exc:
        sp.commit(changes, actor="boss", expected_version=0)
    assert frag in str(exc.value)


def test_group_is_applied_atomically(sqlite):
    with pytest.raises(sp.PolicyError):
        sp.commit({"global.flood_requests_per_ip": 10, "slow.upload_kbps": -1},
                  actor="boss", expected_version=0)
    snap = sp.current(force=True)
    assert snap.overrides == {} and snap.version == 0


def test_edit_and_reset_share_one_version(sqlite):
    flood = "global.flood_requests_per_ip"
    upload = "slow.upload_kbps"
    sp.commit({flood: 4000}, expected_version=0)
    with pytest.raises(sp.PolicyError):
        sp.commit({upload: -1}, reset_ids=[flood], expected_version=1)
    assert sp.current(force=True).value(flood) == 4000
    result = sp.commit({upload: 64}, reset_ids=[flood], expected_version=1)
    assert result["version"] == 2
    assert set(result["changed"]) == {flood, upload}
    assert sp.current(force=True).overrides == {upload: 64}


def test_websocket_policy_cannot_be_changed(sqlite):
    with pytest.raises(sp.PolicyError, match="唯讀"):
        sp.commit({"collab.room_max_connections": 80}, expected_version=0)


# ------------------------------------------------------------------ versioning

def test_commit_stale_write_conflicts(sqlite):
    out = sp.commit({"global.flood_requests_per_ip": 4000}, actor="boss", actor_id=1,
                    reason="降低 flood", expected_version=0)
    assert out["version"] == 1 and out["changed"]["global.flood_requests_per_ip"]["before"] == 5000
    with pytest.raises(sp.StaleVersion) as exc:
        sp.commit({"global.flood_requests_per_ip": 3000}, actor="other", expected_version=0)
    assert exc.value.current_version == 1


def test_rollback_creates_new_version_and_keeps_history(sqlite):
    sp.commit({"global.flood_requests_per_ip": 4000}, actor="boss", reason="v1", expected_version=0)
    sp.commit({"global.flood_requests_per_ip": 1000}, actor="boss", reason="v2", expected_version=1)
    preview = sp.preview_rollback(1, 2)
    assert sp.current(force=True).version == 2
    assert preview["changed"]["global.flood_requests_per_ip"]["after"] == 4000
    out = sp.rollback_to(1, actor="boss", reason="回到 v1", expected_version=2)
    assert out["changed"] == preview["changed"]
    assert out["version"] == 3 and out["rolled_back_to"] == 1
    assert sp.value("global.flood_requests_per_ip") == 4000
    hist = sp.history()
    assert [h["version"] for h in hist] == [3, 2, 1]
    assert hist[0]["action"] == "rollback" and hist[0]["reason"] == "回到 v1"
    assert hist[0]["actor"] == "boss"
    assert hist[2]["changed"]["global.flood_requests_per_ip"] == {"before": 5000, "after": 4000,
                                                                  "label": "全站 flood 請求量"}


def test_reset_drops_overrides_without_deleting_history(sqlite):
    sp.commit({"global.flood_requests_per_ip": 4000, "slow.upload_kbps": 64},
              actor="boss", expected_version=0)
    out = sp.reset_to_defaults(["global.flood_requests_per_ip"], actor="boss", expected_version=1)
    assert out["version"] == 2
    assert sp.value("global.flood_requests_per_ip") == 5000
    assert sp.value("slow.upload_kbps") == 64          # untouched
    assert len(sp.history()) == 2


def test_noop_change_does_not_bump_version(sqlite):
    out = sp.commit({"global.flood_requests_per_ip": 5000}, actor="boss", expected_version=0)
    assert out["noop"] is True and out["version"] == 0
    assert sp.history() == []


def test_payload_stores_only_known_ids(sqlite):
    with sqlite() as db:
        db.add(SecurityPolicyVersion(id=1, payload=json.dumps({"ghost.policy": 3,
                                                               "global.flood_requests_per_ip": 9}),
                                     created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1)))
        db.commit()
    snap = sp.current(force=True)
    assert snap.overrides == {"global.flood_requests_per_ip": 9}


# ------------------------------------------------------------------ availability

def test_failed_refresh_keeps_last_verified_snapshot(sqlite, monkeypatch, fake_clock):
    sp.commit({"global.flood_requests_per_ip": 4000}, actor="boss", expected_version=0)
    assert sp.value("global.flood_requests_per_ip") == 4000

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(sp, "_read_latest", boom)
    fake_clock["now"] += sp.REFRESH_SECONDS + 1
    assert sp.value("global.flood_requests_per_ip") == 4000     # last good snapshot


def test_cold_start_without_snapshot_uses_deployment_defaults(sqlite, monkeypatch, fake_clock):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(sp, "_read_latest", boom)
    monkeypatch.setattr(settings, "SEC_UPLOAD_HOURLY_LIMIT", 111, raising=False)
    sp._snapshot = None
    assert sp.value("volume.uploads_per_hour_per_account") == 111
    assert sp.current().version == 0     # protections stay on, just unmanaged


# ------------------------------------------------------------------ 生效邊界

def test_incr_windowed_pins_the_original_window():
    class R:
        def __init__(self):
            self.store = {}
            self.ttls = {}

        def eval(self, script, numkeys, key, marker, amount, window):
            count = self.store.get(key, 0) + amount
            duration = self.store.get(marker, 3600) if count != amount else window
            self.store.update({key: count, marker: duration})
            self.ttls.update({key: duration, marker: duration})
            return count

        def pipeline(self):
            outer = self

            class P:
                def __init__(self):
                    self.ops = []

                def incrby(self, key, amount):
                    self.ops.append(("incrby", key, amount))
                    return self

                def get(self, key):
                    self.ops.append(("get", key))
                    return self

                def execute(self):
                    out = []
                    for op in self.ops:
                        if op[0] == "incrby":
                            _, key, amount = op
                            outer.store[key] = int(outer.store.get(key, 0)) + amount
                            out.append(outer.store[key])
                        else:
                            out.append(outer.store.get(op[1]))
                    return out

            return P()

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.store:
                return None
            self.store[key] = value
            self.ttls[key] = ex
            return True

        def expire(self, key, seconds):
            self.ttls[key] = seconds
            return True

        def get(self, key):
            return self.store.get(key)

    r = R()
    assert sec._incr_windowed(r, "bkt", 1, 3600) == 1
    assert r.ttls["bkt"] == 3600 and r.ttls["bkt:w"] == 3600
    # an admin raising the window must NOT stretch a bucket that is already open
    assert sec._incr_windowed(r, "bkt", 1, 7200) == 2
    assert r.ttls["bkt"] == 3600 and r.ttls["bkt:w"] == 3600


def test_lowered_flood_threshold_still_reports(monkeypatch):
    """After a threshold is lowered mid-window the counter is already past it;
    the old `n == limit + 1` test would never fire again."""
    events = []
    monkeypatch.setattr(sec, "record_event", lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(sec, "flood_exceeded", REAL["flood_exceeded"])
    r = {"count": 0}

    class FakeR:
        def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

    store = {}
    monkeypatch.setattr(sec, "_client", lambda: FakeR())
    monkeypatch.setattr(sec, "_incr_windowed", lambda *a, **k: 900)   # way past the new limit
    snap = sp.Snapshot(version=0, overrides={"global.flood_requests_per_ip": 500})
    assert sec.flood_exceeded("1.2.3.4", "alice", "/api/x", snap) is True
    assert events and events[0][0][0] == "flood"
    # second rejection inside the same window: still blocking, only one report
    assert sec.flood_exceeded("1.2.3.4", "alice", "/api/x", snap) is True
    assert len(events) == 1


def test_rate_limit_obeys_admin_override(monkeypatch):
    from fastapi import Depends, FastAPI
    from starlette.testclient import TestClient

    from app.api.dependencies import get_redis
    from app.api.rate_limit import rate_limit

    class CountingRedis:
        def __init__(self):
            self.counts = {}

        def eval(self, script, numkeys, key, marker, limit, window):
            self.counts[key] = self.counts.get(key, 0) + 1
            count = self.counts[key]
            return [count, int(count > limit and bool(self.set(marker, '1', nx=True, ex=window)))]

        def pipeline(self):
            outer = self

            class P:
                key = None

                def incr(self, key):
                    self.key = key
                    return self

                def ttl(self, key):
                    return self

                def execute(self):
                    outer.counts[self.key] = outer.counts.get(self.key, 0) + 1
                    return [outer.counts[self.key], 60]

            return P()

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.counts:
                return None
            self.counts[key] = value
            return True

        def expire(self, key, seconds):
            return True

    redis = CountingRedis()
    monkeypatch.setattr(sp, "current", lambda force=False: sp.Snapshot(
        version=7, overrides={"endpoint.files_tus_create": 2}))
    monkeypatch.setattr(sec, "record_event", lambda *a, **k: None)

    app = FastAPI()

    @app.post("/api/files/tus", dependencies=[Depends(rate_limit(30, 300, "endpoint.files_tus_create"))])
    async def tus():
        return {"ok": True}

    app.dependency_overrides[get_redis] = lambda: redis
    client = TestClient(app)
    hdr = {"cf-connecting-ip": "198.51.100.7"}
    got = [client.post("/api/files/tus", headers=hdr).status_code for _ in range(4)]
    # the admin override (2) wins over the code default (30)
    assert got == [200, 200, 429, 429]


# ------------------------------------------------------------------ admin API

def _req(identity="admin"):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.constants import Identity
    req = MagicMock()
    req.state.user = {"identity": Identity.ADMIN if identity == "admin" else Identity.USER,
                      "id": 1, "username": "boss", "user_id": 1}
    req.client = SimpleNamespace(host="198.51.100.1")
    req.headers = {}
    req.method = "PUT"
    return req


def _api():
    from app.api.v1 import ipcontrol
    return ipcontrol


def test_policy_listing_requires_admin(sqlite):
    import asyncio

    api = _api()
    out = asyncio.run(api.admin_policies(request=_req()))
    assert out["version"] == 0
    assert {g["name"] for g in out["groups"]} >= {"全站 flood", "端點請求量", "IP 違規積分"}
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.admin_policies(request=_req("user")))
    assert exc.value.status_code == 403


def test_policy_update_validates_and_records_audit(sqlite, monkeypatch):
    import asyncio

    written = []
    api = _api()
    monkeypatch.setattr(api, "write_event", lambda *a: written.append(a))
    out = asyncio.run(api.admin_policy_update(
        api.PolicyUpdate(changes={"global.flood_requests_per_ip": 4000},
                         expected_version=0, reason="誤觸事件過多"), request=_req()))
    assert out["version"] == 1
    assert written[0][0] == "policy_update" and written[0][2] == "boss"
    assert "4000" in written[0][4] and "誤觸事件過多" in written[0][4]

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.admin_policy_update(
            api.PolicyUpdate(changes={"global.flood_requests_per_ip": 0},
                             expected_version=1), request=_req()))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.admin_policy_update(
            api.PolicyUpdate(changes={"global.flood_requests_per_ip": 10},
                             expected_version=0), request=_req()))
    assert exc.value.status_code == 409 and "v1" in exc.value.detail
    # the rejected writes left no trace
    assert sp.current(force=True).version == 1


def test_policy_history_and_rollback_endpoints(sqlite, monkeypatch):
    import asyncio

    api = _api()
    monkeypatch.setattr(api, "write_event", lambda *a: None)
    asyncio.run(api.admin_policy_update(
        api.PolicyUpdate(changes={"slow.upload_kbps": 128}, expected_version=0, reason="v1"),
        request=_req()))
    asyncio.run(api.admin_policy_update(
        api.PolicyUpdate(changes={"slow.upload_kbps": 32}, expected_version=1, reason="v2"),
        request=_req()))
    hist = asyncio.run(api.admin_policy_history(request=_req(), limit=10))["history"]
    assert [h["version"] for h in hist] == [2, 1]
    out = asyncio.run(api.admin_policy_rollback(
        api.PolicyRollback(to_version=1, expected_version=2, reason="回退"), request=_req()))
    assert out["version"] == 3
    assert sp.value("slow.upload_kbps") == 128


def test_second_worker_converges_on_the_same_value(sqlite):
    """Workers share no memory: each one re-reads the version table when its
    cache TTL elapses, so everybody ends up on the same effective value — and
    a rollback is equally visible everywhere."""
    import time

    sp.commit({"global.flood_requests_per_ip": 4000}, actor="boss", expected_version=0)
    # simulate a second worker that still holds the pre-change snapshot and a
    # cache that has not expired yet
    sp._snapshot = sp.Snapshot(version=0, overrides={})
    sp._fetched_at = time.monotonic()
    assert sp.value("global.flood_requests_per_ip") == 5000        # still its old view
    sp._fetched_at = time.monotonic() - sp.REFRESH_SECONDS - 1      # TTL elapsed
    assert sp.value("global.flood_requests_per_ip") == 4000
    assert sp.current().version == 1
    sp.rollback_to(0, actor="boss", reason="回滾到無覆寫", expected_version=1)
    sp._fetched_at = time.monotonic() - sp.REFRESH_SECONDS - 1
    assert sp.value("global.flood_requests_per_ip") == 5000


def test_threshold_change_does_not_reset_counters_or_rules(sqlite, monkeypatch):
    """Lowering a threshold must not clear an open window nor lift a live block."""
    counters = {}

    class R:
        def set(self, key, value, nx=False, ex=None):
            if nx and key in counters:
                return None
            counters[key] = value
            return True

        def get(self, key):
            return counters.get(key)

        def expire(self, key, seconds):
            return True

        def pipeline(self):
            raise AssertionError("use the pinned-window helper directly")

    monkeypatch.setattr(sec, "_client", lambda: R())
    monkeypatch.setattr(sec, "flood_exceeded", REAL["flood_exceeded"])
    monkeypatch.setattr(sec, "_incr_windowed",
                        lambda r, key, amount, window: int(r.get(key) or 0))
    monkeypatch.setattr(sec, "record_event", lambda *a, **k: None)
    counters["glb:1.2.3.4"] = 900                       # counter already open
    snap_before = sp.Snapshot(version=0, overrides={})
    assert snap_before.value("global.flood_requests_per_ip") == 5000
    sp.commit({"global.flood_requests_per_ip": 500}, actor="boss", expected_version=0)
    snap_after = sp.current(force=True)
    assert counters["glb:1.2.3.4"] == 900               # counter untouched
    assert counters.get("rules", None) is None          # no rule was created here
    assert REAL["flood_exceeded"]("1.2.3.4", None, "/x", snap_after) is True
    assert counters["glb:1.2.3.4"] == 900               # reporting never resets it either
