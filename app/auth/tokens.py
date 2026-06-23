import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import SECRET_KEY

# Provides tamper-detection (HMAC) and expiry, not confidentiality — the URL itself is the secret.
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="magic-link")


def create_magic_link_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    serialized = _serializer.dumps({"tok": token})
    return serialized, token_hash, expires_at


def verify_magic_link_token(serialized: str, max_age: int = 900) -> str | None:
    try:
        data = _serializer.loads(serialized, max_age=max_age)
        return data["tok"]
    except (BadSignature, SignatureExpired):
        return None
