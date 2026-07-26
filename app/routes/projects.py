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


def _first_unmarked_row_id(
    rows: list[Row], row_states: dict[int, RowStateEnum]
) -> int | None:
    """Return the id of the first row whose state is not ``done``, or ``None``."""
    for row in rows:
        if row_states.get(row.id) != RowStateEnum.done:
            return row.id
    return None


async def _render_project_list(
    request: Request,
    user: User,
    session: AsyncSession,
    **extra_context,
):
    """Fetch the user's projects and render the project list page.

    Shared by the GET route and the rename route's validation-error re-render.
    """
    result = await session.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(500)
    )
    projects = result.scalars().all()
    context = {
        "user": user,
        "projects": projects,
        "rename_error": None,
        "rename_error_project_id": None,
    }
    context.update(extra_context)
    return templates.TemplateResponse(request, "projects/list.html", context)


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
    return await _render_project_list(request, user, session)


@router.post("/{project_id}/rename")
async def project_rename(
    request: Request,
    project_id: int,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, user, session)
    name = name.strip()
    if not name:
        return await _render_project_list(
            request,
            user,
            session,
            rename_error="Project name is required.",
            rename_error_project_id=project.id,
        )
    if len(name) > 50:
        return await _render_project_list(
            request,
            user,
            session,
            rename_error="Project name must be 50 characters or fewer.",
            rename_error_project_id=project.id,
        )

    project.name = name
    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit before redirect so the follow-up GET sees the new name.
    await session.commit()

    return RedirectResponse(url="/projects/", status_code=303)


@router.post("/{project_id}/delete")
async def project_delete(
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, user, session)

    # Delete in FK-safe order: RowStates -> Rows + ElementRepetitions -> Elements -> Project.
    element_ids_sub = select(Element.id).where(Element.project_id == project.id)
    rep_ids_sub = select(ElementRepetition.id).where(
        ElementRepetition.element_id.in_(element_ids_sub)
    )
    await session.execute(
        delete(RowState).where(RowState.element_repetition_id.in_(rep_ids_sub))
    )
    await session.execute(delete(Row).where(Row.element_id.in_(element_ids_sub)))
    await session.execute(
        delete(ElementRepetition).where(
            ElementRepetition.element_id.in_(element_ids_sub)
        )
    )
    await session.execute(delete(Element).where(Element.project_id == project.id))
    await session.execute(delete(Project).where(Project.id == project.id))

    await session.commit()

    return RedirectResponse(url="/projects/", status_code=303)


@router.get("/new")
async def project_new_form(request: Request, user: User = Depends(get_current_user)):
    """Display the form for creating a new project.

    Args:
        request (Request): The incoming HTTP request.
        user (User, optional): The user making the request. Defaults to Depends(get_current_user).

    Returns:
        _type_: A template response rendering the new project form.
    """
    return templates.TemplateResponse(request, "projects/new.html", {"user": user})


