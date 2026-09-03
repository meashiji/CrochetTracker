from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
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


async def _get_element_repetition_by_number(
    element_id: int, repetition_number: int, session: AsyncSession
) -> ElementRepetition:
    """
    Fetch an element's repetition by its 1-based repetition number.

    Args:
        element_id (int): id of the element the repetition belongs to
        repetition_number (int): 1-based repetition number within the element
        session (AsyncSession): database session

    Raises:
        HTTPException: if no such repetition exists

    Returns:
        ElementRepetition: the element repetition object
    """
    result = await session.execute(
        select(ElementRepetition).where(
            ElementRepetition.element_id == element_id,
            ElementRepetition.repetition_number == repetition_number,
        )
    )
    repetition = result.scalar_one_or_none()
    if repetition is None:
        raise HTTPException(status_code=404)
    return repetition


def _resolve_requested_rep(request: Request, element: Element) -> tuple[int, bool]:
    """Decide which repetition number an element-page request shows.

    An explicit ``?rep=N`` query param wins — a non-integer or out-of-range value
    is a bad URL and 404s (app convention). Otherwise the last-viewed cookie is
    used, silently clamped into range (stale app-written state, e.g. after a
    decrease, must not 404 the user out of their own page). Defaults to 1.

    Returns:
        tuple[int, bool]: (rep_number, is_explicit) — is_explicit is True only
        when the rep came from the query param, which is the only case where the
        last-viewed cookie gets (re)written.
    """
    rep_param = request.query_params.get("rep")
    if rep_param is not None:
        try:
            rep_number = int(rep_param)
        except ValueError:
            raise HTTPException(status_code=404)
        if rep_number < 1 or rep_number > element.repeat_count:
            raise HTTPException(status_code=404)
        return rep_number, True

    cookie_value = request.cookies.get(f"last_rep_{element.id}")
    try:
        rep_number = int(cookie_value) if cookie_value is not None else 1
    except ValueError:
        rep_number = 1
    return max(1, min(rep_number, element.repeat_count)), False


async def _build_row_progress(
    repetition_id: int, rows: list[Row], session: AsyncSession
) -> dict[int, RowState]:
    """
    Build a dictionary mapping row IDs to their full row progress for one repetition.

    Carries the whole ``RowState`` object (state + stitch_position) rather than a
    derived value, so a single query feeds both the toggle glyph and the stitch
    input.

    Args:
        repetition_id (int): id of the element repetition to fetch states for
        rows (list[Row]): list of rows to fetch states for
        session (AsyncSession): database session

    Returns:
        dict[int, RowState]: dictionary mapping row IDs to their RowState objects
    """
    if not rows:
        return {}
    result = await session.execute(
        select(RowState).where(RowState.element_repetition_id == repetition_id)
    )
    row_states = result.scalars().all()
    return {row_state.row_id: row_state for row_state in row_states}


def _first_unmarked_row_id(
    rows: list[Row], row_progress: dict[int, RowState]
) -> int | None:
    """Return the id of the first row whose state is not ``done``, or ``None``."""
    for row in rows:
        row_state = row_progress.get(row.id)
        if row_state is None or row_state.state != RowStateEnum.done:
            return row.id
    return None


async def _rep_is_complete(
    element: Element, repetition: ElementRepetition, session: AsyncSession
) -> bool:
    """Whether ``repetition`` is fully done: every row of ``element`` is ``done``.

    An element with no pasted rows has nothing to block and is treated as complete.
    """
    row_count = (
        await session.execute(
            select(func.count(Row.id)).where(Row.element_id == element.id)
        )
    ).scalar_one()
    if row_count == 0:
        return True
    done_count = (
        await session.execute(
            select(func.count(RowState.id)).where(
                RowState.element_repetition_id == repetition.id,
                RowState.state == RowStateEnum.done,
            )
        )
    ).scalar_one()
    return done_count == row_count


