from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.auth.dependencies import get_current_user_optional
from app.auth.middleware import AuthRedirectMiddleware
from app.config import SECRET_KEY
from app.db import get_session
from app.models.project import Project
from app.models.user import User
from app.routes.auth import router as auth_router
from app.routes.projects import router as projects_router
from app.routes.stitches import router as stitches_router

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
app.include_router(projects_router)
app.include_router(stitches_router)


@app.exception_handler(Exception)
async def server_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(request, "500.html", {}, status_code=500)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
async def index(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    if user is None:
        return templates.TemplateResponse(
            request, "index.html", {"user": None, "projects": []}
        )

    result = await session.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(500)
    )
    projects = result.scalars().all()
    return templates.TemplateResponse(
        request, "index.html", {"user": user, "projects": projects}
    )