@router.post("/new")
async def project_create(
    request: Request,
    name: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new project.

    Args:
        request (Request): The incoming HTTP request.
        name (str, optional): The name of the project. Defaults to Form(...).
        user (User, optional): The user making the request. Defaults to Depends(get_current_user).
        session (AsyncSession, optional): The database session. Defaults to Depends(get_session).

    Returns:
        _type_: The created project.
    """
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


async def _render_project_detail(
    request: Request,
    user: User,
    project: Project,
    session: AsyncSession,
    **extra_context,
):
    """Fetch a project's elements + row counts and render the project detail page.

    Shared by the GET route and the elements-list rename route's error re-render.
    """
    result = await session.execute(
        select(Element)
        .where(Element.project_id == project.id)
        .order_by(Element.created_at.asc())
    )
    elements = result.scalars().all()
    element_ids = [element.id for element in elements]

    row_counts = await session.execute(
        select(Row.element_id, func.count(Row.id))
        .where(Row.element_id.in_(element_ids))
        .group_by(Row.element_id)
    )
    counts_by_element = dict(row_counts.all())

    state_counts = await session.execute(
        select(ElementRepetition.element_id, RowState.state, func.count(RowState.id))
        .join(ElementRepetition, RowState.element_repetition_id == ElementRepetition.id)
        .where(ElementRepetition.element_id.in_(element_ids))
        .group_by(ElementRepetition.element_id, RowState.state)
    )
    state_counts_by_element: dict[int, dict[RowStateEnum, int]] = {}
    for element_id, state, count in state_counts.all():
        state_counts_by_element.setdefault(element_id, {})[state] = count

    elements_with_counts = []
    for element in elements:
        states = state_counts_by_element.get(element.id, {})
        elements_with_counts.append(
            (
                element,
                counts_by_element.get(element.id, 0),
                states.get(RowStateEnum.done, 0),
                states.get(RowStateEnum.in_progress, 0),
                states.get(RowStateEnum.not_started, 0),
            )
        )
    context = {
        "user": user,
        "project": project,
        "elements_with_counts": elements_with_counts,
        "rename_error": None,
        "rename_error_element_id": None,
    }
    context.update(extra_context)
    return templates.TemplateResponse(request, "projects/detail.html", context)


@router.get("/{project_id}")
async def project_detail(
    request: Request,
    project_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project = await _get_project(project_id, user, session)
    return await _render_project_detail(request, user, project, session)


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


async def _render_element_detail(
    request: Request,
    user: User,
    project: Project,
    element: Element,
    session: AsyncSession,
    **extra_context,
):
    """Fetch an element's rows/row-states and render its detail page.

    Shared by the GET route and every POST route on this page (pattern save,
    rename) so their error re-renders stay in sync with the normal view.
    """
    result = await session.execute(
        select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
    )
    rows = result.scalars().all()
    row_states = await _build_row_states(element.id, rows, session)
    current_row_id = _first_unmarked_row_id(rows, row_states)
    context = {
        "user": user,
        "project": project,
        "element": element,
        "rows": rows,
        "row_states": row_states,
        "has_rows": len(rows) > 0,
        "current_row_id": current_row_id,
    }
    context.update(extra_context)
    return templates.TemplateResponse(request, "projects/element_detail.html", context)


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
    return await _render_element_detail(request, user, project, element, session)


@router.post("/{project_id}/elements/{element_id}/rename")
async def element_rename(
    request: Request,
    project_id: int,
    element_id: int,
    name: str = Form(...),
    return_to: str = Form(default="detail"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Rename an element. `return_to` distinguishes the two places this form can be
    submitted from: the element's own detail page ("detail", the default) or the
    project's elements list ("list") — each stays on its own page afterward.
    """
    project, element = await _get_project_and_element(
        project_id, element_id, user, session
    )
    name = name.strip()
    error = None
    if not name:
        error = "Element name is required."
    elif len(name) > 50:
        error = "Element name must be 50 characters or fewer."

    if error:
        if return_to == "list":
            return await _render_project_detail(
                request,
                user,
                project,
                session,
                rename_error=error,
                rename_error_element_id=element.id,
            )
        return await _render_element_detail(
            request,
            user,
            project,
            element,
            session,
            rename_error=error,
            rename_open=True,
        )

    element.name = name
    session.add(element)
    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit before redirect so the follow-up GET sees the new name.
    await session.commit()

    if return_to == "list":
        return RedirectResponse(url=f"/projects/{project_id}", status_code=303)
    return RedirectResponse(
        url=f"/projects/{project_id}/elements/{element_id}", status_code=303
    )


@router.post("/{project_id}/elements/{element_id}/delete")
async def element_delete(
    project_id: int,
    element_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project, element = await _get_project_and_element(
        project_id, element_id, user, session
    )

    # Delete in FK-safe order: RowStates -> Rows + ElementRepetitions -> Element.
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
    await session.execute(delete(Element).where(Element.id == element.id))

    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    await session.commit()

    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


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
        return await _render_element_detail(
            request, user, project, element, session, error=error
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
    request: Request,
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

    # Commit so the fragment reflects the new state.
    await session.commit()

    return templates.TemplateResponse(
        request,
        "projects/_row.html",
        {
            "project": project,
            "element": element,
            "row": row,
            "row_states": {row.id: row_state.state},
            "current_row_id": None,
        },
        status_code=200,
    )
