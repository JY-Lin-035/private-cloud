"""Security event engine: log, violation scoring, auto ip/user controls, email alerts.

All entry points are best-effort: failures here must never break user requests.
"""
import asyncio
import threading
from datetime import datetime, timedelta

from redis import Redis

from app.config import settings
from app.utils.security_log import write_event

WEIGHTS = {
    "rate_limit": 2,
    "flood": 2,
    "pw_fail": 1,
    "pw_lock": 5,
    "admin_probe": 3,
    "upload_reject": 2,
    "login_fail": 1,
    "quota_change": 0,
}
AUTH_KINDS = {"pw_lock", "admin_probe", "login_fail"}
# rate_limit events aimed at these endpoints are credential/abuse probing
# (throttling transfers would be a painless punishment), so they score in the
# auth pool which escalates straight to a full-site block.
AUTH_ENDPOINTS = (
    "/api/accounts/login", "/api/accounts/register", "/api/accounts/getCode",
    "/api/accounts/resetPW", "/api/accounts/verifyEmail", "/api/share/verifyPassword",
)
# Only kinds whose actor is the *authenticated* account may lead to account
# disabling; login_fail carries an attempted username and must never disable
# (attackers could get a victim's account killed by guessing its name).
DISABLE_ATTESTED_KINDS = {"admin_probe"}
# Escalation ladder: strike # -> block hours; None = permanent (expires_at NULL)
STRIKE_HOURS = (1, 3, 6, 12, 24, 72)
STAGE_TTL = 3 * 3600
SCORE_TTL = 3600
ALERT_COOLDOWN_S = 600

_lock = threading.Lock()
_redis = None
_rules_cache = {"ts": 0.0, "rules": []}


def _client():
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL)
    return _redis


def mask_ip(ip):
    if not ip:
        return "-"
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return (parts[0] + ":xx:xx:" + parts[-1]) if len(parts) > 2 else ip[:4] + "…"
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.xx.xx.{parts[3]}"
    return ip[:2] + "…"


def get_client_ip(scope_headers):
    """Return the trusted client IP.

    Only Cloudflare's `CF-Connecting-IP` is trusted (the edge overwrites it).
    `X-Forwarded-For` is deliberately NOT used: Cloudflare appends to any
    client-supplied value, and Uvicorn's proxy handling can be influenced by it
    (IP spoofing / framing other users / bypassing per-IP limits).
    """
    cf = scope_headers.get("cf-connecting-ip")
    if cf:
        return cf.split(",")[0].strip() or None
    return None


def _incr_ttl(r, key, amount, ttl):
    pipe = r.pipeline()
    pipe.incrby(key, amount)
    pipe.expire(key, ttl)
    return pipe.execute()[0]


# ---------------------------------------------------------------- alerts

def _send_alert(subject, body):
    if not settings.SECURITY_ALERT_ENABLED:
        return
    r = _client()
    if r.get("alert:cooldown"):
        r.incr("alert:pending")
        return
    r.setex("alert:cooldown", ALERT_COOLDOWN_S, "1")
    pending = int(r.get("alert:pending") or 0)
    if pending:
        body += f"\n（冷卻期間另有 {pending} 件事件）"
        r.delete("alert:pending")
    try:
        from app.tasks.email_tasks import send_security_alert_task
        send_security_alert_task.delay(subject, body)
    except Exception:
        pass


