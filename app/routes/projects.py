from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models.project import Element, Project
from app.models.user import User

router = APIRouter(prefix="/projects")
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def project_list(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc()).limit(500)
    )
    projects = result.scalars().all()
    return templates.TemplateResponse(request, "projects/list.html", {"user": user, "projects": projects})


@router.get("/new")
async def project_new_form(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "projects/new.html", {"user": user})


@router.post("/new")
async def project_create(
    request: Request,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request, "projects/new.html", {"user": user, "error": "Project name is required."}
        )
    if len(name) > 50:
        return templates.TemplateResponse(
            request, "projects/new.html", {"user": user, "error": "Project name must be 50 characters or fewer."}
        )
    now = datetime.now(timezone.utc)
    project = Project(user_id=user.id, name=name, created_at=now, updated_at=now)
    session.add(project)
    await session.flush()
    element = Element(project_id=project.id, name=None, repeat_count=1, created_at=now)
    session.add(element)
    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)
