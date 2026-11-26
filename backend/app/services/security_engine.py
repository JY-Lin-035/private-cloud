"""Security event engine: log, violation scoring, auto ip/user controls, email alerts.

All entry points are best-effort: failures here must never break user requests.
"""
import asyncio
import ipaddress
import json
import threading
from datetime import datetime, timedelta

from redis import Redis

from app.config import settings
from app.services import security_policy
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
    "/api/accounts/resetPW", "/api/share/verifyPassword",
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
# Admin-facing wording for a rejection whose *own* request carried no verified
# identity. ipActors (accounts recently seen from an IP) stay a separate
# signal — they must never be back-filled as this request's actor.
UNVERIFIED_ACTOR = "本請求未驗證帳號"


def format_actor(username=None, user_id=None):
    """Display string for the account that triggered THIS request."""
    if username:
        return str(username)
    if user_id:
        return f"#{user_id}"
    return UNVERIFIED_ACTOR

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


def get_client_ip(scope_headers, remote_addr=None):
    """Return the trusted client IP.

    Trust chain:
      1. Cloudflare's `CF-Connecting-IP` (the edge overwrites it; our only
         public ingress is the tunnel).
      2. `X-Real-IP`, but only when TRUST_REAL_IP is enabled AND the socket
         peer is a configured trusted proxy (non-Cloudflare deployments).
    `X-Forwarded-For` is deliberately NOT used: proxies append the client's
    own value at the left, so it is spoofable (framing other users,
    bypassing per-IP limits).
    """
    cf = scope_headers.get("cf-connecting-ip")
    if cf:
        return cf.split(",")[0].strip() or None
    if settings.TRUST_REAL_IP and remote_addr and remote_addr in settings.trusted_proxy_ips:
        real = scope_headers.get("x-real-ip")
        if real:
            return real.split(",")[0].strip() or None
    return None


# ---------------------------------------------------------------- ip matching (R20b)

def normalize_ip(ip):
    """Canonical text form of a bare IP (compressed lowercase), or the input
    stripped if unparseable (legacy rows / non-IP junk must keep working as
    literal exact-match keys, never crash)."""
    if not ip:
        return None
    try:
        return ipaddress.ip_address(ip.strip()).compressed
    except ValueError:
        return ip.strip()


def compile_rule_matcher(raw_ip):
    """Precompiled matcher stored in the rules cache so the per-request path
    never parses rule text. Bare IP -> exact (after normalization);
    CIDR -> network containment. v4 rules only match v4 clients and vice
    versa (ipaddress 'in' already enforces family). Returns None when the
    rule has no ip subject."""
    if not raw_ip:
        return None
    s = raw_ip.strip()
    try:
        # ip_network() accepts bare addresses too (becomes /32 or /128), and
        # only networks implement __contains__ -- normalize everything to a
        # network so the hot path is a single family-checked membership test.
        return ipaddress.ip_network(s, strict=False)
    except ValueError:
        return ("literal", s)


def ip_matches(matcher, norm_ip, raw_ip):
    if matcher is None:
        return False
    if isinstance(matcher, tuple):          # unparseable rule text: literal
        return raw_ip == matcher[1] or norm_ip == matcher[1]
    try:
        return ipaddress.ip_address(norm_ip or raw_ip) in matcher
    except ValueError:
        return False


def _rule_matcher(r):
    """Matcher access with lazy compile: rules built outside _active_rules
    (tests, ad-hoc dicts) carry no '_m'; compile once and memoize in place."""
    m = r.get("_m")
    if m is None and r.get("ip"):
        m = compile_rule_matcher(r["ip"])
        try:
            r["_m"] = m
        except Exception:
            pass
    return m


def _incr_ttl(r, key, amount, ttl):
    pipe = r.pipeline()
    pipe.incrby(key, amount)
    pipe.expire(key, ttl)
    return pipe.execute()[0]


