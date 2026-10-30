"""Cross-worker revocation bus for collaboration WebSockets.

Each worker subscribes to `collab:revoke`; a broadcast reaches every worker so
the in-process room tables can each close their own matching sockets. This
keeps authorisation revocation correct even with multiple uvicorn workers.

Publishing is best-effort (Redis down must never break a delete/sign-out).
"""
import asyncio
import json
import threading
from typing import Optional

from redis import Redis

from app.config import settings

CHANNEL = "collab:revoke"

_loop: Optional[asyncio.AbstractEventLoop] = None
_kicker = None
_started = False
_lock = threading.Lock()
_pub_client: Optional[Redis] = None


def _client() -> Redis:
    global _pub_client
    if _pub_client is None:
        _pub_client = Redis.from_url(settings.REDIS_URL, decode_responses=True,
                                     socket_connect_timeout=5, socket_timeout=5)
    return _pub_client


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def set_kicker(fn) -> None:
    """Register the async callable(kind, file_uuid, user_id, reason) used to
    close local sockets. Provided by the websocket module."""
    global _kicker
    _kicker = fn


def publish_revoke(kind: str, *, file_uuid: Optional[str] = None,
                   user_id: Optional[int] = None, reason: str = "") -> None:
    try:
        payload = json.dumps({"kind": kind, "file_uuid": file_uuid,
                              "user_id": user_id, "reason": reason})
        _client().publish(CHANNEL, payload)
    except Exception:
        pass


def revoke_file(file_uuid: str, reason: str = "file revoked") -> None:
    publish_revoke("file", file_uuid=file_uuid, reason=reason)


def revoke_user(user_id: int, reason: str = "session revoked") -> None:
    publish_revoke("user", user_id=int(user_id), reason=reason)


def _dispatch(message: dict) -> None:
    if not _kicker or not _loop:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _kicker(message.get("kind"), message.get("file_uuid"),
                    message.get("user_id"), message.get("reason", "")),
            _loop,
        )
    except Exception:
        pass


def _run() -> None:
    while True:
        try:
            pubsub = _client().pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(CHANNEL)
            for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                try:
                    _dispatch(json.loads(raw["data"]))
                except Exception:
                    pass
        except Exception:
            # Redis unavailable / reconnect: back off briefly and retry.
            threading.Event().wait(5)


def start() -> None:
    """Start the background subscriber once per worker process."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_run, name="collab-revoke-subscriber", daemon=True).start()