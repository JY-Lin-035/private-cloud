from typing import Optional
from fastapi import Request, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
from redis import Redis
from app.config import settings
from app.utils.logger import log_info, log_error
import json


class SessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client: Redis):
        super().__init__(app)
        self.redis = redis_client
    
    async def dispatch(self, request: Request, call_next):
        # Skip session validation for public endpoints
        public_paths = ['/api/accounts/login', '/api/accounts/register', '/api/accounts/getCode', '/api/accounts/verifyEmail']
        if any(request.url.path.startswith(path) for path in public_paths):
            return await call_next(request)

        # Extract session cookie
        session_token = request.cookies.get('session')

        log_info(f"Session middleware - Request: {request.url.path}", {"has_session_cookie": session_token is not None})
        
        if session_token:
            # Validate session format (id|token)
            if '|' not in session_token:
                log_info("Session middleware - Invalid session format", {"session_token": session_token})
                return Response(status_code=401)
            
            user_id, token_value = session_token.split('|', 1)
            
            try:
                user_id = int(user_id)
            except ValueError:
                log_info("Session middleware - Invalid user_id in session", {"session_token": session_token})
                return Response(status_code=401)
            
            # Check session in Redis
            stored_token = self.redis.get(f"session:{user_id}")
            if not stored_token:
                log_info("Session middleware - Session not found in Redis", {"user_id": user_id})
                return Response(status_code=401)
            
            # Handle both string and bytes
            if isinstance(stored_token, bytes):
                stored_token_str = stored_token.decode()
            else:
                stored_token_str = stored_token
            
            if stored_token_str != session_token:
                log_info("Session middleware - Session token mismatch", {"user_id": user_id})
                return Response(status_code=401)
            
            # Get user data from Redis
            user_data = self.redis.get(f"session_data:{user_id}")
            if user_data:
                try:
                    if isinstance(user_data, bytes):
                        user_data_str = user_data.decode()
                    else:
                        user_data_str = user_data
                    user_dict = json.loads(user_data_str)
                    # Inject user into request state
                    request.state.user = user_dict
                    request.state.user_id = user_id
                    log_info("Session middleware - Session validated", {"user_id": user_id})
                except json.JSONDecodeError as e:
                    log_error("Session middleware - Failed to parse user data", e)
                    return Response(status_code=401)
            else:
                log_info("Session middleware - User data not found in Redis", {"user_id": user_id})
                return Response(status_code=401)
            
            # Extend session expiration
            self.redis.expire(f"session:{user_id}", settings.TOKEN_EXPIRE_TIME * 60)
            self.redis.expire(f"session_data:{user_id}", settings.TOKEN_EXPIRE_TIME * 60)
        else:
            log_info("Session middleware - No session cookie provided", {"path": request.url.path})
        
        # Process request
        response = await call_next(request)
        
        # Set session cookie if user is authenticated
        if session_token and hasattr(request.state, 'user'):
            response.set_cookie(
                key='session',
                value=session_token,
                max_age=settings.TOKEN_EXPIRE_TIME * 60,
                path='/',
                httponly=True,
                samesite='lax'
            )
        
        return response
