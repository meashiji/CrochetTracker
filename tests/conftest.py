import asyncio
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://crochet_tracker:dupa123@127.0.0.1:5433/crochet_tracker_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("MAIL_USERNAME", "test")
os.environ.setdefault("MAIL_PASSWORD", "test")
os.environ.setdefault("MAIL_FROM", "test@example.com")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.main import app

_TEST_DATABASE_URL = os.environ["DATABASE_URL"]
_test_engine = create_async_engine(_TEST_DATABASE_URL)
_TestSessionLocal = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session", autouse=True)
def _create_test_tables():
    """Create all tables once per test session; drop them on teardown."""

    async def _up() -> None:
        e = create_async_engine(_TEST_DATABASE_URL)
        async with e.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await e.dispose()

    async def _down() -> None:
        e = create_async_engine(_TEST_DATABASE_URL)
        async with e.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await e.dispose()

    asyncio.run(_up())
    yield
    asyncio.run(_down())


@pytest.fixture(autouse=True)
async def _dispose_engines():
    """Dispose asyncpg connection pools after each test.

    pytest-asyncio creates a fresh event loop per test (function scope). asyncpg
    connections are loop-bound, so any pool connection from the previous test's loop
    causes 'Future attached to a different loop' when the next test starts. Disposing
    both engines forces fresh connections in the current test's event loop.
    """
    yield
    from app.db import engine as _app_engine
    await _app_engine.dispose()
    await _test_engine.dispose()


@pytest.fixture
async def db_session():
    async with _TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        yield client


@pytest.fixture
async def test_user(async_client, db_session):
    """Create a test user via signup (sets session cookie on async_client), yield the User row."""
    from sqlalchemy import delete, select
    from app.models.user import User

    response = await async_client.post(
        "/auth/signup",
        data={"email": "test@example.com", "password": "testpassword123"},
        follow_redirects=False,
    )
    assert response.status_code == 303, f"Signup failed: {response.status_code}"

    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    user = result.scalar_one()
    yield user

    await db_session.execute(delete(User).where(User.id == user.id))
    await db_session.commit()
