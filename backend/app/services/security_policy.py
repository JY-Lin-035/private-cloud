"""Central registry of application-layer rate-limit / risk thresholds (round 24 PR③).

Everything the site uses to *decide* whether to slow down or reject lives here
behind a fixed policy id. The point is not to build a generic settings blob:

  * ids are fixed and enumerated in code — no arbitrary route, no arbitrary
    Redis key, no "0 means off" surprise, and no unbounded value
  * effective value = admin override -> deployment setting -> code default
  * the SQL table only stores immutable *versions*; the hot path reads an
    in-process snapshot (refreshed with a short TTL), never the database
  * a snapshot is validated as a whole; a failed refresh keeps serving the
    last verified snapshot, and a cold start with no snapshot at all falls
    back to the deployment defaults — protections are never silently dropped
"""
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings

REFRESH_SECONDS = 15.0
# How long to keep serving the fallback snapshot after a failed read. A
# degraded database must not turn into a connection attempt per request.
RETRY_AFTER_FAILURE = 60.0


@dataclass(frozen=True)
class Policy:
    id: str
    label: str
    group: str
    default: int
    unit: str
    subject: str            # what is counted
    window: str             # human-readable window semantics
    action: str             # what happens when it is exceeded
    min_value: int = 1
    max_value: int = 100_000_000
    editable: bool = True
    allow_zero: bool = False
    setting: Optional[str] = None        # deployment override env name
    window_seconds: Optional[int] = None  # bucket length in seconds
    route: Optional[str] = None
    method: Optional[str] = None
    depends: str = ""
    #: set when the value cannot be edited from the admin UI (different
    #: execution layer, e.g. per-worker WebSocket accounting)
    note: str = ""


def _p(**kw) -> Policy:
    return Policy(**kw)


# ------------------------------------------------------------------ endpoint limits
# Bucket = IP + URL path, fixed window armed on the first request of the window.
# The window belongs to the route decorator, so it is displayed but not editable.
_ENDPOINTS = [
    _p(id="endpoint.accounts_register", label="註冊", group="端點請求量", default=5, unit="次",
       window_seconds=300, route="/api/accounts/register", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       editable=True, max_value=10000),
    _p(id="endpoint.accounts_login", label="登入", group="端點請求量", default=5, unit="次",
       window_seconds=30, route="/api/accounts/login", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=10000),
    _p(id="endpoint.accounts_get_code", label="寄送驗證碼", group="端點請求量", default=1, unit="次",
       window_seconds=30, route="/api/accounts/getCode", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=1000),
    _p(id="endpoint.accounts_reset_pw", label="重設密碼", group="端點請求量", default=2, unit="次",
       window_seconds=30, route="/api/accounts/resetPW", method="PUT",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=10000),
    _p(id="endpoint.files_tus_create", label="TUS 上傳建立", group="端點請求量", default=30, unit="次",
       window_seconds=300, route="/api/files/tus", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000,
       depends="只計建立；既有上傳的 HEAD／PATCH 不進這個桶（仍受全站 flood 與規則約束）"),
    _p(id="endpoint.files_multipart", label="Multipart 上傳", group="端點請求量", default=30, unit="次",
       window_seconds=300, route="/api/files/uploadFile", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000),
    _p(id="endpoint.files_create", label="新增檔案記錄", group="端點請求量", default=20, unit="次",
       window_seconds=300, route="/api/files/create", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000),
    _p(id="endpoint.files_content_read", label="內容讀取", group="端點請求量", default=60, unit="次",
       window_seconds=60, route="/api/files/content", method="GET",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000,
       depends="與內容寫入共用同一個計數桶（共用桶），但各自套用自己的上限"),
    _p(id="endpoint.files_content_write", label="內容寫入", group="端點請求量", default=30, unit="次",
       window_seconds=60, route="/api/files/content", method="PUT",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000,
       depends="與內容讀取共用同一個計數桶（共用桶），但各自套用自己的上限"),
    _p(id="endpoint.files_stream", label="串流讀取", group="端點請求量", default=300, unit="次",
       window_seconds=60, route="/api/files/stream", method="GET",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=1000000),
    _p(id="endpoint.preview_token", label="預覽票券", group="端點請求量", default=30, unit="次",
       window_seconds=60, route="/api/preview/previewToken", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000),
    _p(id="endpoint.preview_raw", label="raw 預覽", group="端點請求量", default=120, unit="次",
       window_seconds=60, route="/api/preview/raw", method="GET",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=1000000),
    _p(id="endpoint.share_verify_password", label="分享密碼驗證", group="端點請求量", default=5, unit="次",
       window_seconds=300, route="/api/share/verifyPassword", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=10000,
       depends="與分享密碼鎖（错误次數）疊加計算"),
    _p(id="endpoint.share_download_items", label="分享多選下載", group="端點請求量", default=10, unit="次",
       window_seconds=60, route="/api/share/downloadItems", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000),
    _p(id="endpoint.collab_ws_ticket", label="共編票券", group="端點請求量", default=30, unit="次",
       window_seconds=60, route="/api/collaboration/wsTicket", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000),
    _p(id="endpoint.collab_add_collaborator", label="新增協作者", group="端點請求量", default=15, unit="次",
       window_seconds=60, route="/api/collaboration/addCollaborator", method="POST",
       subject="IP + 路由", window="固定視窗（首次請求開窗，到時重算）", action="HTTP 429",
       max_value=100000),
]