def _alert(kind, ip, actor, target, detail, action_taken=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[MeowCloud 資安警報] {kind} — {mask_ip(ip)}"
    body = (
        f"時間: {now} (UTC+8)\n"
        f"事件: {kind}\n"
        f"來源IP: {mask_ip(ip)}\n"
        f"關聯帳號: {actor or '匿名（無帳號）'}\n"
        f"目標: {target or '-'}\n"
        f"明細: {detail}\n"
        f"動作: {action_taken or '僅記錄'}"
    )
    _send_alert(subject, body)


# ---------------------------------------------------------------- controls

def _active_rules():
    import time as _t
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.ip_control import IpControl

    now = _t.time()
    with _lock:
        if now - _rules_cache["ts"] < 60:
            return _rules_cache["rules"]
    try:
        db = SessionLocal()
        try:
            rows = db.execute(select(IpControl)).scalars().all()
            cutoff = datetime.utcnow()
            rules = [
                {
                    "id": r.id, "subject_type": r.subject_type, "ip": r.ip, "token": r.token,
                    "user_id": r.user_id, "action": r.action, "scope": r.scope,
                    "direction": r.direction, "delay_ms": r.delay_ms or 0,
                    "upload_kbps": r.upload_kbps, "download_kbps": r.download_kbps,
                    "auto": bool(r.auto),
                }
                for r in rows if r.expires_at is None or r.expires_at > cutoff
            ]
            rules.sort(key=lambda x: (x["auto"], -x["id"]))  # manual first, newest first
        finally:
            db.close()
    except Exception:
        rules = _rules_cache["rules"]
    with _lock:
        _rules_cache["ts"] = now
        _rules_cache["rules"] = rules
    return rules


def invalidate_rules_cache():
    with _lock:
        _rules_cache["ts"] = 0.0


def match_rules(ip, user_id, is_upload, is_download, is_share, is_stream=False):
    """Return (block, delay_ms, upload_kbps, download_kbps) merged from active rules.

    Stream precedence: dedicated `stream`-scope rules own playback traffic
    (download_kbps column carries the stream cap); while any stream rule matches,
    transfer/down rules no longer pace streams (single pacer, independent knob).
    Without stream rules, transfer/down falls back and covers streams too, so
    auto escalations never leave a streaming backdoor.
    """
    blocked = False
    delay = 0
    up_kbps = None
    dn_kbps = None

    def _subject_hit(r):
        return (
            (r["subject_type"] == "ip" and ip and r["ip"] == ip)
            or (r["subject_type"] == "ip_token" and ip and r["ip"] == ip and is_share)
            or (r["subject_type"] == "user" and user_id and r["user_id"] == user_id)
        )

    rules = _active_rules()
    stream_governed = is_stream and any(
        _subject_hit(r) and r["scope"] == "stream" for r in rules)

    for r in rules:
        if not _subject_hit(r):
            continue
        if r["scope"] == "stream":
            if not is_stream:
                continue
            if r["action"] == "block":
                blocked = True
                continue
            delay = max(delay, r["delay_ms"])
            v = r["download_kbps"]
            if v:
                dn_kbps = v if dn_kbps is None else min(dn_kbps, v)
            continue
        is_transfer = (is_upload and r["direction"] in ("up", "both")) or \
                      (is_download and r["direction"] in ("down", "both"))
        if is_stream and stream_governed and r["scope"] == "transfer" and not is_upload:
            continue  # stream handled by dedicated rules; ignore transfer down/both pacing
        if r["scope"] == "full":
            if r["action"] == "block":
                blocked = True
                continue
            delay = max(delay, r["delay_ms"])
            if is_transfer:
                if is_upload:
                    up_kbps = r["upload_kbps"] if up_kbps is None else min(filter(None, [up_kbps, r["upload_kbps"]]) or [up_kbps])
                if is_download:
                    dn_kbps = r["download_kbps"] if dn_kbps is None else min(filter(None, [dn_kbps, r["download_kbps"]]) or [dn_kbps])
        else:  # scope transfer
            if not is_transfer:
                continue
            if r["action"] == "block":
                blocked = True
                continue
            delay = max(delay, r["delay_ms"])
            if is_upload:
                v = r["upload_kbps"]
                if v:
                    up_kbps = v if up_kbps is None else min(up_kbps, v)
            if is_download:
                v = r["download_kbps"]
                if v:
                    dn_kbps = v if dn_kbps is None else min(dn_kbps, v)
    return blocked, delay, up_kbps, dn_kbps


def _ensure_auto_rule(r, subject, action, scope, direction, hours):
    """Create/refresh one auto rule. subject: dict of identifying fields."""
    from sqlalchemy import select, delete as sa_delete
    from app.database import SessionLocal
    from app.models.ip_control import IpControl

    db = SessionLocal()
    try:
        q = select(IpControl).where(IpControl.auto.is_(True))
        if subject.get("user_id") is not None:
            q = q.where(IpControl.user_id == subject["user_id"], IpControl.token.is_(None))
        elif subject.get("token") is not None:
            q = q.where(IpControl.ip == subject.get("ip"), IpControl.token == subject["token"])
        else:
            q = q.where(IpControl.ip == subject["ip"], IpControl.token.is_(None))
        existing = db.execute(q).scalars().first()
        expires_new = None if hours is None else datetime.utcnow() + timedelta(hours=hours)
        if existing:
            if existing.expires_at is None:
                return False  # permanent rules are terminal; only admins lift them
            if existing.action == "block" and action == "slow":
                return False  # never downgrade an active block to slow
            changed = (
                existing.action != action
                or expires_new is None
                or (existing.expires_at is not None and existing.expires_at < expires_new)
            )
            existing.action = action
            existing.scope = scope
            existing.direction = direction
            existing.expires_at = expires_new
            if action == "slow":
                if direction in ("up", "both"):
                    existing.delay_ms = settings.SEC_DEFAULT_UPLOAD_DELAY_MS
                    existing.upload_kbps = settings.SEC_DEFAULT_UPLOAD_KBPS
                if direction in ("down", "both"):
                    existing.delay_ms = max(existing.delay_ms or 0, settings.SEC_DEFAULT_DOWNLOAD_DELAY_MS)
                    existing.download_kbps = settings.SEC_DEFAULT_DOWNLOAD_KBPS
            db.commit()
            return bool(changed)
        subject_type = "user" if subject.get("user_id") is not None else ("ip_token" if subject.get("token") is not None else "ip")
        db.add(IpControl(
            subject_type=subject_type,
            ip=subject.get("ip"), token=subject.get("token"),
            user_id=subject.get("user_id"), username=subject.get("username"),
            action=action, scope=scope, direction=direction,
            delay_ms=settings.SEC_DEFAULT_UPLOAD_DELAY_MS if direction in ("up", "both") else settings.SEC_DEFAULT_DOWNLOAD_DELAY_MS,
            upload_kbps=settings.SEC_DEFAULT_UPLOAD_KBPS if direction in ("up", "both") else None,
            download_kbps=settings.SEC_DEFAULT_DOWNLOAD_KBPS if direction in ("down", "both") else None,
            reason="自動觸發（積分/流量閾值）", auto=True, expires_at=None if hours is None else expires_new,
        ))
        db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------- events

def record_event(kind, ip, actor=None, target=None, detail=""):
    """Sync entry. Safe to call from threadpool or asyncio.to_thread."""
    try:
        write_event(kind, ip, actor, target, detail)
        weight = WEIGHTS.get(kind)
        if weight and ip:
            r = _client()
            is_auth = kind in AUTH_KINDS or (
                kind == "rate_limit" and any(str(target or "").startswith(p) for p in AUTH_ENDPOINTS))
            if is_auth:
                score_a = _incr_ttl(r, f"secScoreA:{ip}", weight, SCORE_TTL)
                if score_a >= settings.SEC_SCORE_BLOCK_THRESHOLD:
                    _escalate_to_block(r, ip, actor, kind, score_a, detail)
            else:
                score = _incr_ttl(r, f"secScore:{ip}", weight, SCORE_TTL)
                stage = int(r.get(f"secStage:{ip}") or 0)
                if stage == 0 and score >= settings.SEC_SCORE_SLOW_THRESHOLD:
                    if _ensure_auto_rule(r, {"ip": ip}, "slow", "transfer", "both", 1):
                        r.setex(f"secStage:{ip}", STAGE_TTL, "1")
                        _alert(kind, ip, actor, target, f"{detail}｜積分 {score}", "上傳/下載慢速 1 小時")
                elif stage == 1 and score >= 2 * settings.SEC_SCORE_SLOW_THRESHOLD:
                    _escalate_to_block(r, ip, actor, kind, score, detail)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("security_engine.record_event failed")


def _escalate_to_block(r, ip, actor, kind, score, detail):
    strikes = r.incr(f"secStrikes:{ip}")
    r.expire(f"secStrikes:{ip}", 7 * 24 * 3600)
    # One escalation per completed violation episode: clear both score buckets
    # so the remaining events of the same burst cannot march up the ladder twice.
    r.delete(f"secScoreA:{ip}")
    r.delete(f"secScore:{ip}")
    hours = STRIKE_HOURS[strikes - 1] if strikes <= len(STRIKE_HOURS) else None
    changed = _ensure_auto_rule(r, {"ip": ip}, "block", "full", "both", hours)
    if not changed:
        return  # already at the same-or-harsher punishment — no duplicate alerts
    r.setex(f"secStage:{ip}", STAGE_TTL, "2")
    invalidate_rules_cache()
    extra = ""
    if hours is None and kind in DISABLE_ATTESTED_KINDS and actor:
        extra = _disable_account(actor)
    label = "永久" if hours is None else f"{hours} 小時"
    _alert(kind, ip, actor, "", f"{detail}｜積分 {score}",
           f"全站 429 冷卻 {label}（第 {strikes} 次）{extra}")


def _disable_account(username):
    """Terminal sanction for an authenticated account that kept abusing the
    platform (e.g. probing admin endpoints). Disables it and kills sessions."""
    try:
        from sqlalchemy import select
        from app.database import SessionLocal
        from app.models.account import Account
        db = SessionLocal()
        try:
            acct = db.execute(select(Account).where(Account.name == username)).scalars().first()
            if not acct or not acct.enable:
                return ""
            acct.enable = False
            db.commit()
            uid = acct.id
        finally:
            db.close()
        r = _client()
        r.delete(f"session:{uid}")
        r.delete(f"session_data:{uid}")
        try:
            from app.services import collab_events
            collab_events.revoke_user(uid, "account disabled")
        except Exception:
            pass
        write_event("account_disabled", None, username, None, "累積違規達頂端處置")
        invalidate_rules_cache()
        return f"，並停用帳號 {username}"
    except Exception:
        return ""


def record_admin(kind, ip, actor, target, detail=""):
    try:
        write_event(kind, ip, actor, target, detail)
    except Exception:
        pass


# ---------------------------------------------------------------- transfer counters

def count_upload(user_id, ip, username=None):
    if not user_id:
        return
    try:
        r = _client()
        n = _incr_ttl(r, f"xfer:up:u{user_id}", 1, 3600)
        limit = settings.SEC_UPLOAD_HOURLY_LIMIT
        if n == limit + 1 or n == 2 * limit + 1:
            action = "slow" if n == limit + 1 else "block"
            if _ensure_auto_rule(r, {"user_id": user_id, "username": username, "ip": None, "token": None},
                                 action, "transfer", "up", 1):
                invalidate_rules_cache()
                _alert("upload_volume", None, username or f"#{user_id}", "上傳", f"{n} 次/小時",
                       "上傳限流（慢速）" if action == "slow" else "上傳 block（1h）")
    except Exception:
        pass


def count_download(user_id, ip, token=None, username=None):
    try:
        r = _client()
        if user_id:
            n = _incr_ttl(r, f"xfer:dn:u{user_id}", 1, 3600)
            limit = settings.SEC_DOWNLOAD_HOURLY_LIMIT
            subject = {"user_id": user_id, "username": username}
        elif ip and token:
            n = _incr_ttl(r, f"xfer:dn:a{ip}:{token[:8]}", 1, 3600)
            limit = settings.SEC_ANON_DOWNLOAD_HOURLY_LIMIT
            subject = {"ip": ip, "token": token}
            try:
                hk = f"hotlinks:{ip}"
                r.hset(hk, token[:8], token)
                r.expire(hk, 3600)
            except Exception:
                pass
        else:
            return
        if n == limit + 1 or n == 2 * limit + 1:
            action = "slow" if n == limit + 1 else "block"
            if _ensure_auto_rule(r, subject, action, "transfer", "down", 1):
                invalidate_rules_cache()
                who = username or f"#{user_id}" if user_id else f"{mask_ip(ip)}→連結#{token[:8] if token else ''}"
                _alert("download_volume", None if user_id else ip, who, "下載",
                       f"{n} 次/小時（閾值 {limit}）",
                       "下載限速" if action == "slow" else "下載 block（1h）")
    except Exception:
        pass


def track_actor(ip, user_id):
    if not (ip and user_id):
        return
    try:
        r = _client()
        key = f"ipActors:{ip}"
        r.hset(key, str(user_id), str(int(datetime.now().timestamp())))
        r.expire(key, 3600)
    except Exception:
        pass


def clear_pw_failures(token):
    if not token:
        return
    try:
        r = _client()
        for k in r.scan_iter(match=f"sharePwFail:{token}:*"):
            r.delete(k)
    except Exception:
        pass


def flood_exceeded(ip):
    try:
        r = _client()
        n = _incr_ttl(r, f"glb:{ip}", 1, 3600)
        if n == settings.SEC_GLOBAL_HOURLY_LIMIT + 1:
            record_event("flood", ip, None, None, f"超過全域 {settings.SEC_GLOBAL_HOURLY_LIMIT} 次/小時")
        return n > settings.SEC_GLOBAL_HOURLY_LIMIT
    except Exception:
        return False


def get_ip_scores(limit=10):
    """Top offending IPs with masked display for the dashboard."""
    out = []
    try:
        r = _client()
        pairs = []
        for key in r.scan_iter(match="secScore:*"):
            k = key.decode() if isinstance(key, bytes) else key
            ip = k.split(":", 1)[1]
            pairs.append((int(r.get(key) or 0), ip))
        for key in r.scan_iter(match="secScoreA:*"):
            k = key.decode() if isinstance(key, bytes) else key
            ip = k.split(":", 1)[1]
            pairs.append((int(r.get(key) or 0) + 999, ip))  # auth probes rank top
        pairs.sort(reverse=True)
        for score, ip in pairs[:limit]:
            out.append({"ip": ip, "masked": mask_ip(ip), "score": score if score < 999 else f"auth:{score-999}"})
    except Exception:
        pass
    return out


def record_event_async(kind, ip, actor=None, target=None, detail=""):
    """Fire-and-forget for async (middleware/handler) contexts."""
    asyncio.create_task(asyncio.to_thread(record_event, kind, ip, actor, target, detail))
