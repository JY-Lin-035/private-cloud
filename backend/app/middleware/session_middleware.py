from typing import Optional
from fastapi import Request, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
from redis import Redis
from app.config import settings
from app.utils import logger as log
from app.constants import HTTPStatus
import json

logger = log.get_logger("session_middleware.log")


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

        logger.info(f"Session middleware - Request: {request.url.path}, has_session_cookie: {session_token is not None}")
        
        if session_token:
            # Validate session format (id|token)
            if '|' not in session_token:
                logger.info(f"Session middleware - Invalid session format, session_token: {session_token}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
            user_id, token_value = session_token.split('|', 1)
            
            try:
                user_id = int(user_id)
            except ValueError:
                logger.info(f"Session middleware - Invalid user_id in session, session_token: {session_token}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
            # Check session in Redis
            stored_token = self.redis.get(f"session:{user_id}")
            if not stored_token:
                logger.info(f"Session middleware - Session not found in Redis, user_id: {user_id}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
            # Handle both string and bytes
            if isinstance(stored_token, bytes):
                stored_token_str = stored_token.decode()
            else:
                stored_token_str = stored_token
            
            if stored_token_str != session_token:
                logger.info(f"Session middleware - Session token mismatch, user_id: {user_id}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
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
                    logger.info(f"Session middleware - Session validated, user_id: {user_id}")
                except json.JSONDecodeError as e:
                    logger.error(f"Session middleware - Failed to parse user data: {e}")
                    return Response(status_code=HTTPStatus.UNAUTHORIZED)
            else:
                logger.info(f"Session middleware - User data not found in Redis, user_id: {user_id}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
            # Extend session expiration
            self.redis.expire(f"session:{user_id}", settings.TOKEN_EXPIRE_TIME * 60)
            self.redis.expire(f"session_data:{user_id}", settings.TOKEN_EXPIRE_TIME * 60)
        else:
            logger.info(f"Session middleware - No session cookie provided, path: {request.url.path}")
        
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
                samesite='lax',
                secure=False
            )
        
        return response
