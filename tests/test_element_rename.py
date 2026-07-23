from sqlalchemy import delete

from app.models.project import Element, Project


async def test_rename_updates_name_and_redirects(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rename",
        data={"name": "Sleeve"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (
        response.headers["location"] == f"/projects/{project.id}/elements/{element.id}"
    )

    follow_up = await async_client.get(
        response.headers["location"], follow_redirects=False
    )
    assert follow_up.status_code == 200
    assert "Sleeve" in follow_up.text

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_rename_blank_name_shows_error_and_keeps_old_name(
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
        data={"name": "   "},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Element name is required." in response.text
    assert "Body" in response.text

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_rename_too_long_name_shows_error(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rename",
        data={"name": "x" * 51},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Element name must be 50 characters or fewer." in response.text

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_rename_other_user_sees_404_and_does_not_change_name(
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
        f"/projects/{project.id}/elements/{element.id}/rename",
        data={"name": "Hijacked"},
        follow_redirects=False,
    )

    assert response.status_code == 404

    await db_session.refresh(element)
    assert element.name == "Body"

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()
