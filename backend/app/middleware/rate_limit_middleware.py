from typing import Optional
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from redis import Redis
from app.config import settings
from app.constants import HTTPStatusExtra
import json


# Create rate limiter with Redis backend
def get_redis_key_func(request: Request):
    """Generate rate limit key based on IP address."""
    return f"rate_limit:{get_remote_address(request)}"


class RateLimitMiddleware:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.limiter = Limiter(
            key_func=get_redis_key_func,
            storage_uri=settings.REDIS_URL,
            default_limits=["200 per day", "50 per hour"]
        )
    
    def check_rate_limit(self, request: Request, limit: str):
        """Check if request is within rate limit."""
        key = get_redis_key_func(request)
        
        # Get current count
        current = self.redis.get(key)
        if current is None:
            current = 0
        else:
            current = int(current.decode())
        
        # Parse limit (e.g., "5/30" means 5 requests per 30 seconds)
        parts = limit.split('/')
        max_requests = int(parts[0])
        window_seconds = int(parts[1])
        
        # Check if limit exceeded
        if current >= max_requests:
            raise HTTPException(status_code=HTTPStatusExtra.TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        
        # Increment counter
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        pipe.execute()
