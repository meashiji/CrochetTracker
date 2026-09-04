import random

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.auth.dependencies import get_current_user_optional
from app.auth.middleware import AuthRedirectMiddleware
from app.config import SECRET_KEY
from app.db import get_session
from app.models.pattern import Row
from app.models.progress import RowState, RowStateEnum
from app.models.project import Element, ElementRepetition, Project
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

RESUME_MESSAGES = (
    "Your next stitch is waiting.",
    "A few more rows are ready when you are.",
    "Keep the momentum going.",
    "This project is calling you back.",
)

START_MESSAGES = (
    "A fresh stitch is a good place to start.",
    "Which project will you bring to life today?",
    "Your next handmade idea starts here.",
)


async def _get_element_progress_counts(
    element: Element, session: AsyncSession
) -> dict[str, int]:
    """Return the same row/state counts shown for an element in the project list."""
    row_count = (
        await session.execute(
            select(func.count(Row.id)).where(Row.element_id == element.id)
        )
    ).scalar_one()
    state_result = await session.execute(
        select(RowState.state, func.count(RowState.id))
        .join(ElementRepetition, RowState.element_repetition_id == ElementRepetition.id)
        .where(ElementRepetition.element_id == element.id)
        .group_by(RowState.state)
    )
    state_counts = dict(state_result.all())
    return {
        "row_count": row_count,
        "done_count": state_counts.get(RowStateEnum.done, 0),
        "in_progress_count": state_counts.get(RowStateEnum.in_progress, 0),
        "not_started_count": state_counts.get(RowStateEnum.not_started, 0),
    }


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
    recommendation = await _build_resume_recommendation(projects, session)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "projects": projects, "recommendation": recommendation},
    )


async def _build_resume_recommendation(
    projects: list[Project], session: AsyncSession
) -> dict[str, str] | None:
    """Select one started, unfinished element, with a recent-project fallback."""
    if not projects:
        return None

    project_ids = [project.id for project in projects]
    started_states = (RowStateEnum.in_progress, RowStateEnum.done)
    started_state = aliased(RowState)
    started_repetition = aliased(ElementRepetition)
    started_row = aliased(Row)
    started_element = (
        select(started_state.id)
        .join(
            started_repetition,
            started_repetition.id == started_state.element_repetition_id,
        )
        .join(started_row, started_row.id == started_state.row_id)
        .where(
            started_repetition.element_id == Element.id,
            started_row.element_id == Element.id,
            started_state.state.in_(started_states),
        )
        .exists()
    )
    candidate_result = await session.execute(
        select(Project, Element)
        .join(Element, Element.project_id == Project.id)
        .join(ElementRepetition, ElementRepetition.element_id == Element.id)
        .join(RowState, RowState.element_repetition_id == ElementRepetition.id)
        .join(Row, Row.id == RowState.row_id)
        .where(
            Project.user_id == projects[0].user_id,
            Project.id.in_(project_ids),
            Row.element_id == Element.id,
            RowState.state != RowStateEnum.done,
            started_element,
        )
        .distinct()
    )
    candidates_by_project: dict[int, list[tuple[Project, Element]]] = {}
    for project, element in candidate_result.all():
        candidates_by_project.setdefault(project.id, []).append((project, element))

    if candidates_by_project:
        project_id = random.choice(list(candidates_by_project))
        project, element = random.choice(candidates_by_project[project_id])
        progress_counts = await _get_element_progress_counts(element, session)
        return {
            "eyebrow": "Pick up where you left off",
            "message": random.choice(RESUME_MESSAGES),
            "project_name": project.name,
            "element_name": element.name or "Unnamed element",
            "href": f"/projects/{project.id}/elements/{element.id}",
            "cta": "Continue project",
            "repeat_count": element.repeat_count,
            **progress_counts,
        }

    elements_result = await session.execute(
        select(Element)
        .where(Element.project_id.in_(project_ids))
        .order_by(Element.created_at.asc(), Element.id.asc())
    )
    elements_by_project: dict[int, list[Element]] = {}
    for element in elements_result.scalars().all():
        elements_by_project.setdefault(element.project_id, []).append(element)

    for project in projects:
        elements = elements_by_project.get(project.id, [])
        if elements:
            element = elements[0]
            progress_counts = await _get_element_progress_counts(element, session)
            return {
                "eyebrow": "A gentle nudge",
                "message": random.choice(START_MESSAGES),
                "project_name": project.name,
                "element_name": element.name or "Unnamed element",
                "href": f"/projects/{project.id}/elements/{element.id}",
                "cta": "Start this project",
                "repeat_count": element.repeat_count,
                **progress_counts,
            }
    return None
