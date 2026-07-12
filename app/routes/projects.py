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

ROW_STATE_CYCLE: dict[RowStateEnum, RowStateEnum] = {
    RowStateEnum.not_started: RowStateEnum.in_progress,
    RowStateEnum.in_progress: RowStateEnum.done,
    RowStateEnum.done: RowStateEnum.not_started,
}


async def _get_project(project_id: int, user: User, session: AsyncSession) -> Project:
    """Fetch a project by its ID, ensuring it belongs to the user.

    Args:
        project_id (int): The ID of the project to fetch.
        user (User): The user making the request.
        session (AsyncSession): The database session.

    Raises:
        HTTPException: If the project is not found or does not belong to the user.

    Returns:
        Project: The fetched project.
    """
    project = await session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404)
    return project


async def _get_project_and_element(
    project_id: int,
    element_id: int,
    user: User,
    session: AsyncSession,
) -> tuple[Project, Element]:
    """
    Fetch a project and an element, ensuring the element belongs to the project.

    Args:
        project_id (int): id of project to fetch
        element_id (int): id of element to fetch
        user (User): user making the request
        session (AsyncSession): database session

    Raises:
        HTTPException:  if project or element not found, or if element does not belong to project

    Returns:
        tuple[Project, Element]: the project and element objects
    """
    project = await _get_project(project_id, user, session)
    element = await session.get(Element, element_id)
    if element is None or element.project_id != project.id:
        raise HTTPException(status_code=404)
    return project, element


async def _get_project_element_and_row(
    project_id: int,
    element_id: int,
    row_id: int,
    user: User,
    session: AsyncSession,
) -> tuple[Project, Element, Row]:
    """
    Fetch a project, an element, and a row, ensuring the element and row belong to the project.

    Args:
        project_id (int): id of project to fetch
        element_id (int): id of element to fetch
        row_id (int): id of row to fetch
        user (User): user making the request
        session (AsyncSession): database session

    Raises:
        HTTPException: if any object is not found, or if objects do not belong together

    Returns:
        tuple[Project, Element, Row]: the project, element, and row objects
    """
    project, element = await _get_project_and_element(
        project_id, element_id, user, session
    )
    row = await session.get(Row, row_id)
    if row is None or row.element_id != element.id:
        raise HTTPException(status_code=404)
    return project, element, row


async def _get_element_repetition(
    element_id: int, session: AsyncSession
) -> ElementRepetition:
    """
    Fetch an element repetition by its ID.

    Args:
        element_id (int): id of element to fetch repetition for
        session (AsyncSession): database session

    Raises:
        HTTPException: if repetition is not found

    Returns:
        ElementRepetition: the element repetition object
    """
    result = await session.execute(
        select(ElementRepetition).where(ElementRepetition.element_id == element_id)
    )
    return result.scalar_one()


async def _build_row_states(
    element_id: int, rows: list[Row], session: AsyncSession
) -> dict[int, RowStateEnum]:
    """
    Build a dictionary mapping row IDs to their states.

    Args:
        element_id (int): id of the element to fetch row states for
        rows (list[Row]): list of rows to fetch states for
        session (AsyncSession): database session

    Returns:
        dict[int, RowStateEnum]: dictionary mapping row IDs to their states
    """
    if not rows:
        return {}
    repetition = await _get_element_repetition(element_id, session)
    result = await session.execute(
        select(RowState).where(RowState.element_repetition_id == repetition.id)
    )
    row_states = result.scalars().all()
    return {row_state.row_id: row_state.state for row_state in row_states}


