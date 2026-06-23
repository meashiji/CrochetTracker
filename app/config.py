import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_raw = os.environ["DATABASE_URL"]

if _raw.startswith("postgres://"):
    _raw = _raw.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw.startswith("postgresql://"):
    _raw = _raw.replace("postgresql://", "postgresql+asyncpg://", 1)

# asyncpg's SQLAlchemy dialect doesn't accept the libpq "sslmode" kwarg,
# but it does accept "ssl" with the same string values (e.g. "disable").
_parts = urlsplit(_raw)
_query = urlencode([("ssl" if k == "sslmode" else k, v) for k, v in parse_qsl(_parts.query)])
DATABASE_URL = urlunsplit((_parts.scheme, _parts.netloc, _parts.path, _query, _parts.fragment))

SECRET_KEY = os.environ["SECRET_KEY"]

MAIL_USERNAME = os.environ["MAIL_USERNAME"]
MAIL_PASSWORD = os.environ["MAIL_PASSWORD"]
MAIL_FROM = os.environ["MAIL_FROM"]
MAIL_FROM_NAME = os.environ.get("MAIL_FROM_NAME", "CrochetTracker")
MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
