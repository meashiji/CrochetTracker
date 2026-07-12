from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.user import User


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    user_id = request.session.get("user_id")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401)
    return user


async def get_current_user_optional(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return await session.get(User, user_id)
