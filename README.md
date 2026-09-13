# CrochetTracker
App to organize your crochet works in progress. Track your projects, store patterns, and never lose your place in a row again.

## What it does

- Create, rename, and delete projects and project elements.
- Paste a plain-text pattern and view it as a list of rows.
- Track each row as not started, in progress, or done.
- Track repeated elements independently and record a stitch position.
- Resume work at the first unfinished row when returning to a project.
- Keep projects private to the signed-in user.
- Use email/password or magic-link authentication and an in-app stitch reference.

PDF import, offline use, sharing, and team workspaces are intentionally out of scope for v1.

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

### Running the tests

Tests use a separate PostgreSQL database and create/drop their tables for the test
session. Never point `DATABASE_URL` at a production database.

```bash
# Create the test database once (adjust the user, password, and port as needed)
createdb -h 127.0.0.1 -p 5432 -U postgres crochet_tracker_test

# Use the test database for this shell only
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/crochet_tracker_test
uv run pytest -q
```

The CI test job starts PostgreSQL automatically. The migration quality gate runs
`alembic upgrade head` followed by `alembic check` on a fresh database.

Browser-level tests use Playwright and the same test database. After setting the
test environment variables above, prepare the schema and run them with:

```bash
uv run alembic upgrade head
npm ci
npx playwright install chromium
npx playwright test
```

The E2E scenarios create unique projects, verify row-state persistence after a
reload, and clean up their data.

### Using Fly Postgres instead of a local database

If you don't have Postgres installed locally, tunnel to the Fly Postgres instance:

```bash
# Ensure the Fly CLI is installed and available on PATH.
export PATH="$HOME/.fly/bin:$PATH"

# 1. Check that the app has a DATABASE_URL secret
fly secrets list --app crochet-tracker
# Fly displays secret names and digests, not secret values. Use the database
# credentials from your secure password store for local development.

# 2. Open a local tunnel on port 5432 (keep this terminal open)
fly proxy 5432:5432 -a crochet-tracker-db

# 3. In another terminal, replace the host in your DATABASE_URL with localhost
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

Pushes to `main` run the migration-drift check, test suite, and dependency audit in
GitHub Actions, then deploy automatically to [Fly.io](https://fly.io). Migrations
run automatically before each deploy via the `fly.toml` `release_command`.

Production requires these Fly secrets: `DATABASE_URL`, `SECRET_KEY`,
`MAIL_USERNAME`, `MAIL_PASSWORD`, and `MAIL_FROM`. Do not commit their values.
The production Fly Postgres instance is configured to stay available instead of
scaling to zero on idle.

Manual deploy:
```bash
fly deploy
```

Live app: https://crochet-tracker.fly.dev

## Project documentation

- Product requirements: `context/foundation/prd.md`
- Delivery roadmap: `context/foundation/roadmap.md`
- Test strategy and risk map: `context/foundation/test-plan.md`
