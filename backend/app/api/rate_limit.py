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
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Generate key for this IP and endpoint
        endpoint = request.url.path
        key = f"rate_limit:{client_ip}:{endpoint}"
        
        # Get current count
        current = redis_client.get(key)
        if current is None:
            current = 0
        else:
            current = int(current.decode())
        
        # Check if limit exceeded
        if current >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds."
            )
        
        # Increment counter with expiration
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        pipe.execute()
    
    return check_rate_limit
