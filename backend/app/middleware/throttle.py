"""ASGI throttle middleware.

Responsibilities (per request, keyed by real client IP / session user):
  1. Global flood guard (SEC_GLOBAL_HOURLY_LIMIT per IP per hour -> 429).
  2. Apply active ip_control rules: block -> 429 (disguised as rate limit);
     slow -> per-request delay + bandwidth pacing on transfer endpoints.
  3. Transfer volume counters (upload starts / downloads, incl. anonymous share).
  4. Track ip -> account activity for the admin dashboard.

Never breaks the request pipeline: every hook is fail-open.
"""
import asyncio
import json
import time
from urllib.parse import parse_qs

from app.config import settings
from app.services import security_engine as sec
from app.services import security_policy
from app.utils.session_auth import resolve_session_identity

UPLOAD_PREFIXES = ('/api/files/tus', '/api/files/uploadFile')
DOWNLOAD_PREFIXES = (
    '/api/files/download', '/api/files/downloadBulk', '/api/folders/download',
    '/api/share/downloadFile', '/api/share/downloadFolder', '/api/share/downloadItems',
    '/api/files/stream', '/api/files/raw',
)
STREAM_PREFIXES = ('/api/files/stream',)
NO_COUNT_PREFIXES = ('/api/files/raw',)
SHARE_PREFIX = '/api/share/'
# Some share endpoints carry the link in a query string, others in a JSON body.
# ip_token rules and anonymous download accounting must treat both the same
# way, otherwise a body-based route escapes the very restriction aimed at it.
SHARE_JSON_LINK_PATHS = ('/api/share/status', '/api/share/verifyPassword', '/api/share/downloadItems')
_MAX_JSON_SNIFF = 256 * 1024


class _Pacer:
    __slots__ = ("rate", "start", "total")

    def __init__(self, rate_bps):
        self.rate = max(int(rate_bps), 1024)
        self.start = None
        self.total = 0

    async def consume(self, n):
        now = time.monotonic()
        if self.start is None:
            self.start = now
        self.total += n
        delay = self.total / self.rate - (now - self.start)
        if delay > 0:
            await asyncio.sleep(min(delay, 10))


