from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth.dependencies import get_current_user
from app.auth.middleware import AuthRedirectMiddleware
from app.config import SECRET_KEY
from app.models.user import User
from app.routes.auth import router as auth_router

app = FastAPI(title="CrochetTracker")

# Starlette wraps middleware in reverse add-order (last added = outermost),
# so AuthRedirectMiddleware must be added first to run after SessionMiddleware
# has parsed request.session.
app.add_middleware(AuthRedirectMiddleware)
app.add_middleware(
    SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=True
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
async def index(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "index.html", {"user": user})
