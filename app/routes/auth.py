from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password, verify_password
from app.db import get_session
from app.models.user import User

router = APIRouter(prefix="/auth")
templates = Jinja2Templates(directory="app/templates")


@router.get("/signup")
async def signup_form(request: Request):
    return templates.TemplateResponse(request, "auth/signup.html", {})


@router.post("/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {"error": "An account with this email already exists."},
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is not None and user.password_hash is None:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "This account has no password set. Use magic-link sign-in instead."},
        )

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid email or password."},
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=303)