class ThrottleMiddleware:
    def __init__(self, app):
        self.app = app

    @staticmethod
    def _json_429(origin):
        payload = json.dumps({"detail": "請求過多，請稍後再試"}).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode()),
        ]
        # Only echo origins we actually trust (same list as CORS/OriginGuard);
        # reflecting an arbitrary Origin with credentials is an info oracle.
        if origin and origin in settings.allowed_origins:
            headers.append(("access-control-allow-origin".encode(), origin.encode()))
            headers.append(("access-control-allow-credentials".encode(), b"true"))
        return headers, payload

    async def _share_link(self, scope, headers, receive):
        """Resolve which share link a request targets -> (token, receive).

        `None` means "could not tell" (unknown link): ip_token rules then apply
        as before rather than silently not matching, so tightening a scope can
        never loosen protection. When the link had to be read out of a JSON
        body, the body is replayed verbatim for the application.
        """
        path = scope.get("path", "")
        if not path.startswith(SHARE_PREFIX):
            return None, receive
        qs = parse_qs(scope.get("query_string", b"").decode(errors="ignore"))
        token = (qs.get("link") or [""])[0].strip()
        if token:
            return token, receive
        if scope.get("method") not in ("POST", "PUT", "PATCH") or path not in SHARE_JSON_LINK_PATHS:
            return None, receive
        try:
            length = int(headers.get("content-length") or -1)
        except ValueError:
            length = -1
        if "json" not in (headers.get("content-type") or "") or not 0 <= length <= _MAX_JSON_SNIFF:
            return None, receive

        chunks = []
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        played = {"done": False}

        async def replay():
            if not played["done"]:
                played["done"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        try:
            data = json.loads(body.decode("utf-8", errors="ignore"))
        except Exception:
            data = None
        link = data.get("link") if isinstance(data, dict) else None
        return (str(link).strip() or None), replay

    async def _record_rule_block(self, ip, method, path, actor_display, blockers):
        """Audit an active-rule rejection. Log-only (no scoring): the rule that
        blocked the request is already the punishment, and a blocked IP retries
        hard, so repeats are collapsed to one line per route per 5 minutes."""
        try:
            fresh = await asyncio.to_thread(sec.should_log_reject, "rule_block", ip, path, 300)
            if not fresh:
                return
            await asyncio.to_thread(
                sec.record_event, "rule_block", ip, None, path,
                "生效規則拒絕",
                actor_display=actor_display,
                extra={"HTTP方法": method, "拒絕來源": "規則封鎖",
                       "規則範圍": "、".join(blockers) if blockers else "-",
                       "處分": "HTTP 429"})
        except Exception:
            pass

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            headers = {}
            for k, v in scope.get("headers", []):
                try:
                    headers[k.decode().lower()] = v.decode(errors="ignore")
                except Exception:
                    pass
            _remote = scope.get("client")[0] if scope.get("client") else None
            ip = sec.get_client_ip(headers, _remote) or (_remote or "")
            path = scope.get("path", "")
            # A user id is only trusted after the cookie value is verified
            # against Redis; an unauthenticated caller cannot frame another
            # account by sending a forged `session=42|...` prefix. The same
            # verified identity is stashed for inner layers (audit attribution
            # only — it never authorises anything and never renews the
            # session), so public routes that skip SessionMiddleware can still
            # say whose cookie tripped a rejection.
            identity = None
            try:
                identity = await asyncio.to_thread(
                    resolve_session_identity, sec._client(), headers.get("cookie"))
            except Exception:
                identity = None
            uid = identity["user_id"] if identity else None
            # One policy version per request: flood, endpoint and volume
            # decisions made inside this request all read this same snapshot.
            snapshot = security_policy.current()
            state = scope.setdefault("state", {})
            state["policy_snapshot"] = snapshot
            if identity is not None:
                state["observed_identity"] = identity
            actor_display = (sec.format_actor(identity["username"], identity["user_id"])
                             if identity else sec.UNVERIFIED_ACTOR)
            is_upload = path.startswith(UPLOAD_PREFIXES)
            is_download = path.startswith(DOWNLOAD_PREFIXES)
            is_share = path.startswith(SHARE_PREFIX)
            is_stream = path.startswith(STREAM_PREFIXES)
            share_token, receive = await self._share_link(scope, headers, receive)
            if share_token:
                scope["state"]["share_token"] = share_token

            if ip and await asyncio.to_thread(sec.flood_exceeded, ip, actor_display, path, snapshot):
                rh, payload = self._json_429(headers.get("origin"))
                await send({"type": "http.response.start", "status": 429, "headers": rh})
                await send({"type": "http.response.body", "body": payload})
                return

            blocked, delay_ms, up_kbps, dn_kbps, blockers = await asyncio.to_thread(
                sec.match_rules_detail, ip, uid, is_upload, is_download, is_share, is_stream,
                share_token)
            if blocked:
                await self._record_rule_block(ip, scope.get("method", ""), path,
                                              actor_display, blockers)
                rh, payload = self._json_429(headers.get("origin"))
                await send({"type": "http.response.start", "status": 429, "headers": rh})
                await send({"type": "http.response.body", "body": payload})
                return
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000.0)

            if ip and uid:
                asyncio.create_task(asyncio.to_thread(sec.track_actor, ip, uid))

            if is_download and path not in NO_COUNT_PREFIXES and (not is_stream or not headers.get("range") or headers.get("range").strip().startswith("bytes=0-")):
                # stream/raw seeks are not new downloads; count playback sessions once
                if uid:
                    asyncio.create_task(asyncio.to_thread(sec.count_download, uid, ip, None))
                elif is_share and share_token:
                    asyncio.create_task(asyncio.to_thread(sec.count_download, None, ip, share_token))

            if is_upload and up_kbps:
                pacer = _Pacer(up_kbps * 1024)

                async def paced_receive(_r=receive, _p=pacer):
                    message = await _r()
                    if message.get("type") == "http.request" and message.get("body"):
                        await _p.consume(len(message["body"]))
                    return message

                receive = paced_receive

            if is_download and dn_kbps:
                pacer = _Pacer(dn_kbps * 1024)

                async def paced_send(message, _p=pacer, _s=send):
                    if message.get("type") == "http.response.body" and message.get("body"):
                        await _p.consume(len(message["body"]))
                    await _s(message)

                send = paced_send
        except Exception:
            pass  # throttle layer must never take the site down

        await self.app(scope, receive, send)