async def _build_rep_completion(
    element: Element, rows: list[Row], session: AsyncSession
) -> dict[int, bool]:
    """Return whether each repetition is fully done, keyed by repetition number."""
    reps_result = await session.execute(
        select(ElementRepetition)
        .where(ElementRepetition.element_id == element.id)
        .order_by(ElementRepetition.repetition_number.asc())
    )
    repetitions = reps_result.scalars().all()
    if not repetitions:
        return {}
    if not rows:
        return {repetition.repetition_number: True for repetition in repetitions}

    done_result = await session.execute(
        select(RowState.element_repetition_id, func.count(RowState.id))
        .where(
            RowState.element_repetition_id.in_(
                repetition.id for repetition in repetitions
            ),
            RowState.state == RowStateEnum.done,
        )
        .group_by(RowState.element_repetition_id)
    )
    done_by_repetition = dict(done_result.all())
    return {
        repetition.repetition_number: done_by_repetition.get(repetition.id, 0)
        == len(rows)
        for repetition in repetitions
    }


async def _can_advance_row(
    element: Element,
    repetition: ElementRepetition,
    row: Row,
    session: AsyncSession,
) -> bool:
    """Whether an advance on ``row`` in ``repetition`` is allowed by crochet order.

    Two gates must both pass, when they apply:
      1. Within-rep: the previous row (``position - 1``) in the same repetition is
         ``done``. Row 1 (no predecessor) passes this gate.
      2. Across-rep: for repetition N > 1, rep N-1 is fully ``done``. Rep 1 passes.

    Reverts (``done -> not_started``) are never gated by this helper — callers only
    use it for the not_started->in_progress and in_progress->done transitions.
    """
    prev_row = (
        await session.execute(
            select(Row).where(
                Row.element_id == element.id,
                Row.position == row.position - 1,
            )
        )
    ).scalar_one_or_none()
    if prev_row is not None:
        prev_state = (
            await session.execute(
                select(RowState).where(
                    RowState.element_repetition_id == repetition.id,
                    RowState.row_id == prev_row.id,
                )
            )
        ).scalar_one_or_none()
        if prev_state is None or prev_state.state != RowStateEnum.done:
            return False

    if repetition.repetition_number > 1:
        prev_rep = await _get_element_repetition_by_number(
            element.id, repetition.repetition_number - 1, session
        )
        if not await _rep_is_complete(element, prev_rep, session):
            return False

    return True


async def _locked_row_ids(
    rows: list[Row],
    row_progress: dict[int, RowState],
    element: Element,
    rep_number: int,
    session: AsyncSession,
) -> set[int]:
    """Ids of rows whose next transition would be a blocked advance.

    A row is locked when its state is not ``done`` AND (its immediate predecessor
    in this rep is not ``done`` OR the prior rep is not fully ``done``). ``done``
    rows are never locked (their next transition is a revert, always allowed).
    Mirrors ``_can_advance_row`` for the render path, using the already-fetched
    ``row_progress`` instead of per-row queries.
    """
    rep_unlocked = True
    if rep_number > 1:
        prev_rep = await _get_element_repetition_by_number(
            element.id, rep_number - 1, session
        )
        rep_unlocked = await _rep_is_complete(element, prev_rep, session)

    locked: set[int] = set()
    prev_done = True  # row 1 has no predecessor, so its within-rep gate passes
    for row in rows:
        row_state = row_progress.get(row.id)
        state = row_state.state if row_state is not None else None
        if state == RowStateEnum.done:
            prev_done = True
        else:
            if not prev_done or not rep_unlocked:
                locked.add(row.id)
            prev_done = False
    return locked


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

    # Commit before redirect so the follow-up GET sees the new project.
    # get_session also commits after the handler returns, but the browser can
    # send the redirect GET before that cleanup runs.
    await session.commit()

    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)


