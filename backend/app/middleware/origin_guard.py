"""CSRF defence for cookie-authenticated, state-changing requests.

Browsers always attach an Origin header to cross-origin (and same-origin
non-GET) fetch/XHR/form submissions. When the `session` cookie is present on an
unsafe method we require Origin (or, failing that, Referer) to be one of the
configured front-end origins. Requests without the session cookie (CLI clients,
anonymous share downloads, token URLs) are unaffected.

Registered *inside* CORSMiddleware so early 403s still carry CORS headers.
"""
import json

from app.config import settings


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_STATUS = 403


def _reject(origin: str | None):
    payload = json.dumps({"detail": "來源不受信任"}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode()),
    ]
    # Only echo CORS headers for an origin we already know is allowed.
    if origin and origin in settings.allowed_origins:
        headers.append((b"access-control-allow-origin", origin.encode()))
        headers.append((b"access-control-allow-credentials", b"true"))
    return headers, payload


def _origin_ok(value: str | None) -> bool:
    if not value:
        return False
    # Origin is exactly scheme://host[:port]; Referer is a full URL.
    candidate = value.rstrip("/")
    if "://" in candidate:
        parts = candidate.split("/", 3)
        candidate = "/".join(parts[:3])  # scheme://host[:port]
    return candidate in settings.allowed_origins


def _has_session_cookie(headers: dict[str, str]) -> bool:
    cookie = headers.get("cookie") or ""
    return "session=" in cookie


# Unauthenticated auth endpoints that are still CSRF-relevant (login-CSRF:
# an attacker POSTs a victim's browser to /login to plant the attacker's
# session). For these we validate Origin WHENEVER the browser sends one,
# even though there is no session cookie yet. A missing Origin (native/curl)
# is allowed — a real cross-site browser form/fetch always sends it.
ANON_ORIGIN_CHECKED = (
    "/api/accounts/login",
    "/api/accounts/register",
    "/api/accounts/getCode",
    "/api/accounts/resetPW",
    "/api/share/verifyPassword",
)


class OriginGuardMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {}
        for k, v in scope.get("headers", []):
            try:
                headers[k.decode().lower()] = v.decode(errors="ignore")
            except Exception:
                pass

        origin = headers.get("origin")
        referer = headers.get("referer")

        if not _has_session_cookie(headers):
            # Login-CSRF guard: no cookie yet, but if this is one of the auth
            # endpoints and a browser Origin is attached, it must be trusted.
            path = scope.get("path", "")
            if origin is not None and path.startswith(ANON_ORIGIN_CHECKED) and not _origin_ok(origin):
                rh, payload = _reject(origin)
                await send({"type": "http.response.start", "status": _STATUS, "headers": rh})
                await send({"type": "http.response.body", "body": payload})
                return
            await self.app(scope, receive, send)
            return

        if _origin_ok(origin) or (not origin and _origin_ok(referer)):
            await self.app(scope, receive, send)
            return

        rh, payload = _reject(origin)
        await send({"type": "http.response.start", "status": _STATUS, "headers": rh})
        await send({"type": "http.response.body", "body": payload})