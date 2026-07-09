from sqlalchemy import delete, select

from app.models.project import Element, Project
from app.models.user import User


async def test_project_detail_owner_sees_200(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.get(f"/projects/{project.id}", follow_redirects=False)

    assert response.status_code == 200
    assert "Sunset shawl" in response.text


async def test_project_detail_other_user_sees_404(test_user, async_client, db_session):
    other_user = User(email="other@example.com", password_hash="x")
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    project = Project(user_id=other_user.id, name="Not yours")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.get(f"/projects/{project.id}", follow_redirects=False)

    assert response.status_code == 404

    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.execute(delete(User).where(User.id == other_user.id))
    await db_session.commit()


async def test_add_element_redirects_to_its_detail(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/new",
        data={"name": "Sleeve"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    result = await db_session.execute(select(Element).where(Element.project_id == project.id))
    element = result.scalar_one()
    assert response.headers["location"] == f"/projects/{project.id}/elements/{element.id}"

    # test_user's teardown only deletes Project rows; Element has no cascade, so
    # it must be removed first to avoid an FK violation there.
    await db_session.execute(delete(Element).where(Element.project_id == project.id))
    await db_session.commit()


async def test_add_element_blank_name_shows_error(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/new",
        data={"name": "  "},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Element name is required." in response.text