@router.get("/")
async def project_list(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a list of projects for the current user, ordered by last updated time.

    Args:
        request (Request): The incoming HTTP request.
        user (User, optional): The user making the request. Defaults to Depends(get_current_user).
        session (AsyncSession, optional): The database session. Defaults to Depends(get_session).

    Returns:
        _type_: A list of projects for the current user.
    """
    result = await session.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(500)
    )
    projects = result.scalars().all()
    return templates.TemplateResponse(
        request, "projects/list.html", {"user": user, "projects": projects}
    )


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
            request,
            "projects/new.html",
            {"user": user, "error": "Project name is required."},
        )
    if len(name) > 50:
        return templates.TemplateResponse(
            request,
            "projects/new.html",
            {"user": user, "error": "Project name must be 50 characters or fewer."},
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
    project = await _get_project(project_id, user, session)
    result = await session.execute(
        select(Element)
        .where(Element.project_id == project.id)
        .order_by(Element.created_at.asc())
    )
    elements = result.scalars().all()
    row_counts = await session.execute(
        select(Row.element_id, func.count(Row.id))
        .where(Row.element_id.in_([element.id for element in elements]))
        .group_by(Row.element_id)
    )
    counts_by_element = dict(row_counts.all())
    elements_with_counts = [
        (element, counts_by_element.get(element.id, 0)) for element in elements
    ]
    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {
            "user": user,
            "project": project,
            "elements_with_counts": elements_with_counts,
        },
    )


@router.get("/{project_id}/elements/new")
async def element_new_form(
    request: Request,
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, user, session)
    return templates.TemplateResponse(
        request, "projects/element_new.html", {"user": user, "project": project}
    )


@router.post("/{project_id}/elements/new")
async def element_create(
    request: Request,
    project_id: int,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, user, session)
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
            {
                "user": user,
                "project": project,
                "error": "Element name must be 50 characters or fewer.",
            },
        )
    now = datetime.now(timezone.utc)
    element = Element(project_id=project.id, name=name, repeat_count=1, created_at=now)
    session.add(element)
    await session.flush()
    project.updated_at = now
    session.add(project)

    # Commit before redirect so the follow-up GET sees the new element.
    await session.commit()

    return RedirectResponse(
        url=f"/projects/{project_id}/elements/{element.id}", status_code=303
    )


@router.get("/{project_id}/elements/{element_id}")
async def element_detail(
    request: Request,
    project_id: int,
    element_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project, element = await _get_project_and_element(
        project_id, element_id, user, session
    )
    result = await session.execute(
        select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
    )
    rows = result.scalars().all()
    row_states = await _build_row_states(element.id, rows, session)
    return templates.TemplateResponse(
        request,
        "projects/element_detail.html",
        {
            "user": user,
            "project": project,
            "element": element,
            "rows": rows,
            "row_states": row_states,
            "has_rows": len(rows) > 0,
        },
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
    project, element = await _get_project_and_element(
        project_id, element_id, user, session
    )

    async def _rerender_with_error(error: str):
        existing = await session.execute(
            select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
        )
        rows = existing.scalars().all()
        row_states = await _build_row_states(element.id, rows, session)
        return templates.TemplateResponse(
            request,
            "projects/element_detail.html",
            {
                "user": user,
                "project": project,
                "element": element,
                "rows": rows,
                "row_states": row_states,
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
        return await _rerender_with_error(
            "Pattern text produced no rows — please check the input."
        )

    # Delete existing rows in FK-safe order: RowStates → Rows + ElementRepetitions
    rep_ids_sub = select(ElementRepetition.id).where(
        ElementRepetition.element_id == element.id
    )
    await session.execute(
        delete(RowState).where(RowState.element_repetition_id.in_(rep_ids_sub))
    )
    await session.execute(delete(Row).where(Row.element_id == element.id))
    await session.execute(
        delete(ElementRepetition).where(ElementRepetition.element_id == element.id)
    )

    element.pattern_text = pattern_text.strip()
    session.add(element)

    new_rows = [
        Row(element_id=element.id, position=pos, content=content)
        for pos, content in parsed
    ]
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
        RowState(
            element_repetition_id=rep.id, row_id=row.id, state=RowStateEnum.not_started
        )
        for rep in new_reps
        for row in new_rows
    )

    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit before redirect so the follow-up GET sees the new rows.
    # get_session also commits after the handler returns, but the browser can
    # send the redirect GET before that cleanup runs.
    await session.commit()

    return RedirectResponse(
        url=f"/projects/{project_id}/elements/{element_id}", status_code=303
    )


@router.post("/{project_id}/elements/{element_id}/rows/{row_id}/state")
async def row_state_toggle(
    project_id: int,
    element_id: int,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project, element, row = await _get_project_element_and_row(
        project_id, element_id, row_id, user, session
    )
    repetition = await _get_element_repetition(element.id, session)
    result = await session.execute(
        select(RowState).where(
            RowState.element_repetition_id == repetition.id,
            RowState.row_id == row.id,
        )
    )
    row_state = result.scalar_one()
    row_state.state = ROW_STATE_CYCLE[row_state.state]
    session.add(row_state)

    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit before redirect so the follow-up GET sees the new state.
    await session.commit()

    return RedirectResponse(
        url=f"/projects/{project_id}/elements/{element_id}", status_code=303
    )
