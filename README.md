# CrochetTracker
App to organize your crochet works in progress. Track your projects, store patterns, and never lose your place in a row again.

## Local development

**Prerequisites:** Python 3.14, [uv](https://docs.astral.sh/uv/), a running Postgres instance (or tunnel to Fly Postgres).

```bash
# Install dependencies
uv sync

# Set the database URL (replace with your local Postgres credentials)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/crochet_tracker

# Required for sessions and magic-link email — app/config.py raises at startup if these are unset
export SECRET_KEY=some-local-dev-secret
export MAIL_USERNAME=your-gmail-address@gmail.com
export MAIL_PASSWORD=your-gmail-app-password
export MAIL_FROM=your-gmail-address@gmail.com

# Run the app
uv run uvicorn app.main:app --reload --port 8000
```

App will be available at `http://localhost:8000`.

Note: sign up (or request a magic link) with a real, reachable email address.
Gmail's SMTP server accepts and relays mail to any recipient without erroring —
including non-routable test domains like `@example.com` — so the app reports
success even though nothing ever arrives.

### Using Fly Postgres instead of a local database

If you don't have Postgres installed locally, tunnel to the Fly Postgres instance:

```bash
# Add fly to PATH (or use full path /home/pg/.fly/bin/fly each time)
export PATH="$HOME/.fly/bin:$PATH"

# 1. Find your DATABASE_URL
fly secrets list --app crochet-tracker
# Look for DATABASE_URL — copy the value

# 2. Open a local tunnel on port 5432 (keep this terminal open)
fly proxy 5432:5432 -a crochet-tracker-db

# 3. In another terminal — replace the host in DATABASE_URL with localhost
#    e.g. if DATABASE_URL = postgres://user:pass@crochet-tracker-db.flycast:5432/db
#    set it to:
export DATABASE_URL=postgresql://user:pass@localhost:5432/db

uv run uvicorn app.main:app --reload --port 8000
```

### Database migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Revert last migration
uv run alembic downgrade -1

# Generate a new migration after changing models
uv run alembic revision --autogenerate -m "describe your change"
```

## Deployment

Pushes to `main` deploy automatically via GitHub Actions to [Fly.io](https://fly.io).
Migrations run automatically before each deploy via `fly.toml` `release_command`.

Manual deploy:
```bash
/home/pg/.fly/bin/fly deploy
```

Live app: https://crochet-tracker.fly.dev