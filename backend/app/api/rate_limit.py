from fastapi import Request, HTTPException, Depends
from typing import Callable
from redis import Redis
from app.api.dependencies import get_redis


def rate_limit(max_requests: int, window_seconds: int) -> Callable:
    """
    Create a rate limiting dependency.
    
    Args:
        max_requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
    
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
        
        # Generate key for this IP and endpoint
        endpoint = request.url.path
        key = f"rate_limit:{client_ip}:{endpoint}"
        
        # Atomic fixed-window: INCR and only (re)arm the TTL when the key has
        # none. Setting EXPIRE on every hit would let a persistent attacker
        # slide the window open forever (permanent 429 for the whole bucket),
        # and get-then-incr raced under concurrency.
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if ttl is not None and ttl < 0:
            redis_client.expire(key, window_seconds)
        
        # Check if limit exceeded (count is post-increment)
        if count > max_requests:
            try:
                from app.services import security_engine
                security_engine.record_event(
                    "rate_limit", client_ip, None, endpoint,
                    f"限流 {max_requests}/{window_seconds}s 觸發（第 {count} 次）")
            except Exception:
                pass
            raise HTTPException(
                status_code=429,
                detail="請求過多，請稍後再試"
            )
    
    return check_rate_limit
