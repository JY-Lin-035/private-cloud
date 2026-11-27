"""Helpers to parse and verify the server-side `session` cookie.

The cookie value is `"{user_id}|{token}"`. It is only trusted after the exact
value is compared (constant time) against `session:{user_id}` in Redis.
"""
import hmac
import json
import re as _re
from typing import Optional

from redis import Redis

# Single definition of "this cookie header carries a session cookie".
# OriginGuard (CSRF trigger), Throttle (identity observation) and
# SessionMiddleware (authorisation) all ask through these two helpers, so a
# request can never be "credentialed" to one layer and anonymous to another.
_SESSION_MARKER = _re.compile(r"(?:^|;)\s*[Ss]ession\s*=")


def cookie_header(scope) -> str:
    return "; ".join(value.decode("latin-1") for key, value in scope.get("headers", ())
                     if key.lower() == b"cookie")


def parse_session_cookie(cookie_header: Optional[str]) -> Optional[str]:
    """Extract the raw `session` cookie value using the SAME parser the auth
    layer (Starlette SimpleCookie) uses, and fail closed on duplicates.

    Red-team DS2-5: earlier hand-rolled `startswith("session=")` disagreed with
    SimpleCookie on whitespace around `=` (e.g. `session = v`), resurrecting the
    auth-vs-guard divergence. Red-team r10: duplicate cookies resolved
    last-wins by Starlette vs first-wins here — accounting evasion.
    """
    if not cookie_header:
        return None
    if len(_SESSION_MARKER.findall(cookie_header)) != 1:
        return None
    try:
        from http.cookies import SimpleCookie
        c = SimpleCookie()
        c.load(cookie_header)
        m = c.get("session")
        return m.value if m else None
    except Exception:
        return None


def has_session_cookie(cookie_header: Optional[str]) -> bool:
    """Whether a session-ish cookie is present at all (OriginGuard's CSRF
    trigger). Shares parse_session_cookie's detector so the two cookie views
    in the pipeline can never disagree about 'is this request credentialed'."""
    if not cookie_header:
        return False
    return bool(_SESSION_MARKER.search(cookie_header))


def split_session_value(value: Optional[str]) -> Optional[tuple[int, str]]:
    """Return (user_id, raw_value) when the value has the `id|token` shape."""
    if not value or "|" not in value:
        return None
    uid_s, _token = value.split("|", 1)
    try:
        uid = int(uid_s)
    except ValueError:
        return None
    if uid <= 0:
        return None
    return uid, value


def _decode(raw) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw


def verify_session_value(redis: Redis, value: Optional[str]) -> Optional[dict]:
    """Fully validate a session cookie value and return its user dict.

    Returns None if the format is wrong, the stored token does not match, or
    the session/user data is missing. Comparison is constant-time.
    """
    parsed = split_session_value(value)
    if not parsed:
        return None
    uid, raw = parsed
    try:
        stored = redis.get(f"session:{uid}")
        if not stored:
            return None
        if not hmac.compare_digest(_decode(stored), raw):
            return None
        data = redis.get(f"session_data:{uid}")
        if not data:
            return None
        user = json.loads(_decode(data))
        if not isinstance(user, dict):
            return None
        ids = [user[field] for field in ("user_id", "id") if field in user]
        if not ids or any(type(value) not in (int, str) or str(value) != str(uid) for value in ids):
            return None
        return user
    except Exception:
        return None


def resolve_session_uid(redis: Redis, value: Optional[str]) -> Optional[int]:
    """Verify a session cookie and return the authenticated user id (or None)."""
    data = verify_session_value(redis, value)
    if not data:
        return None
    try:
        uid = int(data.get("user_id"))
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def resolve_session_identity(redis: Redis,
                             cookie_header: Optional[str]) -> Optional[dict]:
    """Return {'user_id', 'username'} for ATTRIBUTION purposes, or None.

    Stricter than resolve_session_uid on purpose: a security event may only
    name an account when every link in the chain agrees.

      * exactly one `session` cookie (duplicate cookies are ambiguous -> drop)
      * the `id|token` value matches Redis (constant-time, see above)
      * the Redis account blob names the SAME id the cookie prefix claims
        (a stale/partial session_data must never frame another account)

    Deliberately does NOT renew or extend anything, and never exposes the
    stored email — only the display name / id are safe for admin logs.
    """
    value = parse_session_cookie(cookie_header)
    parsed = split_session_value(value) if value else None
    if not parsed:
        return None
    uid, raw = parsed
    data = verify_session_value(redis, raw)
    if not data:
        return None
    # Legacy session blobs stored the id under 'id'; the auth layer accepts
    # both, so attribution must too (otherwise a real signed-in request would
    # be reported as 本請求未驗證帳號 while SessionMiddleware authorised it).
    data_uid = None
    for field in ("user_id", "id"):
        try:
            candidate = int(data.get(field))
        except (TypeError, ValueError):
            continue
        if candidate > 0:
            data_uid = candidate
            break
    if data_uid is None or data_uid != uid:
        return None
    username = data.get("username")
    return {"user_id": uid, "username": str(username) if username else None}