async def _render_project_detail(
    request: Request,
    user: User,
    project: Project,
    session: AsyncSession,
    **extra_context,
):
    """Fetch a project's elements + row counts and render the project detail page."""
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

    if rows:
        rep_number, is_explicit = _resolve_requested_rep(request, element)
        rep_complete_by_number = await _build_rep_completion(element, rows, session)
        first_incomplete_rep = next(
            (
                number
                for number in range(1, element.repeat_count + 1)
                if not rep_complete_by_number.get(number, False)
            ),
            None,
        )
        auto_jumped = (
            not is_explicit
            and first_incomplete_rep is not None
            and first_incomplete_rep != rep_number
        )
        if auto_jumped:
            rep_number = first_incomplete_rep
        repetition = await _get_element_repetition_by_number(
            element.id, rep_number, session
        )
        row_progress = await _build_row_progress(repetition.id, rows, session)
        locked_row_ids = await _locked_row_ids(
            rows, row_progress, element, rep_number, session
        )
    else:
        # No pattern saved yet: no repetitions exist, so there is nothing to
        # resolve or scope — show the degenerate rep 1 and never write a cookie.
        rep_number, is_explicit = 1, False
        rep_complete_by_number = {}
        auto_jumped = False
        row_progress = {}
        locked_row_ids = set()

    current_row_id = _first_unmarked_row_id(rows, row_progress)
    context = {
        "user": user,
        "project": project,
        "element": element,
        "rows": rows,
        "row_progress": row_progress,
        "locked_row_ids": locked_row_ids,
        "has_rows": len(rows) > 0,
        "current_row_id": current_row_id,
        "rep_number": rep_number,
        "rep_numbers": range(1, element.repeat_count + 1),
        "rep_complete_by_number": rep_complete_by_number,
    }
    context.update(extra_context)
    response = templates.TemplateResponse(
        request, "projects/element_detail.html", context
    )
    if is_explicit or auto_jumped:
        # Explicit rep picks and automatic jumps both pin the displayed rep. A bare
        # GET that stays on the last-viewed rep leaves its cookie untouched.
        response.set_cookie(
            f"last_rep_{element.id}",
            str(rep_number),
            max_age=31_536_000,
            samesite="lax",
            secure=True,
            httponly=True,
        )
    return response


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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Rename an element from its own detail page."""
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

    response = RedirectResponse(url=f"/projects/{project_id}", status_code=303)
    response.set_cookie(
        f"last_rep_{element.id}",
        "",
        max_age=0,
        samesite="lax",
    )
    return response


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


@router.post("/{project_id}/elements/{element_id}/repeat-count")
async def element_update_repeat_count(
    request: Request,
    project_id: int,
    element_id: int,
    repeat_count: int = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Adjust an element's repeat count, seeding or pruning reps/RowStates to
    match, then bounce to the element page."""
    project, element = await _get_project_and_element(
        project_id, element_id, user, session
    )

    if repeat_count < 1 or repeat_count > 99:
        return await _render_element_detail(
            request,
            user,
            project,
            element,
            session,
            repeat_error="Repeat count must be between 1 and 99.",
        )

    rows_result = await session.execute(
        select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
    )
    rows = rows_result.scalars().all()
    reps_result = await session.execute(
        select(ElementRepetition).where(ElementRepetition.element_id == element.id)
    )
    existing_reps = reps_result.scalars().all()

    # Invariant: whenever an element has rows, its ElementRepetition rows exactly
    # match repeat_count (numbered 1..N). With no rows there are no repetitions
    # and the stepper is a plain field update.
    #
    # The rep work is driven by the freshly fetched reps (their max number), NOT
    # the element field: under a double-submit race the field can lag the actual
    # reps, and seeding from the field would re-insert existing repetition numbers
    # and trip the (element_id, repetition_number) unique constraint.
    existing_max = max((rep.repetition_number for rep in existing_reps), default=0)

    try:
        if rows:
            if repeat_count > existing_max:
                new_reps = [
                    ElementRepetition(element_id=element.id, repetition_number=i)
                    for i in range(existing_max + 1, repeat_count + 1)
                ]
                for rep in new_reps:
                    session.add(rep)
                await session.flush()  # populate PKs before RowState inserts reference them
                # Seed via a single bulk Core insert. ORM adds would hold every
                # (rep, row) RowState in the session identity map until commit
                # (reps × rows objects) — an OOM risk for a pathological 1→99
                # increase on a huge pattern. Core insert bypasses the identity
                # map. `state` is passed explicitly; the `updated_at` column
                # default still applies.
                await session.execute(
                    insert(RowState),
                    [
                        {
                            "element_repetition_id": rep.id,
                            "row_id": row.id,
                            "state": RowStateEnum.not_started,
                        }
                        for rep in new_reps
                        for row in rows
                    ],
                )
            elif repeat_count < existing_max:
                removed_rep_ids = [
                    rep.id
                    for rep in existing_reps
                    if rep.repetition_number > repeat_count
                ]
                if removed_rep_ids:
                    # FK-safe order: RowStates before their ElementRepetitions.
                    await session.execute(
                        delete(RowState).where(
                            RowState.element_repetition_id.in_(removed_rep_ids)
                        )
                    )
                    await session.execute(
                        delete(ElementRepetition).where(
                            ElementRepetition.id.in_(removed_rep_ids)
                        )
                    )

        element.repeat_count = repeat_count
        session.add(element)
        project.updated_at = datetime.now(timezone.utc)
        session.add(project)

        # Commit before redirect so the follow-up GET sees the new rep structure.
        await session.commit()
    except IntegrityError:
        # Graceful degradation on a duplicate-seed race (e.g. two concurrent + or
        # − submits): the other request already landed its reps — roll back and
        # bounce to the element page rather than 500.
        await session.rollback()
        return RedirectResponse(
            url=f"/projects/{project_id}/elements/{element_id}", status_code=303
        )

    # Bare URL, no ?rep= — a stale last-rep cookie is clamped on the next read
    # rather than 404ing the user out of their own page.
    if request.headers.get("HX-Request"):
        # HTMX request: swap just the stepper (the rep pills come along via an
        # out-of-band swap) so the page and its scroll position stay put — a
        # redirect would reload and re-run the auto-scroll to the current row.
        # Re-fetch post-commit: the objects loaded above are expired and lazy
        # loads would raise in async.
        project, element = await _get_project_and_element(
            project_id, element_id, user, session
        )
        if rows:
            cookie_value = request.cookies.get(f"last_rep_{element.id}")
            try:
                pinned_rep = int(cookie_value) if cookie_value is not None else 1
            except ValueError:
                pinned_rep = 1
            if pinned_rep > element.repeat_count:
                # The rep currently on screen was just pruned — swapping only
                # the stepper+pills would leave a stale row list up, so make
                # the client reload the whole page.  Use HX-Redirect (not
                # HX-Refresh) to land on the bare element URL without ?rep=;
                # the stale cookie will be silently clamped by
                # _resolve_requested_rep instead of 404ing on an out-of-range
                # explicit query param.
                return Response(
                    status_code=200,
                    headers={
                        "HX-Redirect": f"/projects/{project_id}/elements/{element_id}"
                    },
                )
        rep_number, _ = _resolve_requested_rep(request, element)
        rep_complete_by_number = await _build_rep_completion(element, rows, session)
        return templates.TemplateResponse(
            request,
            "projects/_repeat_stepper.html",
            {
                "project": project,
                "element": element,
                "has_rows": bool(rows),
                "rep_number": rep_number,
                "rep_numbers": range(1, element.repeat_count + 1),
                "rep_complete_by_number": rep_complete_by_number,
            },
        )
    return RedirectResponse(
        url=f"/projects/{project_id}/elements/{element_id}", status_code=303
    )