def _incr_windowed(r, key, amount, window):
    """Increment a counter and (re)arm its TTL, keeping the window length the
    bucket was OPENED with.

    An admin raising or lowering a window must not retroactively stretch or
    shrink buckets that already exist — those expire under the old rule and
    only then pick the new window up. The length is pinned in a side key.
    """
    wkey = f"{key}:w"
    pipe = r.pipeline()
    pipe.incrby(key, amount)
    pipe.get(wkey)
    n, pinned = pipe.execute()
    try:
        window = int(pinned) if pinned is not None else int(window)
    except (TypeError, ValueError):
        window = int(window)
    try:
        if pinned is None:
            r.set(wkey, str(window), nx=True, ex=window * 2)
        else:
            r.expire(wkey, window * 2)
    except Exception:
        pass
    r.expire(key, window)
    return n


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


def _alert(kind, ip, actor, target, detail, action_taken="", actor_display=None, extra=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[MeowCloud 資安警報] {kind} — {mask_ip(ip)}"
    lines = [
        f"時間: {now} (UTC+8)",
        f"事件: {kind}",
        f"來源IP: {mask_ip(ip)}",
        f"觸發帳號: {actor_display if actor_display is not None else (actor or UNVERIFIED_ACTOR)}",
    ]
    for label, value in (extra or {}).items():
        if value not in (None, ""):
            lines.append(f"{label}: {value}")
    lines += [
        f"目標: {target or '-'}",
        f"明細: {detail}",
        f"動作: {action_taken or '僅記錄'}",
    ]
    _send_alert(subject, "\n".join(lines))


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
                    "_m": compile_rule_matcher(r.ip),
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


def match_rules(ip, user_id, is_upload, is_download, is_share, is_stream=False, token=None):
    blocked, delay, up_kbps, dn_kbps, _ = match_rules_detail(
        ip, user_id, is_upload, is_download, is_share, is_stream, token)
    return blocked, delay, up_kbps, dn_kbps


def match_rules_detail(ip, user_id, is_upload, is_download, is_share, is_stream=False, token=None):
    """Return (block, delay_ms, upload_kbps, download_kbps, blocking_rule_ids).

    `blocking_rule_ids` is only meaningful when block is True; the throttle
    layer records it so admins can see WHICH rule produced a 429.

    `token` is the share link the request actually targets. An `ip_token` rule
    is scoped to ONE link on that address: without it, blocking one shared
    folder silently blocked every other link leaving from the same IP. When
    the link cannot be determined (unparseable/oversized body) the rule still
    applies — punishment stays at least as strict as before, never looser.

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
    blockers = []
    nip = normalize_ip(ip)

    def _subject_hit(r):
        st = r["subject_type"]
        if st == "ip":
            return bool(ip) and ip_matches(_rule_matcher(r), nip, ip)
        if st == "ip_token":
            if not (ip and is_share) or not ip_matches(_rule_matcher(r), nip, ip):
                return False
            return token is None or (r.get("token") or "") == token
        return st == "user" and bool(user_id) and r["user_id"] == user_id

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
                blockers.append(f"rule#{r.get('id')}(stream)")
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
                blockers.append(f"rule#{r.get('id')}(full)")
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
                blockers.append(f"rule#{r.get('id')}(transfer/{r.get('direction')})")
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
    return blocked, delay, up_kbps, dn_kbps, blockers


def _ensure_auto_rule(r, subject, action, scope, direction, hours, snapshot=None):
    """Create/refresh one auto rule. subject: dict of identifying fields.

    Slow-lane parameters come from the policy registry, so an admin changing
    the default delay/bandwidth changes what NEW auto rules look like without
    rewriting rules that already exist.
    """
    from sqlalchemy import select, delete as sa_delete
    from app.database import SessionLocal
    from app.models.ip_control import IpControl

    snap = snapshot or security_policy.current()
    up_delay = snap.value("slow.upload_delay_ms")
    down_delay = snap.value("slow.download_delay_ms")
    up_kbps = snap.value("slow.upload_kbps")
    down_kbps = snap.value("slow.download_kbps")

    db = SessionLocal()
    try:
        # Merge key is (subject + DIRECTION) among AUTO rules.
        #
        # Direction has to be part of the key: an upload-volume escalation
        # ("up") and a download-volume one ("down") used to fight over the same
        # row, each rewriting the other's direction and silently flipping which
        # half of the traffic was punished.
        #
        # Scope is deliberately NOT part of it: the punishment ladder upgrades
        # one row in place (transfer/slow -> full/block). Excluding scope keeps
        # "a permanent block is terminal" true regardless of which stage asks,
        # and keeps one IP at one auto rule per direction.
        #
        # AUTO never merges into a manual rule — the admin's parameters win.
        q = select(IpControl).where(IpControl.auto.is_(True),
                                    IpControl.direction == direction)
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
                    existing.delay_ms = up_delay
                    existing.upload_kbps = up_kbps
                if direction in ("down", "both"):
                    existing.delay_ms = max(existing.delay_ms or 0, down_delay)
                    existing.download_kbps = down_kbps
            db.commit()
            return bool(changed)
        subject_type = "user" if subject.get("user_id") is not None else ("ip_token" if subject.get("token") is not None else "ip")
        db.add(IpControl(
            subject_type=subject_type,
            ip=subject.get("ip"), token=subject.get("token"),
            user_id=subject.get("user_id"), username=subject.get("username"),
            action=action, scope=scope, direction=direction,
            delay_ms=up_delay if direction in ("up", "both") else down_delay,
            upload_kbps=up_kbps if direction in ("up", "both") else None,
            download_kbps=down_kbps if direction in ("down", "both") else None,
            reason="自動觸發（積分/流量閾值）", auto=True, expires_at=None if hours is None else expires_new,
        ))
        db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------- events

def record_event(kind, ip, actor=None, target=None, detail="",
                 actor_display=None, extra=None, score=True):
    """Sync entry. Safe to call from threadpool or asyncio.to_thread.

    `extra` is a dict of admin-only context (HTTP method, route id, rejection
    source, threshold, outcome). It is appended to the audit line and rendered
    in the alert e-mail; it never reaches the client.

    `score=False` records the event but does not feed the violation score —
    used for repeat rejections inside an already-counted window, so a burst
    costs one violation instead of N while every request stays auditable.
    """
    audit_detail = detail
    if extra:
        rendered = "；".join(f"{k}={v}" for k, v in extra.items() if v not in (None, ""))
        if rendered:
            audit_detail = f"{detail}｜{rendered}" if detail else rendered
    try:
        write_event(kind, ip, actor_display if actor_display is not None else actor,
                    target, audit_detail)
        weight = WEIGHTS.get(kind) if score else None
        if weight and ip:
            r = _client()
            snap = security_policy.current()
            is_auth = kind in AUTH_KINDS or (
                kind == "rate_limit" and any(str(target or "").startswith(p) for p in AUTH_ENDPOINTS))
            if is_auth:
                score_a = _incr_ttl(r, f"secScoreA:{ip}", weight, SCORE_TTL)
                if score_a >= snap.value("score.auth_block_threshold"):
                    _escalate_to_block(r, ip, actor, kind, score_a, audit_detail, target,
                                       actor_display=actor_display)
            else:
                score_n = _incr_ttl(r, f"secScore:{ip}", weight, SCORE_TTL)
                slow_at = snap.value("score.slow_threshold")
                stage = int(r.get(f"secStage:{ip}") or 0)
                if stage == 0 and score_n >= slow_at:
                    if _ensure_auto_rule(r, {"ip": ip}, "slow", "transfer", "both", 1, snapshot=snap):
                        r.setex(f"secStage:{ip}", STAGE_TTL, "1")
                        # The rule just became effective: without dropping the
                        # local cache the admin UI (and this worker) would keep
                        # serving the pre-slow decision for up to 60s.
                        invalidate_rules_cache()
                        _alert(kind, ip, actor, target, f"{audit_detail}｜積分 {score_n}",
                               "上傳/下載慢速 1 小時", actor_display=actor_display)
                elif stage == 1 and score_n >= snap.value("score.escalated_block_threshold"):
                    _escalate_to_block(r, ip, actor, kind, score_n, audit_detail, target,
                                       actor_display=actor_display)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("security_engine.record_event failed")


def _escalate_to_block(r, ip, actor, kind, score, detail, target=None, actor_display=None):
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
    _alert(kind, ip, actor, target, f"{detail}｜積分 {score}",
           f"全站 429 冷卻 {label}（第 {strikes} 次）{extra}", actor_display=actor_display)


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

# An auto slow/block rule lasts this many hours, so the "already escalated"
# claim marker lives exactly as long: one escalation per stage per hour,
# independent of where the threshold happens to sit.
AUTO_RULE_HOURS = 1


def transfer_stage(n, limit):
    """0 = within limits, 1 = slow lane, 2 = block.

    Deliberately a plain comparison instead of `n == limit + 1`: after an
    admin lowers a threshold mid-window the counter is already past it and the
    exact-crossing test would silently never fire again.
    """
    if n > 2 * limit:
        return 2
    if n > limit:
        return 1
    return 0


def claim_stage(r, marker_key, ttl):
    """Atomic once-per-window claim (SET NX). True only for the first caller,
    also across workers — so repeated hits never add a second violation."""
    try:
        return bool(r.set(marker_key, "1", nx=True, ex=max(int(ttl), 1)))
    except Exception:
        return True


def count_upload(user_id, ip, username=None, snapshot=None):
    """Account upload volume, counted at the CREATION boundary (see files.py).

    Called once per successfully created upload — not per tus HEAD/PATCH or
    per failed attempt — so a batch in progress is not miscounted as dozens of
    uploads. Request-level abuse is still covered by the endpoint limiter and
    the flood guard.
    """
    if not user_id:
        return
    try:
        r = _client()
        snap = snapshot or security_policy.current()
        key = f"xfer:up:u{user_id}"
        window = snap.value("volume.upload_window_seconds")
        n = _incr_windowed(r, key, 1, window)
        limit = snap.value("volume.uploads_per_hour_per_account")
        stage = transfer_stage(n, limit)
        if stage and claim_stage(r, f"{key}:s{stage}", AUTO_RULE_HOURS * 3600):
            action = "slow" if stage == 1 else "block"
            if _ensure_auto_rule(r, {"user_id": user_id, "username": username, "ip": None, "token": None},
                                 action, "transfer", "up", AUTO_RULE_HOURS, snapshot=snap):
                invalidate_rules_cache()
                _alert("upload_volume", None, username or f"#{user_id}", "上傳",
                       f"{n} 次/{window}s（閾值 {limit}）",
                       "上傳限流（慢速）" if action == "slow" else "上傳 block（1h）",
                       extra={"拒絕來源": "帳號上傳量", "規則範圍": "transfer/up"})
    except Exception:
        pass


def count_download(user_id, ip, token=None, username=None, snapshot=None):
    try:
        r = _client()
        snap = snapshot or security_policy.current()
        if user_id:
            key = f"xfer:dn:u{user_id}"
            window = snap.value("volume.download_window_seconds")
            n = _incr_windowed(r, key, 1, window)
            limit = snap.value("volume.downloads_per_hour_per_account")
            subject = {"user_id": user_id, "username": username}
        elif ip and token:
            key = f"xfer:dn:a{ip}:{token[:8]}"
            window = snap.value("volume.anon_share_download_window_seconds")
            n = _incr_windowed(r, key, 1, window)
            limit = snap.value("volume.anon_share_downloads_per_hour")
            subject = {"ip": ip, "token": token}
            try:
                hk = f"hotlinks:{normalize_ip(ip) or ip}"
                r.hset(hk, token[:8], token)
                r.expire(hk, 3600)
            except Exception:
                pass
        else:
            return
        stage = transfer_stage(n, limit)
        if stage and claim_stage(r, f"{key}:s{stage}", AUTO_RULE_HOURS * 3600):
            action = "slow" if stage == 1 else "block"
            if _ensure_auto_rule(r, subject, action, "transfer", "down", AUTO_RULE_HOURS, snapshot=snap):
                invalidate_rules_cache()
                who = username or f"#{user_id}" if user_id else f"{mask_ip(ip)}→連結#{token[:8] if token else ''}"
                _alert("download_volume", None if user_id else ip, who, "下載",
                       f"{n} 次/{window}s（閾值 {limit}）",
                       "下載限速" if action == "slow" else "下載 block（1h）",
                       extra={"拒絕來源": "帳號下載量" if user_id else "匿名分享下載量",
                              "規則範圍": "transfer/down"})
    except Exception:
        pass


def track_actor(ip, user_id):
    if not (ip and user_id):
        return
    try:
        r = _client()
        key = f"ipActors:{normalize_ip(ip)}"
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


def should_log_reject(kind, ip, target, window=300):
    """True only for the FIRST rejection logged per (kind, ip, route).

    A blocked IP retries hard; without this marker one incident would flood
    the audit log. Counters keep counting every rejected request — only the
    admin-facing record is de-duplicated.
    """
    try:
        r = _client()
        key = f"secLogged:{kind}:{normalize_ip(ip) or ip}:{target or '-'}"
        return bool(r.set(key, "1", nx=True, ex=max(int(window), 1)))
    except Exception:
        return True


def flood_exceeded(ip, actor_display=None, target=None, snapshot=None):
    try:
        r = _client()
        snap = snapshot or security_policy.current()
        limit = snap.value("global.flood_requests_per_ip")
        window = snap.value("global.flood_window_seconds")
        n = _incr_windowed(r, f"glb:{ip}", 1, window)
        # First rejection inside this window (SET NX marker) rather than
        # `n == limit + 1`: after a threshold is lowered mid-window the
        # counter is already past the new limit and the exact-crossing test
        # would never report again.
        if n > limit and should_log_reject("flood", ip, None, window):
            record_event("flood", ip, None, target,
                         f"超過全域 {limit} 次/小時（第 {n} 次）",
                         actor_display=actor_display,
                         extra={"拒絕來源": "全站 flood", "門檻": f"{limit}/{window}s"})
        return n > limit
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


def recent_ip_actors(ip, limit=20):
    """Accounts recently observed acting from `ip` (admin display only).

    This is correlation, NOT proof of who triggered a given request — keep it
    out of the attribution path (see UNVERIFIED_ACTOR).
    """
    if not ip:
        return []
    out = []
    try:
        r = _client()
        key = f"ipActors:{normalize_ip(ip)}"
        for uid, ts in (r.hgetall(key) or {}).items():
            uid = uid.decode() if isinstance(uid, bytes) else uid
            try:
                ts = int(ts)
            except (TypeError, ValueError):
                continue
            name = None
            try:
                raw = r.get(f"session_data:{uid}")
                if raw:
                    name = json.loads(raw.decode() if isinstance(raw, bytes) else raw).get("username")
            except Exception:
                name = None
            out.append({"user_id": int(uid), "username": name or f"#{uid}",
                        "last_seen": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")})
        out.sort(key=lambda x: x["last_seen"], reverse=True)
    except Exception:
        return []
    return out[:limit]


def record_event_async(kind, ip, actor=None, target=None, detail="",
                       actor_display=None, extra=None, score=True):
    """Fire-and-forget for async (middleware/handler) contexts."""
    asyncio.create_task(asyncio.to_thread(
        record_event, kind, ip, actor, target, detail, actor_display, extra, score))
