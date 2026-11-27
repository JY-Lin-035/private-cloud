from fastapi import Request, HTTPException, Depends
from typing import Callable, Optional
from redis import Redis
from app.api.dependencies import get_redis

_FIXED_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('DEL', KEYS[2]) end
redis.call('EXPIRE', KEYS[1], ARGV[2], 'NX')
local scored = 0
if count > tonumber(ARGV[1]) then
    local until_ms = redis.call('PEXPIRETIME', KEYS[1])
    if redis.call('SET', KEYS[2], '1', 'NX', 'PXAT', until_ms) then scored = 1 end
end
return {count, scored}
"""


def _count_request(redis_client, key, limit, window):
    count, scored = redis_client.eval(_FIXED_WINDOW, 2, key, f"{key}:strike", limit, window)
    return count, bool(scored)


def _route_id(request: Request) -> str:
    """Fixed route identifier for audit output.

    A raw URL path can carry identifiers (and, in the future, attacker-chosen
    segments); the matched route template is stable and cannot forge audit
    rows. Falls back to the plain path when nothing matched (404 probing).
    """
    route = request.scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    return template or request.url.path


def _event_actor(request: Request) -> tuple[Optional[str], str, Optional[str]]:
    """(actor_for_sanctioning, actor_display, identity_source) for this request.

    Attribution comes ONLY from identities this request actually proved:

      1. `request.state.user` — set by SessionMiddleware on protected routes
         after a Redis-verified cookie (the authoritative source).
      2. `request.state.observed_identity` — what ThrottleMiddleware verified
         for public routes that deliberately skip session auth. Read-only:
         it never grants access and never renews the session.

    Nothing is guessed from the body, the cookie's id prefix, or ipActors.
    """
    from app.services.security_engine import UNVERIFIED_ACTOR

    user = getattr(request.state, "user", None)
    if isinstance(user, dict) and (user.get("username") or user.get("user_id")):
        username = user.get("username") or user.get("name")
        uid = user.get("user_id") or user.get("id")
        display = str(username) if username else (f"#{uid}" if uid else UNVERIFIED_ACTOR)
        return (str(username) if username else None), display, "verified_session"

    observed = getattr(request.state, "observed_identity", None)
    if isinstance(observed, dict) and observed.get("user_id"):
        username = observed.get("username")
        display = str(username) if username else f"#{observed['user_id']}"
        # Observed-but-not-authorised: display it, but keep it out of the
        # sanction-eligible `actor` channel entirely.
        return None, display, "observed_session"

    return None, UNVERIFIED_ACTOR, "none"


def rate_limit(max_requests: int, window_seconds: int, policy_id: Optional[str] = None) -> Callable:
    """
    Create a rate limiting dependency.

    Args:
        max_requests: Maximum number of requests allowed (code default)
        window_seconds: Time window in seconds
        policy_id: Registered threshold this route obeys. When given, the
            effective limit is read from the request's policy snapshot — one
            version per request, so a concurrent admin edit can never mix
            halves of two configurations inside a single decision.

    Returns:
        A dependency function that can be used in FastAPI routes

    Example:
        @router.post("/login", dependencies=[Depends(rate_limit(5, 10))])
    """
    def check_rate_limit(
        request: Request,
        redis_client: Redis = Depends(get_redis)
    ):
        """Check rate limit using Redis."""
        from app.utils.client_ip import request_client_ip
        client_ip = request_client_ip(request)

        if policy_id:
            from app.services import security_policy
            snapshot = security_policy.for_request(request)
            limit = snapshot.value(policy_id)
            window = security_policy.REGISTRY[policy_id].window_seconds or window_seconds
        else:
            limit, window = max_requests, window_seconds

        # Generate key for this IP and endpoint
        endpoint = request.url.path
        key = f"rate_limit:{client_ip}:{endpoint}"
        
        # The score marker shares the bucket's exact expiry, in one operation.
        count, first_overage = _count_request(redis_client, key, limit, window)
        
        # Check if limit exceeded (count is post-increment)
        if count > limit:
            # Every rejected request is still audited AND still counted against
            # the bucket, but the violation SCORE is claimed once per window
            # with SET NX — atomic, so N workers handling one burst cannot all
            # book it, and one long burst costs one violation instead of fifty.
            actor, actor_display, identity_source = _event_actor(request)
            route = _route_id(request)
            try:
                from app.services import security_engine
                security_engine.record_event(
                    "rate_limit", client_ip, actor, route,
                    f"限流 {limit}/{window}s 觸發（第 {count} 次）",
                    actor_display=actor_display,
                    extra={
                        "HTTP方法": request.method,
                        "路由": route,
                        "政策": policy_id or "-",
                        "拒絕來源": "端點限流",
                        "門檻": f"{limit}/{window}s",
                        "規則範圍": "endpoint",
                        "處分": "HTTP 429",
                        "身分來源": identity_source,
                        "違規計分": "是" if first_overage else "否（同一視窗重複）",
                    },
                    score=first_overage)
            except Exception:
                pass
            # Public contract: a generic 429. Thresholds, routes and the
            # identity that tripped them stay server-side for authorised admins.
            raise HTTPException(
                status_code=429,
                detail="請求過多，請稍後再試"
            )
    
    return check_rate_limit
