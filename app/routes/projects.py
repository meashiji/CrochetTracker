from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models.pattern import Row
from app.models.progress import RowState, RowStateEnum
from app.models.project import Element, ElementRepetition, Project
from app.models.user import User
from app.services.pattern import parse_pattern

router = APIRouter(prefix="/projects")
templates = Jinja2Templates(directory="app/templates")

MAX_PATTERN_LENGTH = 50_000


async def _get_project_and_element(
    project_id: int,
    element_id: int,
    user: User,
    session: AsyncSession,
) -> tuple[Project, Element]:
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404)
    element = await session.get(Element, element_id)
    if element is None or element.project_id != project.id:
        raise HTTPException(status_code=404)
    return project, element


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


@router.get("/{project_id}")
async def project_detail(
    request: Request,
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404)
    result = await session.execute(select(Element).where(Element.project_id == project.id))
    elements = result.scalars().all()
    row_counts = await session.execute(
        select(Row.element_id, func.count(Row.id))
        .where(Row.element_id.in_([element.id for element in elements]))
        .group_by(Row.element_id)
    )
    counts_by_element = dict(row_counts.all())
    elements_with_counts = [(element, counts_by_element.get(element.id, 0)) for element in elements]
    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {"user": user, "project": project, "elements_with_counts": elements_with_counts},
    )


@router.get("/{project_id}/elements/new")
async def element_new_form(
    request: Request,
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "projects/element_new.html", {"user": user, "project": project})


@router.post("/{project_id}/elements/new")
async def element_create(
    request: Request,
    project_id: int,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404)
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request,
            "projects/element_new.html",
            {"user": user, "project": project, "error": "Element name is required."},
        )
    if len(name) > 50:
        return templates.TemplateResponse(
            request,
            "projects/element_new.html",
            {"user": user, "project": project, "error": "Element name must be 50 characters or fewer."},
        )
    now = datetime.now(timezone.utc)
    element = Element(project_id=project.id, name=name, repeat_count=1, created_at=now)
    session.add(element)
    await session.flush()
    project.updated_at = now
    session.add(project)
    return RedirectResponse(url=f"/projects/{project_id}/elements/{element.id}", status_code=303)


@router.get("/{project_id}/elements/{element_id}")
async def element_detail(
    request: Request,
    project_id: int,
    element_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project, element = await _get_project_and_element(project_id, element_id, user, session)
    result = await session.execute(
        select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
    )
    rows = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "projects/element_detail.html",
        {"user": user, "project": project, "element": element, "rows": rows, "has_rows": len(rows) > 0},
    )


@router.post("/{project_id}/elements/{element_id}")
async def element_save_pattern(
    request: Request,
    project_id: int,
    element_id: int,
    pattern_text: str = Form(default=""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project, element = await _get_project_and_element(project_id, element_id, user, session)

    async def _rerender_with_error(error: str):
        existing = await session.execute(
            select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
        )
        rows = existing.scalars().all()
        return templates.TemplateResponse(
            request,
            "projects/element_detail.html",
            {
                "user": user,
                "project": project,
                "element": element,
                "rows": rows,
                "has_rows": len(rows) > 0,
                "error": error,
            },
        )

    if len(pattern_text) > MAX_PATTERN_LENGTH:
        return await _rerender_with_error(
            f"Pattern too large — max {MAX_PATTERN_LENGTH:,} characters."
        )

    parsed = parse_pattern(pattern_text)
    if not parsed:
        return await _rerender_with_error("Pattern text produced no rows — please check the input.")

    # Delete existing rows in FK-safe order: RowStates → Rows + ElementRepetitions
    rep_ids_sub = select(ElementRepetition.id).where(ElementRepetition.element_id == element.id)
    await session.execute(delete(RowState).where(RowState.element_repetition_id.in_(rep_ids_sub)))
    await session.execute(delete(Row).where(Row.element_id == element.id))
    await session.execute(delete(ElementRepetition).where(ElementRepetition.element_id == element.id))

    element.pattern_text = pattern_text.strip()
    session.add(element)

    new_rows = [Row(element_id=element.id, position=pos, content=content) for pos, content in parsed]
    for row in new_rows:
        session.add(row)

    new_reps = [
        ElementRepetition(element_id=element.id, repetition_number=i)
        for i in range(1, element.repeat_count + 1)
    ]
    for rep in new_reps:
        session.add(rep)

    await session.flush()  # populate PKs before RowState inserts reference them

    session.add_all(
        RowState(element_repetition_id=rep.id, row_id=row.id, state=RowStateEnum.not_started)
        for rep in new_reps
        for row in new_rows
    )

    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit before redirect so the follow-up GET sees the new rows.
    # get_session also commits after the handler returns, but the browser can
    # send the redirect GET before that cleanup runs.
    await session.commit()

    return RedirectResponse(url=f"/projects/{project_id}/elements/{element_id}", status_code=303)
