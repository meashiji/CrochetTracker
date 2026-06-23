from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

# Exact paths that don't require a session. /static/ stays as a prefix.
_PUBLIC_PATHS = {"/health", "/auth/login", "/auth/signup", "/auth/magic-link", "/auth/magic-link/verify"}


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_public = path in _PUBLIC_PATHS or path.startswith("/static/")
        if request.session.get("user_id") is None and not is_public:
            return RedirectResponse(url="/auth/login", status_code=303)
        return await call_next(request)
