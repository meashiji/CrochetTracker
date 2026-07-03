import pytest
from sqlalchemy import delete

from app.models.user import User


async def test_unauthenticated_request_redirects(async_client):
    response = await async_client.get("/projects/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/login")


async def test_tampered_session_cookie_redirects(async_client):
    async_client.cookies.set("session", "not-a-valid-hmac-signed-payload")
    response = await async_client.get("/projects/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/login")


async def test_valid_session_returns_200(test_user, async_client):
    response = await async_client.get("/projects/", follow_redirects=False)
    assert response.status_code == 200


async def test_orphaned_user_id_returns_401(test_user, async_client, db_session):
    await db_session.execute(delete(User).where(User.id == test_user.id))
    await db_session.commit()

    response = await async_client.get("/projects/", follow_redirects=False)
    assert response.status_code == 401
