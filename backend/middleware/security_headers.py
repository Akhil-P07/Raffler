"""Security headers applied to every response.

connect-src must include the API origin or the SPA's fetch/axios calls are
blocked by the browser. style-src 'unsafe-inline' is required for Tailwind's
injected styles. Both pull from config so deploys point at real domains.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        csp = (
            "default-src 'self'; "
            f"connect-src 'self' {settings.API_ORIGIN}; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'"
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        return response
