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
from app.utils.session_auth import parse_session_cookie, resolve_session_uid

UPLOAD_PREFIXES = ('/api/files/tus', '/api/files/uploadFile')
DOWNLOAD_PREFIXES = (
    '/api/files/download', '/api/files/downloadBulk', '/api/folders/download',
    '/api/share/downloadFile', '/api/share/downloadFolder', '/api/share/downloadItems',
    '/api/files/stream', '/api/files/raw',
)
STREAM_PREFIXES = ('/api/files/stream',)
NO_COUNT_PREFIXES = ('/api/files/raw',)
SHARE_PREFIX = '/api/share/'


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
    def _session_cookie(headers):
        """Return the raw session cookie value (unverified)."""
        return parse_session_cookie(headers.get("cookie"))

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
            ip = sec.get_client_ip(headers) or (scope.get("client")[0] if scope.get("client") else "")
            path = scope.get("path", "")
            # A user id is only trusted after the cookie value is verified
            # against Redis; an unauthenticated caller cannot frame another
            # account by sending a forged `session=42|...` prefix.
            uid = None
            raw_session = self._session_cookie(headers)
            if raw_session:
                try:
                    uid = await asyncio.to_thread(resolve_session_uid, sec._client(), raw_session)
                except Exception:
                    uid = None
            is_upload = path.startswith(UPLOAD_PREFIXES)
            is_download = path.startswith(DOWNLOAD_PREFIXES)
            is_share = path.startswith(SHARE_PREFIX)
            is_stream = path.startswith(STREAM_PREFIXES)

            if ip and await asyncio.to_thread(sec.flood_exceeded, ip):
                rh, payload = self._json_429(headers.get("origin"))
                await send({"type": "http.response.start", "status": 429, "headers": rh})
                await send({"type": "http.response.body", "body": payload})
                return

            blocked, delay_ms, up_kbps, dn_kbps = await asyncio.to_thread(
                sec.match_rules, ip, uid, is_upload, is_download, is_share, is_stream)
            if blocked:
                rh, payload = self._json_429(headers.get("origin"))
                await send({"type": "http.response.start", "status": 429, "headers": rh})
                await send({"type": "http.response.body", "body": payload})
                return
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000.0)

            if ip and uid:
                asyncio.create_task(asyncio.to_thread(sec.track_actor, ip, uid))

            if is_upload:
                asyncio.create_task(asyncio.to_thread(sec.count_upload, uid, ip))
            if is_download and path not in NO_COUNT_PREFIXES and (not is_stream or not headers.get("range") or headers.get("range").strip().startswith("bytes=0-")):
                # stream/raw seeks are not new downloads; count playback sessions once
                if uid:
                    asyncio.create_task(asyncio.to_thread(sec.count_download, uid, ip, None))
                elif is_share:
                    qs = parse_qs(scope.get("query_string", b"").decode(errors="ignore"))
                    token = (qs.get("link") or [""])[0]
                    if token:
                        asyncio.create_task(asyncio.to_thread(sec.count_download, None, ip, token))

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
