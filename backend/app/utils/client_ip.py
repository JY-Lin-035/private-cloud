"""Trusted client IP for FastAPI requests.

Cloudflare provides the real client address in `CF-Connecting-IP`. We never use
`X-Forwarded-For` (spoofable). When the header is absent (local development),
fall back to the direct peer address.
"""
from fastapi import Request


def request_client_ip(request: Request) -> str:
    try:
        from app.services.security_engine import get_client_ip
        headers = {k.lower(): v for k, v in request.headers.items()}
        ip = get_client_ip(headers)
        if ip:
            return ip
    except Exception:
        pass
    return request.client.host if request.client else "unknown"