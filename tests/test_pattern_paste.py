import pytest
from sqlalchemy import delete, select

from app.models.pattern import Row
from app.models.progress import RowState, RowStateEnum
from app.models.project import Element, ElementRepetition, Project
from app.routes.projects import MAX_PATTERN_LENGTH
from app.services.pattern import parse_pattern


@pytest.fixture
async def project_and_element(test_user, db_session):
    """Create a Project + Element owned by test_user; tear down unconditionally.

    Teardown runs as fixture finalization (after the test's `yield` point), so it
    fires even if an assertion in the test body raises — a plain "cleanup at the end
    of the test function" would leave Row/ElementRepetition/RowState/Element rows
    behind on failure, which then breaks test_user's own teardown (FK violation on
    Project delete) and leaks the User row into subsequent tests.
    """
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    yield project, element

    rep_ids_sub = select(ElementRepetition.id).where(ElementRepetition.element_id == element.id)
    await db_session.execute(delete(RowState).where(RowState.element_repetition_id.in_(rep_ids_sub)))
    await db_session.execute(delete(Row).where(Row.element_id == element.id))
    await db_session.execute(delete(ElementRepetition).where(ElementRepetition.element_id == element.id))
    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_pattern_paste_creates_matching_db_records(
    test_user, async_client, db_session, project_and_element
):
    project, element = project_and_element
    pattern_text = "Row 1\nRow 2\nRow 3"

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": pattern_text},
        follow_redirects=False,
    )
    assert response.status_code == 303

    expected = parse_pattern(pattern_text)

    rows = (
        await db_session.execute(
            select(Row).where(Row.element_id == element.id).order_by(Row.position)
        )
    ).scalars().all()
    assert len(rows) == len(expected)
    for row, (pos, content) in zip(rows, expected):
        assert row.position == pos
        assert row.content == content

    reps = (
        await db_session.execute(
            select(ElementRepetition).where(ElementRepetition.element_id == element.id)
        )
    ).scalars().all()
    assert len(reps) == 1
    assert reps[0].repetition_number == 1

    states = (
        await db_session.execute(
            select(RowState).where(RowState.element_repetition_id == reps[0].id)
        )
    ).scalars().all()
    assert len(states) == len(rows)
    assert all(s.state == RowStateEnum.not_started for s in states)


async def test_pattern_paste_bumps_project_updated_at(
    test_user, async_client, db_session, project_and_element
):
    project, element = project_and_element
    updated_before = project.updated_at

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.refresh(project)
    assert project.updated_at > updated_before


async def test_pattern_repaste_replaces_rows(
    test_user, async_client, db_session, project_and_element
):
    project, element = project_and_element

    first_response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2\nRow 3"},
        follow_redirects=False,
    )
    assert first_response.status_code == 303

    original_rows = (
        await db_session.execute(select(Row).where(Row.element_id == element.id))
    ).scalars().all()
    original_ids = {row.id for row in original_rows}
    assert len(original_ids) == 3

    second_response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "New A\nNew B"},
        follow_redirects=False,
    )
    assert second_response.status_code == 303

    new_rows = (
        await db_session.execute(
            select(Row).where(Row.element_id == element.id).order_by(Row.position)
        )
    ).scalars().all()
    new_ids = {row.id for row in new_rows}

    assert len(new_rows) == 2
    assert [row.content for row in new_rows] == ["New A", "New B"]
    assert new_ids.isdisjoint(original_ids)

    reps = (
        await db_session.execute(
            select(ElementRepetition).where(ElementRepetition.element_id == element.id)
        )
    ).scalars().all()
    assert len(reps) == 1

    states = (
        await db_session.execute(
            select(RowState).where(RowState.element_repetition_id == reps[0].id)
        )
    ).scalars().all()
    assert len(states) == len(new_rows)


async def test_pattern_paste_blank_result_writes_nothing(
    test_user, async_client, db_session, project_and_element
):
    project, element = project_and_element

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "   \n   \n"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Pattern text produced no rows" in response.text

    rows = (
        await db_session.execute(select(Row).where(Row.element_id == element.id))
    ).scalars().all()
    assert rows == []


async def test_pattern_paste_oversized_writes_nothing(
    test_user, async_client, db_session, project_and_element
):
    project, element = project_and_element
    oversized = "x" * (MAX_PATTERN_LENGTH + 1)

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": oversized},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Pattern too large" in response.text

    rows = (
        await db_session.execute(select(Row).where(Row.element_id == element.id))
    ).scalars().all()
    assert rows == []


async def test_pattern_paste_rejected_repaste_leaves_existing_rows_intact(
    test_user, async_client, db_session, project_and_element
):
    project, element = project_and_element

    first_response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2"},
        follow_redirects=False,
    )
    assert first_response.status_code == 303

    original_rows = (
        await db_session.execute(
            select(Row).where(Row.element_id == element.id).order_by(Row.position)
        )
    ).scalars().all()
    original = [(row.id, row.position, row.content) for row in original_rows]
    assert len(original) == 2

    rejected_response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "   "},
        follow_redirects=False,
    )
    assert rejected_response.status_code == 200
    assert "Pattern text produced no rows" in rejected_response.text

    rows_after = (
        await db_session.execute(
            select(Row).where(Row.element_id == element.id).order_by(Row.position)
        )
    ).scalars().all()
    after = [(row.id, row.position, row.content) for row in rows_after]
    assert after == original


async def test_pattern_paste_other_user_sees_404_and_writes_nothing(
    test_user, second_user, db_session, project_and_element
):
    _second_user, second_client = second_user
    project, element = project_and_element

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2"},
        follow_redirects=False,
    )
    assert response.status_code == 404

    rows = (
        await db_session.execute(select(Row).where(Row.element_id == element.id))
    ).scalars().all()
    assert rows == []