POLICIES: tuple[Policy, ...] = (
    *_ENDPOINTS,
    _p(id="global.flood_requests_per_ip", label="全站 flood 請求量", group="全站 flood",
       default=5000, unit="次", setting="SEC_GLOBAL_HOURLY_LIMIT", window_seconds=3600,
       subject="IP（所有請求）",
       window="活動續期視窗：每次請求都把 3,600 秒 TTL 往後刷新，不是整點重算，也不是精確的滾動小時",
       action="HTTP 429（直接拒絕，不含延遲）", max_value=10_000_000,
       depends="先於規則與端點限流判定；觸發時不區分 method"),
    _p(id="global.flood_window_seconds", label="全站 flood 時間窗", group="全站 flood",
       default=3600, unit="秒", min_value=60, max_value=86400,
       subject="同上", window="桶長度；改此值只對新开的桶生效", action="同上",
       depends="既有桶沿用開窗當下的長度直到到期"),
    _p(id="score.slow_threshold", label="違規積分：進入傳輸慢速", group="IP 違規積分",
       default=20, unit="分", setting="SEC_SCORE_SLOW_THRESHOLD",
       subject="IP（違規事件加權積分）", window="積分桶 1 小時（活動時刷新）",
       action="自動 slow 規則 1 小時（延遲 + 頻寬限制）", max_value=10000,
       depends="每次請求的端點限流事件權重 2 分；同視窗只計一次"),
    _p(id="score.auth_block_threshold", label="違規積分：驗證類直封", group="IP 違規積分",
       default=15, unit="分", setting="SEC_SCORE_BLOCK_THRESHOLD",
       subject="IP（登入/註冊/驗證碼/分享密碼等驗證類端點）", window="積分桶 1 小時（活動時刷新）",
       action="全站 block（依封鎖階梯）", max_value=10000,
       depends="與一般積分為兩個獨立的桶"),
    _p(id="score.escalated_block_threshold", label="違規積分：慢速升級封鎖", group="IP 違規積分",
       default=40, unit="分", min_value=2, max_value=10000,
       subject="IP", window="同上", action="全站 block（依封鎖階梯）",
       depends="固定為「慢速門檻 × 2」；改這個值等於改 score.slow_threshold 的兩倍",
       note="值由 score.slow_threshold × 2 推導，編輯此項會一併影響升級判定"),
    _p(id="volume.uploads_per_hour_per_account", label="帳號上傳量（慢速）", group="帳號／分享傳輸量",
       default=600, unit="次", setting="SEC_UPLOAD_HOURLY_LIMIT", window_seconds=3600,
       subject="帳號（成功建立的上傳次數）", window="活動續期視窗：每次上傳刷新 3,600 秒 TTL",
       action="自動 slow 規則 1 小時；達 2 倍轉 block", max_value=1_000_000),
    _p(id="volume.upload_window_seconds", label="上傳量時間窗", group="帳號／分享傳輸量",
       default=3600, unit="秒", min_value=60, max_value=86400,
       subject="同上", window="桶長度；改此值只對新开的桶生效", action="同上"),
    _p(id="volume.downloads_per_hour_per_account", label="帳號下載量（慢速）", group="帳號／分享傳輸量",
       default=300, unit="次", setting="SEC_DOWNLOAD_HOURLY_LIMIT", window_seconds=3600,
       subject="帳號（下載請求次數；串流 seek 不重計）",
       window="活動續期視窗：每次下載刷新 3,600 秒 TTL",
       action="自動 slow 規則 1 小時；達 2 倍轉 block", max_value=1_000_000),
    _p(id="volume.download_window_seconds", label="下載量時間窗", group="帳號／分享傳輸量",
       default=3600, unit="秒", min_value=60, max_value=86400,
       subject="同上", window="桶長度；改此值只對新开的桶生效", action="同上"),
    _p(id="volume.anon_share_downloads_per_hour", label="匿名分享下載量（慢速）", group="帳號／分享傳輸量",
       default=150, unit="次", setting="SEC_ANON_DOWNLOAD_HOURLY_LIMIT", window_seconds=3600,
       subject="IP + 分享連結", window="活動續期視窗：每次下載刷新 3,600 秒 TTL",
       action="自動 ip_token slow 規則 1 小時；達 2 倍轉 block", max_value=1_000_000),
    _p(id="volume.anon_share_download_window_seconds", label="匿名分享下載時間窗", group="帳號／分享傳輸量",
       default=3600, unit="秒", min_value=60, max_value=86400,
       subject="同上", window="桶長度；改此值只對新开的桶生效", action="同上"),
    _p(id="slow.upload_delay_ms", label="預設上傳延遲", group="慢速規則",
       default=2000, unit="毫秒", setting="SEC_DEFAULT_UPLOAD_DELAY_MS", allow_zero=True,
       min_value=0, max_value=60000, subject="套用規則的請求（每請求）", window="無（每次請求皆套用）",
       action="回應前等待，不拒絕",
       depends="寫入自動 slow／block 規則時作為預設值；已存在的規則不受影響"),
    _p(id="slow.download_delay_ms", label="預設下載延遲", group="慢速規則",
       default=0, unit="毫秒", setting="SEC_DEFAULT_DOWNLOAD_DELAY_MS", allow_zero=True,
       min_value=0, max_value=60000, subject="套用規則的請求（每請求）", window="無（每次請求皆套用）",
       action="回應前等待，不拒絕",
       depends="雙向（both）自動規則共用同一個延遲值"),
    _p(id="slow.upload_kbps", label="預設上傳頻寬", group="慢速規則",
       default=256, unit="KiB/s", setting="SEC_DEFAULT_UPLOAD_KBPS", max_value=1_048_576,
       subject="套用規則的請求（每請求，非帳號總頻寬）", window="無（每次請求皆套用）",
       action="限速傳輸",
       depends="寫入自動 slow 規則時作為預設值"),
    _p(id="slow.download_kbps", label="預設下載頻寬", group="慢速規則",
       default=512, unit="KiB/s", setting="SEC_DEFAULT_DOWNLOAD_KBPS", max_value=1_048_576,
       subject="套用規則的請求（每請求，非帳號總頻寬）", window="無（每次請求皆套用）",
       action="限速傳輸",
       depends="寫入自動 slow 規則時作為預設值"),
    _p(id="share.password_failures_per_window", label="分享密碼錯誤次數", group="分享密碼鎖",
       default=10, unit="次", setting=None, window_seconds=900, min_value=1, max_value=1000,
       subject="IP + 分享連結", window="錯誤計數存 900 秒（與 share.password_window_seconds 同）",
       action="後續驗證回 HTTP 429",
       depends="與 /api/share/verifyPassword 的端點請求限額疊加"),
    _p(id="share.password_window_seconds", label="分享密碼鎖時間窗", group="分享密碼鎖",
       default=900, unit="秒", min_value=60, max_value=86400,
       subject="同上", window="桶長度；改此值只對新开的桶生效", action="同上"),
    _p(id="collab.room_max_connections", label="共編房間連線數", group="共編 WebSocket",
       default=50, unit="條連線", setting="MAX_ROOM_CONNECTIONS", subject="每個檔案房間（每 worker）",
       window="無（即時連線數）", action="WebSocket 關閉碼 4429", editable=False,
       note="計數在程序內的 RoomManager，語義是「每 worker、每房間」；與 HTTP 429 分開"),
    _p(id="collab.ws_messages_per_minute", label="共編訊息速率", group="共編 WebSocket",
       default=1200, unit="則", setting="WS_MSG_PER_MIN", subject="每條連線",
       window="每連線 60 秒固定計數", action="WebSocket 關閉碼 4429", editable=False,
       note="長連線的判定在連線建立時取樣，不即時採用新值"),
)

