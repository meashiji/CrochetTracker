from sqlalchemy import delete, select

from app.models.pattern import Row
from app.models.progress import RowState
from app.models.project import Element, ElementRepetition, Project


async def test_rename_from_list_redirects_to_project_detail(
    test_user, async_client, db_session
):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rename",
        data={"name": "Sleeve", "return_to": "list"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{project.id}"

    follow_up = await async_client.get(
        response.headers["location"], follow_redirects=False
    )
    assert follow_up.status_code == 200
    assert "Sleeve" in follow_up.text

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_rename_from_list_blank_name_rerenders_project_detail(
    test_user, async_client, db_session
):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rename",
        data={"name": "   ", "return_to": "list"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Element name is required." in response.text
    assert project.name in response.text

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_delete_removes_element_and_redirects_to_project_detail(
    test_user, async_client, db_session
):
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
        f"/projects/{project.id}/elements/{element.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{project.id}"

    remaining_element = (
        await db_session.execute(select(Element).where(Element.id == element.id))
    ).scalar_one_or_none()
    assert remaining_element is None

    remaining_rows = (
        (await db_session.execute(select(Row).where(Row.element_id == element.id)))
        .scalars()
        .all()
    )
    assert remaining_rows == []

    remaining_reps = (
        (
            await db_session.execute(
                select(ElementRepetition).where(
                    ElementRepetition.element_id == element.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining_reps == []

    remaining_states = (
        (
            await db_session.execute(
                select(RowState).where(
                    RowState.element_repetition_id.in_(
                        select(ElementRepetition.id).where(
                            ElementRepetition.element_id == element.id
                        )
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining_states == []

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_delete_other_user_sees_404_and_does_not_delete(
    test_user, second_user, async_client, db_session
):
    _second_user, second_client = second_user

    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 404

    remaining = (
        await db_session.execute(select(Element).where(Element.id == element.id))
    ).scalar_one_or_none()
    assert remaining is not None

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()
