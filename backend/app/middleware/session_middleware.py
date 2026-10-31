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
    # Read-only, background-polled endpoints that authenticate the session but
    # must never slide its expiry forward. Keeping these out of the renewal path
    # is what makes an idle (but open) tab expire as designed.
    NO_RENEW_PATHS = ('/api/announcements',)

    # Endpoints that must be reachable without a valid session. Matched by
    # EXACT path (plus an explicit prefix list) so a future sibling route such
    # as /api/files/downloadXxx can never silently become public.
    PUBLIC_EXACT = frozenset({
        '/api/accounts/login',
        '/api/accounts/register',
        '/api/accounts/getCode',
        '/api/accounts/resetPW',
        '/api/accounts/checkSession',
        '/api/accounts/settings/public',
        '/api/share/downloadFile',
        '/api/share/downloadFolder',
        '/api/share/downloadItems',
        '/api/share/browse',
        '/api/share/status',
        '/api/share/verifyPassword',
        '/api/files/download',
        '/api/files/raw',
    })
    PUBLIC_PREFIX = ('/api/email/verify/',)

    def __init__(self, app, redis_client: Redis):
        super().__init__(app)
        self.redis = redis_client

    def _is_public(self, path: str) -> bool:
        return path in self.PUBLIC_EXACT or any(path.startswith(p) for p in self.PUBLIC_PREFIX)

    def _is_no_renew(self, request: Request) -> bool:
        return (
            request.method == 'GET'
            and any(request.url.path.startswith(p) for p in self.NO_RENEW_PATHS)
        )

    async def dispatch(self, request: Request, call_next):
        # Skip session validation for public endpoints
        if self._is_public(request.url.path):
            return await call_next(request)

        # Extract session cookie
        raw_cookie = request.headers.get('cookie') or ''
        from app.utils.session_auth import parse_session_cookie
        session_token = parse_session_cookie(raw_cookie)
        if session_token is None and 'session' in raw_cookie.lower():
            # a session-ish cookie exists but the single trusted parser
            # rejects it (duplicates / malformed) -> fail closed
            logger.info("Session middleware - Rejected malformed/duplicate session cookie")
            return Response(status_code=HTTPStatus.UNAUTHORIZED)
        if session_token:
            # Validate session format (id|token)
            if '|' not in session_token:
                logger.info(f"Session middleware - Invalid session format, path: {request.url.path}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
            user_id, token_value = session_token.split('|', 1)
            
            try:
                user_id = int(user_id)
            except ValueError:
                logger.info(f"Session middleware - Invalid user_id in session, path: {request.url.path}")
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
                except json.JSONDecodeError as e:
                    logger.error(f"Session middleware - Failed to parse user data: {e}")
                    return Response(status_code=HTTPStatus.UNAUTHORIZED)
            else:
                logger.info(f"Session middleware - User data not found in Redis, user_id: {user_id}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            
            # Extend session expiration.
            # Passive background-polling endpoints (the announcement ticker) must NOT
            # keep a session alive, otherwise an idle-but-open tab would never expire.
            # Real user interactions still slide the window forward as before.
            if not self._is_no_renew(request):
                self.redis.expire(f"session:{user_id}", settings.TOKEN_EXPIRE_TIME * 60)
                self.redis.expire(f"session_data:{user_id}", settings.TOKEN_EXPIRE_TIME * 60)
        
        # Process request
        response = await call_next(request)
        
        # Set session cookie if user is authenticated
        if session_token and hasattr(request.state, 'user') and not self._is_no_renew(request):
                    response.set_cookie(
                        key='session',
                        value=session_token,
                        max_age=settings.TOKEN_EXPIRE_TIME * 60,
                        path='/',
                        httponly=True,
                        samesite=settings.COOKIE_SAMESITE,
                        secure=True
                    )
        
        return response
