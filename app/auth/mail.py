from functools import lru_cache

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.config import (
    MAIL_FROM,
    MAIL_FROM_NAME,
    MAIL_PASSWORD,
    MAIL_PORT,
    MAIL_SERVER,
    MAIL_USERNAME,
)


@lru_cache(maxsize=1)
def _get_mailer() -> FastMail:
    conf = ConnectionConfig(
        MAIL_USERNAME=MAIL_USERNAME,
        MAIL_PASSWORD=MAIL_PASSWORD,
        MAIL_FROM=MAIL_FROM,
        MAIL_FROM_NAME=MAIL_FROM_NAME,
        MAIL_PORT=MAIL_PORT,
        MAIL_SERVER=MAIL_SERVER,
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )
    return FastMail(conf)


async def send_magic_link_email(to_email: str, link_url: str) -> None:
    message = MessageSchema(
        subject="Your CrochetTracker login link",
        recipients=[to_email],
        body=f"Click to log in:\n\n{link_url}\n\nThis link expires in 15 minutes and can only be used once.",
        subtype=MessageType.plain,
    )
    await _get_mailer().send_message(message)
