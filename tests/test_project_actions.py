from sqlalchemy import delete, select

from app.models.pattern import Row
from app.models.progress import RowState
from app.models.project import Element, ElementRepetition, Project


async def test_rename_updates_name_and_redirects(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/rename",
        data={"name": "Winter shawl"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/projects/"

    follow_up = await async_client.get("/projects/", follow_redirects=False)
    assert follow_up.status_code == 200
    assert "Winter shawl" in follow_up.text

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_rename_blank_name_shows_error_and_keeps_old_name(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/rename",
        data={"name": "   "},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Project name is required." in response.text
    assert "Sunset shawl" in response.text

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_rename_too_long_name_shows_error(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/rename",
        data={"name": "x" * 51},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Project name must be 50 characters or fewer." in response.text

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_rename_other_user_sees_404_and_does_not_change_name(
    test_user, second_user, async_client, db_session
):
    _second_user, second_client = second_user

    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await second_client.post(
        f"/projects/{project.id}/rename",
        data={"name": "Hijacked"},
        follow_redirects=False,
    )

    assert response.status_code == 404

    await db_session.refresh(project)
    assert project.name == "Sunset shawl"

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_delete_removes_project_and_redirects(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/projects/"

    remaining = (
        await db_session.execute(select(Project).where(Project.id == project.id))
    ).scalar_one_or_none()
    assert remaining is None


async def test_delete_removes_elements_rows_and_row_states(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    save_response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2"},
        follow_redirects=False,
    )
    assert save_response.status_code == 303

    response = await async_client.post(
        f"/projects/{project.id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303

    remaining_elements = (
        await db_session.execute(select(Element).where(Element.project_id == project.id))
    ).scalars().all()
    assert remaining_elements == []

    remaining_rows = (
        await db_session.execute(select(Row).where(Row.element_id == element.id))
    ).scalars().all()
    assert remaining_rows == []

    remaining_reps = (
        await db_session.execute(
            select(ElementRepetition).where(ElementRepetition.element_id == element.id)
        )
    ).scalars().all()
    assert remaining_reps == []

    remaining_states = (
        await db_session.execute(
            select(RowState).where(
                RowState.element_repetition_id.in_(
                    select(ElementRepetition.id).where(ElementRepetition.element_id == element.id)
                )
            )
        )
    ).scalars().all()
    assert remaining_states == []


async def test_delete_other_user_sees_404_and_does_not_delete(
    test_user, second_user, async_client, db_session
):
    _second_user, second_client = second_user

    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await second_client.post(
        f"/projects/{project.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 404

    remaining = (
        await db_session.execute(select(Project).where(Project.id == project.id))
    ).scalar_one_or_none()
    assert remaining is not None

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()
