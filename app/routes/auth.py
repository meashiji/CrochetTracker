from datetime import datetime, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mail import send_magic_link_email
from app.auth.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.auth.tokens import create_magic_link_token, verify_magic_link_token
from app.db import get_session
from app.models.magic_link_token import MagicLinkToken
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
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {"error": "Password must be at least 8 characters."},
        )

    email = email.strip().lower()
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
    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    has_password = user is not None and user.password_hash is not None
    password_hash = user.password_hash if has_password else DUMMY_PASSWORD_HASH
    if not has_password or not verify_password(password, password_hash):
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


@router.get("/magic-link")
async def magic_link_request_form(request: Request):
    return templates.TemplateResponse(request, "auth/magic_link_request.html", {})


@router.post("/magic-link")
async def magic_link_request(
    request: Request,
    email: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email)
        session.add(user)
        await session.flush()

    serialized, token_hash, expires_at = create_magic_link_token()
    token_row = MagicLinkToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(token_row)
    await session.commit()

    verify_url = str(request.base_url).rstrip("/") + f"/auth/magic-link/verify?token={serialized}"
    await send_magic_link_email(email, verify_url)

    return templates.TemplateResponse(request, "auth/magic_link_sent.html", {})


@router.get("/magic-link/verify")
async def magic_link_verify(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_session),
):
    raw_token = verify_magic_link_token(token)
    if raw_token is None:
        return templates.TemplateResponse(request, "auth/magic_link_error.html", {})

    token_hash = sha256(raw_token.encode()).hexdigest()
    result = await session.execute(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
    )
    token_row = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if token_row is None or token_row.used_at is not None or token_row.expires_at < now:
        return templates.TemplateResponse(request, "auth/magic_link_error.html", {})

    token_row.used_at = now
    await session.commit()

    request.session["user_id"] = token_row.user_id
    return RedirectResponse(url="/", status_code=303)