REGISTRY: dict[str, Policy] = {p.id: p for p in POLICIES}
GROUPS: tuple[str, ...] = tuple(dict.fromkeys(p.group for p in POLICIES))
WINDOW_IDS = {
    "global.flood_requests_per_ip": "global.flood_window_seconds",
    "volume.uploads_per_hour_per_account": "volume.upload_window_seconds",
    "volume.downloads_per_hour_per_account": "volume.download_window_seconds",
    "volume.anon_share_downloads_per_hour": "volume.anon_share_download_window_seconds",
    "share.password_failures_per_window": "share.password_window_seconds",
}


class PolicyError(ValueError):
    """Invalid value or unknown id supplied by an admin."""


def get(policy_id: str) -> Policy:
    try:
        return REGISTRY[policy_id]
    except KeyError:
        raise PolicyError(f"未知政策 ID：{policy_id}") from None


def code_default(policy_id: str) -> int:
    return get(policy_id).default


def deployment_value(policy_id: str) -> int:
    """What the running deployment (env/.env) says, else the code default."""
    p = get(policy_id)
    if p.setting:
        v = getattr(settings, p.setting, None)
        if isinstance(v, int):
            return v
    return p.default


def _valid(p: Policy, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyError(f"{p.label}必須是整數")
    if value < p.min_value or (value == 0 and not p.allow_zero):
        lower = p.min_value if p.allow_zero else max(p.min_value, 1)
        raise PolicyError(f"{p.label}不可小於 {lower}")
    if value > p.max_value:
        raise PolicyError(f"{p.label}不可大於 {p.max_value:,}")
    return value


def validate(changes: dict[str, int]) -> dict[str, int]:
    """Validate a whole group of edits; raises on the first problem so a bad
    value can never be half-applied."""
    out: dict[str, int] = {}
    for pid, value in changes.items():
        item = get(pid)
        if not item.editable:
            raise PolicyError(f"{item.label}為唯讀")
        out[pid] = _valid(item, value)
    _validate_dependencies(out)
    return out


def _validate_dependencies(changes: dict[str, int]) -> None:
    # score escalation is expressed as a multiple of the slow threshold; keep
    # the derived value from being *below* the stage it escalates from.
    slow = changes.get("score.slow_threshold", deployment_value("score.slow_threshold"))
    escalated = changes.get("score.escalated_block_threshold")
    if escalated is not None and escalated <= slow:
        raise PolicyError("慢速升級封鎖積分必須大於慢速門檻")


# ------------------------------------------------------------------ snapshot cache

@dataclass(frozen=True)
class Snapshot:
    version: int
    overrides: dict[str, int] = field(default_factory=dict)

    def value(self, policy_id: str) -> int:
        if policy_id in self.overrides:
            return self.overrides[policy_id]
        if policy_id == "score.escalated_block_threshold":
            return 2 * self.value("score.slow_threshold")
        return deployment_value(policy_id)

    def window(self, policy_id: str, fallback: int) -> int:
        """Bucket length for `policy_id`, taken from its own
        `<policy_id>_window_seconds` policy when one is registered."""
        candidate = WINDOW_IDS.get(policy_id)
        if candidate is not None:
            return self.value(candidate)
        return fallback

    def as_dict(self) -> dict:
        return {"version": self.version, "overrides": dict(self.overrides)}


_lock = threading.Lock()
_snapshot: Optional[Snapshot] = None      # last *verified* snapshot
_fetched_at = 0.0


def _read_latest():
    """(version, overrides) from SQL. Raises on failure (caller keeps the
    last verified snapshot rather than falling back to defaults)."""
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.security_policy import SecurityPolicyVersion

    db = SessionLocal()
    try:
        row = db.execute(select(SecurityPolicyVersion)
                         .order_by(SecurityPolicyVersion.id.desc()).limit(1)).scalars().first()
        if row is None:
            return 0, {}
        payload = json.loads(row.payload) if row.payload else {}
        return row.id, validate({k: v for k, v in payload.items() if k in REGISTRY})
    finally:
        db.close()


def current(force: bool = False) -> Snapshot:
    """Hot-path read: never touches SQL more often than REFRESH_SECONDS."""
    global _snapshot, _fetched_at
    with _lock:
        now = time.monotonic()
        fresh = _snapshot is not None and (now - _fetched_at) < REFRESH_SECONDS
        if fresh and not force:
            return _snapshot
        try:
            version, overrides = _read_latest()
        except Exception:
            if force:
                raise
            if _snapshot is None:
                _snapshot = Snapshot(version=0)
            _fetched_at = time.monotonic() + RETRY_AFTER_FAILURE - REFRESH_SECONDS
        else:
            _snapshot = Snapshot(version=version, overrides=overrides)
            _fetched_at = time.monotonic()
        return _snapshot


def value(policy_id: str, snapshot: Optional[Snapshot] = None) -> int:
    return (snapshot or current()).value(policy_id)


def for_request(request) -> Snapshot:
    """The snapshot Throttle pinned for this request, or a fresh read.

    Falls back when there is no middleware-provided state (background jobs,
    unit tests calling a handler directly) or when the value is not a
    Snapshot at all (a mock in a test double) — never trust a foreign object
    to behave like a frozen policy version.
    """
    state = getattr(request, "state", None)
    snapshot = getattr(state, "policy_snapshot", None) if state is not None else None
    return snapshot if isinstance(snapshot, Snapshot) else current()


def invalidate_cache() -> None:
    """Called by the writing process so its next read sees its own change."""
    global _fetched_at
    with _lock:
        _fetched_at = 0.0


def describe(policy_id: str, snapshot: Optional[Snapshot] = None) -> dict:
    """One UI row: effective value + where it came from + its semantics."""
    p = get(policy_id)
    snap = snapshot or current()
    if p.id in snap.overrides:
        value_, source = snap.overrides[p.id], "管理員覆寫"
    elif p.setting and getattr(settings, p.setting, None) != p.default:
        value_, source = getattr(settings, p.setting), "部署設定"
    else:
        value_, source = snap.value(p.id), "程式預設"
    window = p.window
    if p.window_seconds is not None:
        actual = snap.window(p.id, p.window_seconds)
        if actual != p.window_seconds:
            window = f"{window}（目前視窗 {actual} 秒）"
    return {
        "id": p.id,
        "label": p.label,
        "group": p.group,
        "value": value_,
        "source": source,
        "code_default": p.default,
        "deployment_value": deployment_value(p.id),
        "unit": p.unit,
        "subject": p.subject,
        "window": window,
        "window_seconds": snap.window(p.id, p.window_seconds) if p.window_seconds is not None else None,
        "window_editable": p.id in WINDOW_IDS,
        "action": p.action,
        "editable": p.editable,
        "allow_zero": p.allow_zero,
        "min": p.min_value if p.allow_zero else max(p.min_value, 1),
        "max": p.max_value,
        "route": p.route,
        "method": p.method,
        "depends": p.depends,
        "note": p.note,
    }


def effective_map(snapshot: Optional[Snapshot] = None) -> dict[str, int]:
    snap = snapshot or current()
    return {pid: snap.value(pid) for pid in REGISTRY}


def public_snapshot(snapshot: Optional[Snapshot] = None) -> dict:
    """The admin listing: every policy grouped, with provenance."""
    snap = snapshot or current()
    groups = []
    for name in GROUPS:
        items = [describe(p.id, snap) for p in POLICIES if p.group == name]
        groups.append({"name": name, "items": items})
    return {"version": snap.version, "groups": groups}


# ------------------------------------------------------------------ writes

class StaleVersion(Exception):
    """Another tab committed first: the caller must re-read and retry."""

    def __init__(self, current_version: int):
        super().__init__(f"版本衝突（目前 v{current_version}）")
        self.current_version = current_version


def _insert(payload: dict, *, diff: dict, actor, actor_id, reason, expected: int, action: str) -> int:
    """Insert version `expected + 1`.

    The primary key IS the version, so a stale tab gets an IntegrityError
    instead of silently overwriting a newer setting — no extra lock needed.
    """
    from sqlalchemy.exc import IntegrityError
    from app.database import SessionLocal
    from app.models.security_policy import SecurityPolicyVersion

    db = SessionLocal()
    try:
        row = SecurityPolicyVersion(
            id=expected + 1,
            payload=json.dumps({k: int(v) for k, v in sorted(payload.items())}),
            diff=json.dumps(diff, ensure_ascii=False, sort_keys=True),
            reason=(reason or "")[:255] or None,
            actor=actor,
            actor_id=actor_id,
            parent_version=expected if expected else None,
            action=action,
        )
        db.add(row)
        db.commit()
        return row.id
    except IntegrityError as exc:
        db.rollback()
        latest = _read_latest()[0]
        raise StaleVersion(latest) from exc
    finally:
        db.close()


def _diff_for(before: Snapshot, after_payload: dict) -> dict:
    """Effective-value changes only (a no-op edit records nothing)."""
    diff = {}
    after = Snapshot(before.version, after_payload)
    for pid in REGISTRY:
        b = before.value(pid)
        a = after.value(pid)
        if a != b:
            diff[pid] = {"before": b, "after": a, "label": REGISTRY[pid].label}
    return diff


def commit(changes: dict[str, int], *, reset_ids=(), actor=None, actor_id=None, reason="",
           expected_version: int) -> dict:
    """Apply a validated group of edits as ONE new version."""
    snap = current(force=True)
    if snap.version != expected_version:
        raise StaleVersion(snap.version)
    clean = {pid: _valid(get(pid), value) for pid, value in changes.items()}
    for pid in clean:
        if not get(pid).editable:
            raise PolicyError(f"{get(pid).label}為唯讀")
    payload = dict(snap.overrides)
    if clean.keys() & set(reset_ids):
        raise PolicyError("不能同時修改和重設同一項門檻")
    for pid in reset_ids:
        get(pid)
        payload.pop(pid, None)
    payload.update(clean)
    validate(payload)
    diff = _diff_for(snap, payload)
    if payload == snap.overrides or (not reset_ids and not diff):
        return {"version": snap.version, "changed": {}, "noop": True}
    version = _insert(payload, diff=diff, actor=actor, actor_id=actor_id,
                      reason=reason, expected=snap.version, action="update")
    invalidate_cache()
    return {"version": version, "changed": diff}


def reset_to_defaults(policy_ids: list[str], *, actor=None, actor_id=None, reason="",
                      expected_version: int) -> dict:
    """Drop admin overrides for these ids -> deployment setting -> code default.

    'Recover default' deliberately does NOT delete the version history; it
    appends a version that simply carries fewer overrides.
    """
    snap = current(force=True)
    if snap.version != expected_version:
        raise StaleVersion(snap.version)
    for pid in policy_ids:
        get(pid)  # unknown id -> PolicyError
    payload = {k: v for k, v in snap.overrides.items() if k not in set(policy_ids)}
    diff = _diff_for(snap, payload)
    if not diff:
        return {"version": snap.version, "changed": {}, "noop": True}
    version = _insert(payload, diff=diff, actor=actor, actor_id=actor_id,
                      reason=reason, expected=snap.version, action="reset")
    invalidate_cache()
    return {"version": version, "changed": diff, "reset": sorted(policy_ids)}


def _rollback_payload(version: int, expected_version: int):
    from app.database import SessionLocal
    from app.models.security_policy import SecurityPolicyVersion

    snap = current(force=True)
    if snap.version != expected_version:
        raise StaleVersion(snap.version)
    if version == 0:
        payload: dict[str, int] = {}          # "before any admin change"
    else:
        db = SessionLocal()
        try:
            target = db.get(SecurityPolicyVersion, version)
            if target is None:
                raise PolicyError(f"找不到版本 v{version}")
            payload = {k: int(v) for k, v in json.loads(target.payload or "{}").items()
                       if k in REGISTRY}
        finally:
            db.close()
    return snap, validate(payload)


def preview_rollback(version: int, expected_version: int) -> dict:
    snap, payload = _rollback_payload(version, expected_version)
    return {"version": snap.version, "changed": _diff_for(snap, payload)}


def rollback_to(version: int, *, actor=None, actor_id=None, reason="",
                expected_version: int) -> dict:
    """Re-publish an older payload as a new version."""
    snap, payload = _rollback_payload(version, expected_version)
    diff = _diff_for(snap, payload)
    new_version = _insert(payload, diff=diff, actor=actor, actor_id=actor_id,
                          reason=reason, expected=snap.version, action="rollback")
    invalidate_cache()
    return {"version": new_version, "rolled_back_to": version, "changed": diff}


def history(limit: int = 50) -> list[dict]:
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.security_policy import SecurityPolicyVersion

    out = []
    db = SessionLocal()
    try:
        rows = db.execute(select(SecurityPolicyVersion)
                          .order_by(SecurityPolicyVersion.id.desc()).limit(limit)).scalars().all()
        for row in rows:
            try:
                diff = json.loads(row.diff or "{}")
            except ValueError:
                diff = {}
            out.append({
                "version": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "actor": row.actor,
                "reason": row.reason,
                "action": row.action,
                "changed": diff,
            })
    finally:
        db.close()
    return out
