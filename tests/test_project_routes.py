from sqlalchemy import delete, select

from app.models.pattern import Row
from app.models.progress import RowState
from app.models.project import Element, ElementRepetition, Project
from app.models.user import User


async def test_project_detail_owner_sees_200(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    response = await async_client.get(f"/projects/{project.id}", follow_redirects=False)

    assert response.status_code == 200
    assert "Sunset shawl" in response.text


async def test_project_detail_shows_row_count(test_user, async_client, db_session):
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    db_session.add_all(
        Row(element_id=element.id, position=i, content=f"Row {i}") for i in range(1, 4)
    )
    await db_session.commit()

    response = await async_client.get(f"/projects/{project.id}", follow_redirects=False)

    assert response.status_code == 200
    assert "3 rows" in response.text

    await db_session.execute(delete(Row).where(Row.element_id == element.id))
    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_project_detail_shows_row_state_breakdown(
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
        data={"pattern_text": "Row 1\nRow 2\nRow 3"},
        follow_redirects=False,
    )
    assert save_response.status_code == 303

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

    # Row 1 -> done (two toggles), Row 2 -> in_progress (one toggle), Row 3 stays not_started.
    for _ in range(2):
        await async_client.post(
            f"/projects/{project.id}/elements/{element.id}/rows/{rows[0].id}/state",
            follow_redirects=False,
        )
    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/rows/{rows[1].id}/state",
        follow_redirects=False,
    )

    response = await async_client.get(f"/projects/{project.id}", follow_redirects=False)

    assert response.status_code == 200
    assert "3 rows" in response.text
    assert "● 1" in response.text
    assert "◐ 1" in response.text
    assert "○ 1" in response.text

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
    result = await db_session.execute(
        select(Element).where(Element.project_id == project.id)
    )
    element = result.scalar_one()
    assert (
        response.headers["location"] == f"/projects/{project.id}/elements/{element.id}"
    )

    follow_up = await async_client.get(
        response.headers["location"], follow_redirects=False
    )
    assert follow_up.status_code == 200

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


async def test_element_detail_other_user_sees_404(test_user, second_user, db_session):
    _second_user, second_client = second_user

    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await second_client.get(
        f"/projects/{project.id}/elements/{element.id}", follow_redirects=False
    )

    assert response.status_code == 404

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_element_save_pattern_other_user_sees_404(
    test_user, second_user, db_session
):
    _second_user, second_client = second_user

    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2"},
        follow_redirects=False,
    )

    assert response.status_code == 404

    rows = (
        (await db_session.execute(select(Row).where(Row.element_id == element.id)))
        .scalars()
        .all()
    )
    assert rows == []

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def test_element_detail_wrong_project_sees_404(
    test_user, async_client, db_session
):
    project_a = Project(user_id=test_user.id, name="Project A")
    project_b = Project(user_id=test_user.id, name="Project B")
    db_session.add(project_a)
    db_session.add(project_b)
    await db_session.commit()

    element_of_b = Element(project_id=project_b.id, name="Body", repeat_count=1)
    db_session.add(element_of_b)
    await db_session.commit()

    # Same owner as project_a, but element_of_b belongs to project_b — the URL pairing
    # (project_a.id, element_of_b.id) must still 404 even though test_user owns both.
    response = await async_client.get(
        f"/projects/{project_a.id}/elements/{element_of_b.id}", follow_redirects=False
    )

    assert response.status_code == 404

    await db_session.execute(delete(Element).where(Element.id == element_of_b.id))
    await db_session.commit()