@router.post(
    "/{project_id}/elements/{element_id}/reps/{rep_number}/rows/{row_id}/state"
)
async def row_state_toggle(
    request: Request,
    project_id: int,
    element_id: int,
    rep_number: int,
    row_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    project, element, row = await _get_project_element_and_row(
        project_id, element_id, row_id, user, session
    )
    repetition = await _get_element_repetition_by_number(
        element.id, rep_number, session
    )
    result = await session.execute(
        select(RowState).where(
            RowState.element_repetition_id == repetition.id,
            RowState.row_id == row.id,
        )
    )
    row_state = result.scalar_one_or_none()
    if row_state is None:
        raise HTTPException(status_code=404)

    next_state = ROW_STATE_CYCLE[row_state.state]
    # Crochet order: only advances (toward done) are gated; reverts to not_started
    # are always allowed (even for an orphaned done row). A blocked advance leaves
    # state unchanged and no project.updated_at bump.
    if next_state in (RowStateEnum.in_progress, RowStateEnum.done):
        if not await _can_advance_row(element, repetition, row, session):
            return templates.TemplateResponse(
                request,
                "projects/_row.html",
                {
                    "project": project,
                    "element": element,
                    "row": row,
                    "row_progress": {row.id: row_state},
                    "locked_row_ids": {row.id},
                    "current_row_id": None,
                    "rep_number": rep_number,
                },
                status_code=200,
            )

    row_state.state = next_state
    session.add(row_state)

    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit so the fragment reflects the new state.
    await session.commit()

    # The changed row's lock state affects the NEXT row (its predecessor changed),
    # so swap that row out-of-band too — otherwise it stale-locks until reload.
    next_row = (
        await session.execute(
            select(Row).where(
                Row.element_id == element.id, Row.position == row.position + 1
            )
        )
    ).scalar_one_or_none()
    rows_result = await session.execute(
        select(Row).where(Row.element_id == element.id).order_by(Row.position.asc())
    )
    rows = rows_result.scalars().all()
    rep_complete_by_number = await _build_rep_completion(element, rows, session)

    def _row_fragment(rendered_row, rendered_state, rendered_locked, *, oob=False):
        return templates.env.get_template("projects/_row.html").render(
            project=project,
            element=element,
            row=rendered_row,
            row_progress={rendered_row.id: rendered_state},
            locked_row_ids={rendered_row.id} if rendered_locked else set(),
            current_row_id=None,
            rep_number=rep_number,
            oob=oob,
        )

    changed_row_locked = (
        next_state == RowStateEnum.not_started
        and not await _can_advance_row(element, repetition, row, session)
    )
    body = _row_fragment(row, row_state, rendered_locked=changed_row_locked)
    if next_row is not None:
        rep_unlocked = True
        if repetition.repetition_number > 1:
            prev_rep = await _get_element_repetition_by_number(
                element.id, repetition.repetition_number - 1, session
            )
            rep_unlocked = await _rep_is_complete(element, prev_rep, session)
        next_row_state = (
            await session.execute(
                select(RowState).where(
                    RowState.element_repetition_id == repetition.id,
                    RowState.row_id == next_row.id,
                )
            )
        ).scalar_one_or_none()
        # A missing RowState behaves as not_started (i.e. not done).
        next_done = (
            next_row_state is not None and next_row_state.state == RowStateEnum.done
        )
        # next row is locked iff it's not done AND (its predecessor (this row) isn't
        # done OR the prior rep isn't complete) — mirrors _locked_row_ids.
        next_locked = not next_done and (
            row_state.state != RowStateEnum.done or not rep_unlocked
        )
        if next_row_state is None:
            next_row_state = RowState(
                element_repetition_id=repetition.id,
                row_id=next_row.id,
                state=RowStateEnum.not_started,
            )
        body += _row_fragment(next_row, next_row_state, next_locked, oob=True)

    body += templates.env.get_template("projects/_rep_pills.html").render(
        element=element,
        rep_number=rep_number,
        rep_numbers=range(1, element.repeat_count + 1),
        rep_complete_by_number=rep_complete_by_number,
        oob=True,
    )

    return HTMLResponse(body, status_code=200)


@router.post(
    "/{project_id}/elements/{element_id}/reps/{rep_number}/rows/{row_id}/stitch"
)
async def row_update_stitch_position(
    request: Request,
    project_id: int,
    element_id: int,
    rep_number: int,
    row_id: int,
    stitch_position: str = Form(default=""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Persist a row's stitch position (blank clears) and return the updated
    row fragment; invalid input re-renders the row with error styling."""
    project, element, row = await _get_project_element_and_row(
        project_id, element_id, row_id, user, session
    )
    repetition = await _get_element_repetition_by_number(
        element.id, rep_number, session
    )
    result = await session.execute(
        select(RowState).where(
            RowState.element_repetition_id == repetition.id,
            RowState.row_id == row.id,
        )
    )
    row_state = result.scalar_one_or_none()
    if row_state is None:
        raise HTTPException(status_code=404)

    locked_row_ids = (
        {row.id}
        if row_state.state != RowStateEnum.done
        and not await _can_advance_row(element, repetition, row, session)
        else set()
    )

    def _render_fragment(*, stitch_error: bool = False):
        return templates.TemplateResponse(
            request,
            "projects/_row.html",
            {
                "project": project,
                "element": element,
                "row": row,
                "row_progress": {row.id: row_state},
                "locked_row_ids": locked_row_ids,
                "current_row_id": None,
                "rep_number": rep_number,
                "stitch_error": stitch_error,
            },
            status_code=200,
        )

    value = stitch_position.strip()
    if value == "":
        row_state.stitch_position = None
    elif not value.isascii() or not value.isdigit() or not (1 <= int(value) <= 9999):
        # Invalid input: re-render the row with the error treatment and write
        # nothing — the DB value is left untouched. `.isascii()` guards against
        # Unicode superscript digits whose `.isdigit()` is True but that
        # `int()` would reject.
        return _render_fragment(stitch_error=True)
    else:
        row_state.stitch_position = int(value)

    session.add(row_state)

    project.updated_at = datetime.now(timezone.utc)
    session.add(project)

    # Commit so the fragment reflects the new value.
    await session.commit()

    return _render_fragment()
