from typing import Optional
from fastapi import Request, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
from redis import Redis
from app.config import settings
from app.utils import logger as log
from app.constants import HTTPStatus

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
        from app.utils.session_auth import (cookie_header, parse_session_cookie, split_session_value,
                                            verify_session_value)
        raw_cookie = cookie_header(request.scope)
        session_token = parse_session_cookie(raw_cookie)
        if session_token is None and 'session' in raw_cookie.lower():
            # a session-ish cookie exists but the single trusted parser
            # rejects it (duplicates / malformed) -> fail closed
            logger.info("Session middleware - Rejected malformed/duplicate session cookie")
            return Response(status_code=HTTPStatus.UNAUTHORIZED)
        if session_token:
            parsed = split_session_value(session_token)
            if not parsed:
                logger.info(f"Session middleware - Invalid session format, path: {request.url.path}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)
            user_id = parsed[0]

            # One verification implementation for the whole app: the shared
            # helper compares the token against Redis in constant time, so
            # middleware / Throttle / checkSession can never disagree about
            # who is signed in.
            user_dict = verify_session_value(self.redis, session_token)
            if user_dict is None:
                logger.info(f"Session middleware - Session not found or mismatched, user_id: {user_id}")
                return Response(status_code=HTTPStatus.UNAUTHORIZED)

            # Inject user into request state
            request.state.user = user_dict
            request.state.user_id = user_id

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
