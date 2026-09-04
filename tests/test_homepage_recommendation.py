from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.models.pattern import Row
from app.models.progress import RowState, RowStateEnum
from app.models.project import Element, ElementRepetition, Project


async def _add_tracked_element(db_session, project, name, states):
    element = Element(project_id=project.id, name=name, repeat_count=1)
    db_session.add(element)
    await db_session.flush()

    rows = [
        Row(element_id=element.id, position=position, content=f"Row {position}")
        for position in range(1, len(states) + 1)
    ]
    repetition = ElementRepetition(element_id=element.id, repetition_number=1)
    db_session.add_all(rows + [repetition])
    await db_session.flush()
    db_session.add_all(
        RowState(element_repetition_id=repetition.id, row_id=row.id, state=state)
        for row, state in zip(rows, states)
    )
    return element


async def _delete_homepage_projects(db_session, project_ids):
    element_ids = select(Element.id).where(Element.project_id.in_(project_ids))
    repetition_ids = select(ElementRepetition.id).where(
        ElementRepetition.element_id.in_(element_ids)
    )
    await db_session.execute(
        delete(RowState).where(RowState.element_repetition_id.in_(repetition_ids))
    )
    await db_session.execute(delete(Row).where(Row.element_id.in_(element_ids)))
    await db_session.execute(
        delete(ElementRepetition).where(ElementRepetition.element_id.in_(element_ids))
    )
    await db_session.execute(delete(Element).where(Element.project_id.in_(project_ids)))
    await db_session.execute(delete(Project).where(Project.id.in_(project_ids)))
    await db_session.commit()


def _choose_min(values):
    if all(isinstance(value, int) for value in values):
        return min(values)
    return values[0]


def _choose_max(values):
    if all(isinstance(value, int) for value in values):
        return max(values)
    return values[-1]


@pytest.fixture
async def homepage_recommendation_data(test_user, db_session):
    active_one = Project(user_id=test_user.id, name="Sunset shawl")
    active_two = Project(user_id=test_user.id, name="Garden cardigan")
    untouched = Project(user_id=test_user.id, name="New blanket")
    db_session.add_all([active_one, active_two, untouched])
    await db_session.commit()

    active_one_element = await _add_tracked_element(
        db_session,
        active_one,
        "Body",
        [RowStateEnum.in_progress, RowStateEnum.not_started],
    )
    active_two_element = await _add_tracked_element(
        db_session,
        active_two,
        "Sleeve",
        [RowStateEnum.done, RowStateEnum.not_started],
    )
    untouched_element = Element(project_id=untouched.id, name="Blanket", repeat_count=1)
    db_session.add(untouched_element)
    await db_session.commit()

    yield {
        "active_one": (active_one, active_one_element),
        "active_two": (active_two, active_two_element),
        "untouched": (untouched, untouched_element),
    }

    await _delete_homepage_projects(
        db_session, [active_one.id, active_two.id, untouched.id]
    )


async def test_homepage_recommends_started_unfinished_element(
    test_user, async_client, db_session, homepage_recommendation_data, monkeypatch
):
    """The random pool contains started unfinished projects, not untouched ones."""
    active_one, active_one_element = homepage_recommendation_data["active_one"]

    monkeypatch.setattr("app.main.random.choice", _choose_min)

    response = await async_client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert 'class="panel resume-card"' in response.text
    assert "Pick up where you left off" in response.text
    assert active_one.name in response.text
    assert active_one_element.name in response.text
    assert "×1" in response.text
    assert "2 rows" in response.text
    assert "● 0" in response.text
    assert "◐ 1" in response.text
    assert "○ 1" in response.text
    assert (
        f'href="/projects/{active_one.id}/elements/{active_one_element.id}"'
        in response.text
    )
    assert (
        "New blanket"
        not in response.text.split('class="panel resume-card"', 1)[1].split(
            "</section>", 1
        )[0]
    )


async def test_homepage_recommendation_changes_when_selection_changes(
    test_user, async_client, db_session, homepage_recommendation_data, monkeypatch
):
    """The refresh-based version can show a different eligible project."""
    active_one, _ = homepage_recommendation_data["active_one"]
    active_two, active_two_element = homepage_recommendation_data["active_two"]

    monkeypatch.setattr("app.main.random.choice", _choose_max)
    response = await async_client.get("/", follow_redirects=False)

    assert active_two.name in response.text
    assert active_two_element.name in response.text

    monkeypatch.setattr("app.main.random.choice", _choose_min)
    response = await async_client.get("/", follow_redirects=False)

    assert active_one.name in response.text


async def test_homepage_falls_back_to_last_changed_project(
    test_user, async_client, db_session
):
    """With no started work, the latest changed project is encouraged to start."""
    now = datetime.now(timezone.utc)
    older = Project(
        user_id=test_user.id,
        name="Older project",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    latest = Project(
        user_id=test_user.id,
        name="Latest project",
        created_at=now - timedelta(days=1),
        updated_at=now,
    )
    db_session.add_all([older, latest])
    await db_session.commit()
    older_element = Element(project_id=older.id, name="Older part", repeat_count=1)
    latest_element = Element(project_id=latest.id, name="Latest part", repeat_count=1)
    db_session.add_all([older_element, latest_element])
    await db_session.commit()

    response = await async_client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "A gentle nudge" in response.text
    assert "Start this project" in response.text
    assert latest.name in response.text
    assert f'href="/projects/{latest.id}/elements/{latest_element.id}"' in response.text
    assert (
        "Older project"
        not in response.text.split('class="panel resume-card"', 1)[1].split(
            "</section>", 1
        )[0]
    )

    await _delete_homepage_projects(db_session, [older.id, latest.id])
