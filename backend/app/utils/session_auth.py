"""Helpers to parse and verify the server-side `session` cookie.

The cookie value is `"{user_id}|{token}"`. It is only trusted after the exact
value is compared (constant time) against `session:{user_id}` in Redis.
"""
import hmac
import json
from typing import Optional

from redis import Redis


def parse_session_cookie(cookie_header: Optional[str]) -> Optional[str]:
    """Extract the raw `session` cookie value from a Cookie header string."""
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("session="):
            return part[len("session="):] or None
    return None


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
        return json.loads(_decode(data))
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