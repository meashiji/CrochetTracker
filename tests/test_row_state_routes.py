import pytest
from sqlalchemy import delete, select

from app.models.pattern import Row
from app.models.progress import RowState, RowStateEnum
from app.models.project import Element, ElementRepetition, Project


@pytest.fixture
async def project_element_rows(test_user, async_client, db_session):
    """Create a Project + Element with rows pasted via the real route, so
    ElementRepetition/RowState rows exist exactly as production writes them.

    Teardown runs as fixture finalization (after yield), so it fires even if an
    assertion in the test body raises.
    """
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2\nRow 3"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    rows = (
        (
            await db_session.execute(
                select(Row)
                .where(Row.element_id == element.id)
                .order_by(Row.position.asc())
            )
        )
        .scalars()
        .all()
    )

    yield project, element, rows

    rep_ids_sub = select(ElementRepetition.id).where(
        ElementRepetition.element_id == element.id
    )
    await db_session.execute(
        delete(RowState).where(RowState.element_repetition_id.in_(rep_ids_sub))
    )
    await db_session.execute(delete(Row).where(Row.element_id == element.id))
    await db_session.execute(
        delete(ElementRepetition).where(ElementRepetition.element_id == element.id)
    )
    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def _row_state(db_session, row_id):
    # db_session's identity map isn't expired by the app's separate session commit, so a
    # stale cached object would otherwise be returned instead of the fresh row. Scoping
    # populate_existing to this query (rather than session-wide expire_all) avoids
    # expiring unrelated objects (e.g. test_user's `user`) still needed by teardown.
    result = await db_session.execute(
        select(RowState)
        .where(RowState.row_id == row_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def test_toggle_cycles_not_started_to_in_progress(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (
        response.headers["location"] == f"/projects/{project.id}/elements/{element.id}"
    )

    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.in_progress


async def test_toggle_full_cycle_returns_to_not_started(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]
    url = f"/projects/{project.id}/elements/{element.id}/rows/{row.id}/state"

    await async_client.post(url, follow_redirects=False)
    await async_client.post(url, follow_redirects=False)
    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.done

    await async_client.post(url, follow_redirects=False)
    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.not_started


async def test_toggle_persists_across_reload(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]

    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rows/{row.id}/state",
        follow_redirects=False,
    )

    response = await async_client.get(
        f"/projects/{project.id}/elements/{element.id}", follow_redirects=False
    )
    assert response.status_code == 200
    assert "◐" in response.text


async def test_toggle_bumps_project_updated_at(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]
    updated_before = project.updated_at

    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rows/{row.id}/state",
        follow_redirects=False,
    )

    await db_session.refresh(project)
    assert project.updated_at > updated_before


async def test_toggle_other_user_sees_404_and_does_not_change_state(
    test_user, second_user, db_session, project_element_rows
):
    _second_user, second_client = second_user
    project, element, rows = project_element_rows
    row = rows[0]

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 404
    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.not_started


async def test_toggle_wrong_element_pairing_sees_404(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]

    other_project = Project(user_id=test_user.id, name="Other project")
    db_session.add(other_project)
    await db_session.commit()

    other_element = Element(project_id=other_project.id, name="Sleeve", repeat_count=1)
    db_session.add(other_element)
    await db_session.commit()

    # row belongs to `element`, not `other_element` — the URL pairing must 404
    # even though test_user owns both projects.
    response = await async_client.post(
        f"/projects/{other_project.id}/elements/{other_element.id}/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 404

    await db_session.execute(delete(Element).where(Element.id == other_element.id))
    await db_session.execute(delete(Project).where(Project.id == other_project.id))
    await db_session.commit()
