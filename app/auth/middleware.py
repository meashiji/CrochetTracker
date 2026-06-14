from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

PUBLIC_PATH_PREFIXES = ("/health", "/auth/", "/static/")


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.session.get("user_id") is None and not request.url.path.startswith(
            PUBLIC_PATH_PREFIXES
        ):
            return RedirectResponse(url="/auth/login", status_code=303)
        return await call_next(request)
