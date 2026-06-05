import os

_raw = os.environ["DATABASE_URL"]

if _raw.startswith("postgres://"):
    DATABASE_URL = _raw.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw.startswith("postgresql://"):
    DATABASE_URL = _raw.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw
