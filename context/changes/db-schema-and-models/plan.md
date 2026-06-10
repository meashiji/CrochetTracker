# Database Schema + SQLModel Models Implementation Plan

## Overview

Stand up the complete database layer for CrochetTracker: six SQLModel entity models, an async database engine wired to Fly Postgres, and Alembic migrations running automatically via Fly's `release_command` on every deploy. This is F-01 — the foundation everything else builds on.

## Current State Analysis

- `pyproject.toml` has FastAPI + uvicorn only; no SQLModel, asyncpg, or Alembic.
- `app/models/` and `app/routes/` are empty directories.
- No `app/db.py` or `app/config.py` exists.
- Fly Postgres is provisioned and `DATABASE_URL` is already set as a Fly secret (via `fly postgres attach`).
- Fly delivers the URL in `postgres://` format — this must be normalised to `postgresql+asyncpg://` for the async driver.

## Desired End State

Six SQLModel entity tables exist in Fly Postgres, created by a clean Alembic migration that runs automatically before each deploy. The app can open an async DB session from any route via a FastAPI dependency. `uv run alembic upgrade head` applies the migration; `uv run alembic downgrade -1` reverts it.

### Key Discoveries

- Fly Postgres `DATABASE_URL` uses the `postgres://` scheme — asyncpg requires `postgresql+asyncpg://`. Normalisation must happen before the engine is created (`config.py`).
- SQLModel async session requires `expire_on_commit=False` on the `async_sessionmaker` — without it, accessing model attributes after `await session.commit()` raises `MissingGreenlet` errors.
- `UniqueConstraint` on multiple columns requires `from sqlalchemy import UniqueConstraint` and `__table_args__` — SQLModel's `Field` only handles single-column constraints.
- Alembic's asyncio runner pattern (shipped in Alembic 1.12+) lets `alembic upgrade head` work against an asyncpg engine without adding a separate psycopg2 dependency.
- Pool size on a `shared-cpu-1x / 256 MB` VM: keep `pool_size=3, max_overflow=0` to avoid OOM under concurrent HTMX requests.

## What We're NOT Doing

- No auth fields on User (hashed_password, magic_link_token) — those belong to F-02.
- No route handlers, no Jinja2 templates — this plan is schema and engine only.
- No seed data or fixtures.
- No RowState records created here — F-01 only defines the schema; RowState rows are inserted eagerly by the pattern-paste handler in S-01.

## Implementation Approach

Three sequential phases: (1) add packages and wire the async engine, (2) define the six models, (3) initialise Alembic and generate the initial migration. Each phase has a runnable verification step before moving on.

## Critical Implementation Details

- **URL normalisation** — `DATABASE_URL` from Fly starts with `postgres://`. Replace the scheme prefix to `postgresql+asyncpg://` before passing to `create_async_engine`. Do not rely on SQLAlchemy's dialect auto-detection; the scheme must be explicit.
- **`expire_on_commit=False`** — required on `async_sessionmaker`. Without it, accessing any attribute on a model instance after `await session.commit()` (the common route handler pattern) raises a `MissingGreenlet` / lazy-load error that only surfaces at runtime, not at import time.
- **Alembic `target_metadata`** — `env.py` must import all SQLModel models before `target_metadata = SQLModel.metadata` is set, otherwise `alembic revision --autogenerate` produces an empty migration.

---

## Phase 1: Dependencies + Configuration + DB Engine

### Overview

Add the three new packages to `pyproject.toml`, create `app/config.py` to read and normalise `DATABASE_URL`, and create `app/db.py` with the async engine, session factory, and FastAPI dependency.

### Changes Required

#### 1. `pyproject.toml` — add dependencies

**File:** `pyproject.toml`

**Intent:** Add `sqlmodel`, `asyncpg`, and `alembic` as runtime dependencies so `uv sync` pulls them into the lockfile and the Docker image.

**Contract:** Three new entries in the `dependencies` list — `sqlmodel`, `asyncpg`, `alembic`. No version pins; `uv.lock` freezes the resolved versions. Run `uv add sqlmodel asyncpg alembic` to append them and regenerate the lock.

#### 2. `app/config.py` — settings and URL normalisation

**File:** `app/config.py` (new file)

**Intent:** Centralise environment variable reading and perform the `postgres://` → `postgresql+asyncpg://` scheme transformation so the rest of the app always receives a valid asyncpg URL.

**Contract:** Exports a single `settings` object (or module-level constant `DATABASE_URL: str`) derived from `os.environ["DATABASE_URL"]`. The transformation replaces only the scheme prefix and handles both `postgres://` and `postgresql://` inputs. Raises `KeyError` at import time if `DATABASE_URL` is absent — fail fast.

#### 3. `app/db.py` — async engine + session dependency

**File:** `app/db.py` (new file)

**Intent:** Create the SQLAlchemy async engine and session factory, and expose a `get_session` async generator for FastAPI dependency injection.

**Contract:** Exports:
- `engine: AsyncEngine` — created with `pool_size=3, max_overflow=0`
- `AsyncSessionLocal: async_sessionmaker[AsyncSession]` — with `expire_on_commit=False`
- `get_session() -> AsyncGenerator[AsyncSession, None]` — yields one `AsyncSession` per request, commits on success, rolls back on exception, closes on exit

The engine is module-level (created once at import). No `create_all` call here — schema creation is Alembic's job.

### Success Criteria

#### Automated Verification

- `uv sync` completes without error after adding the three deps
- `uv run python -c "from app.db import engine, get_session; print('db ok')"` prints `db ok` (requires `DATABASE_URL` in env)
- `uv run python -c "from app.config import DATABASE_URL; assert 'asyncpg' in DATABASE_URL"` passes

#### Manual Verification

- `fly secrets list` shows `DATABASE_URL` is present
- Running the app locally with `DATABASE_URL` set to a local Postgres URL starts without errors

**Implementation Note:** Pause here before Phase 2. Verify the engine import works cleanly.

---

## Phase 2: SQLModel Models

### Overview

Define all six entity models in `app/models/`. Each model is a `SQLModel` with `table=True`. The models encode the full schema the migration will create.

### Changes Required

#### 1. `app/models/__init__.py` — package init + re-exports

**File:** `app/models/__init__.py` (new file)

**Intent:** Make `app/models` a package and re-export all models so Alembic's `env.py` can import them with a single `from app.models import *` without enumerating each module.

**Contract:** Imports and re-exports `User`, `Project`, `Element`, `ElementRepetition`, `Row`, `RowStateEnum`, `RowState` from their respective sibling modules.

#### 2. `app/models/user.py` — User (minimal, F-01 scope)

**File:** `app/models/user.py` (new file)

**Intent:** Define the User identity table. Auth fields (password hash, magic link token) are intentionally absent — F-02 adds them via an additive migration.

**Contract:** Table name `user`. Fields: `id` (int primary key, auto-increment), `email` (str, unique, indexed), `created_at` (datetime, UTC, non-nullable, server-default = now). SQLModel convention: `Optional[int]` for auto-increment PK with `default=None`.

#### 3. `app/models/project.py` — Project + Element + ElementRepetition

**File:** `app/models/project.py` (new file)

**Intent:** Define the three project-hierarchy entities in one module (they are tightly coupled and small).

**Contract:**

- **Project** — table `project`: `id`, `user_id` (FK → `user.id`, indexed), `name` (str, non-nullable), `created_at`, `updated_at` (both datetime UTC).
- **Element** — table `element`: `id`, `project_id` (FK → `project.id`, indexed), `name` (`str | None`, nullable — `None` represents the auto-created default element), `pattern_text` (`str | None`, nullable — stores the raw pasted text for re-parsing), `repeat_count` (int, default=1, ≥1), `created_at`.
- **ElementRepetition** — table `element_repetition`: `id`, `element_id` (FK → `element.id`, indexed), `repetition_number` (int, 1-based). `UniqueConstraint("element_id", "repetition_number")` enforced via `__table_args__`.

#### 4. `app/models/pattern.py` — Row

**File:** `app/models/pattern.py` (new file)

**Intent:** Define the Row entity — one record per parsed line of an element's pattern.

**Contract:** Table `row`: `id`, `element_id` (FK → `element.id`, indexed), `position` (int, 1-based ordering within the element), `content` (str — the text of this row). `UniqueConstraint("element_id", "position")` via `__table_args__`. No direct link to ElementRepetition — rows belong to the element's pattern; repetitions track progress through the same rows.

#### 5. `app/models/progress.py` — RowStateEnum + RowState

**File:** `app/models/progress.py` (new file)

**Intent:** Define the RowState junction table — the core of the app's tracking mechanic. Each record links one `ElementRepetition` to one `Row` with a state and optional stitch position.

**Contract:**

- **RowStateEnum** — `str` enum with values `not_started`, `in_progress`, `done`. Using `str` as the base makes Postgres store the values as plain strings (readable in psql) and makes JSON serialisation automatic.
- **RowState** — table `row_state`: `id`, `element_repetition_id` (FK → `element_repetition.id`, indexed), `row_id` (FK → `row.id`), `state` (`RowStateEnum`, default=`not_started`), `stitch_position` (`int | None`, nullable — only meaningful when `state == in_progress`), `updated_at` (datetime UTC, updated on every write). `UniqueConstraint("element_repetition_id", "row_id")` via `__table_args__`.

### Success Criteria

#### Automated Verification

- `uv run python -c "from app.models import User, Project, Element, ElementRepetition, Row, RowState; print('models ok')"` prints `models ok`
- `uv run python -c "from sqlmodel import SQLModel; from app.models import *; print(list(SQLModel.metadata.tables.keys()))"` prints all six table names

#### Manual Verification

- Inspect the model file for correct field types, FK references, and `__table_args__` on the three models that need `UniqueConstraint`

**Implementation Note:** Pause here. Verify all models import cleanly and appear in `SQLModel.metadata.tables` before writing the Alembic migration.

---

## Phase 3: Alembic Setup + Initial Migration + Fly Release Command

### Overview

Initialise Alembic, wire it to the async engine via the asyncio runner pattern, generate the initial migration from the SQLModel models, and configure Fly to run migrations before every deploy.

### Changes Required

#### 1. Initialise Alembic

**File:** `alembic/` directory (new, created by `alembic init alembic`)

**Intent:** Scaffold the Alembic directory structure (`alembic/env.py`, `alembic/versions/`, `alembic.ini`).

**Contract:** Run `uv run alembic init alembic` from the project root. This creates `alembic.ini` at the root and `alembic/env.py`. Do not commit the default `sqlalchemy.url` value in `alembic.ini` — override it in `env.py` instead.

#### 2. `alembic/env.py` — async runner configuration

**File:** `alembic/env.py` (replace generated content)

**Intent:** Wire Alembic to the async engine and ensure all SQLModel models are imported so autogenerate detects the full schema.

**Contract:** The file must:
1. Import `from app.models import *` (populates `SQLModel.metadata`)
2. Set `target_metadata = SQLModel.metadata`
3. Read `DATABASE_URL` from environment (same normalisation as `app/config.py`)
4. Implement the asyncio runner pattern: `run_migrations_online` creates an `async_engine_from_config`, opens an async connection, and calls `connection.run_sync(do_run_migrations)` inside `asyncio.run(run_async_migrations())`
5. Use `poolclass=pool.NullPool` for the migration engine (migrations don't need a pool)

The asyncio runner pattern (Alembic 1.12+ docs): the sync `do_run_migrations(connection)` function calls `context.configure(connection=connection, target_metadata=target_metadata)` then `context.run_migrations()`. The async wrapper passes this function to `connection.run_sync(...)`.

#### 3. `alembic/versions/<hash>_initial_schema.py` — generated migration

**File:** `alembic/versions/<hash>_initial_schema.py` (generated)

**Intent:** The initial migration that creates all six tables with correct columns, FKs, indexes, and unique constraints.

**Contract:** Run `uv run alembic revision --autogenerate -m "initial schema"` after `env.py` is configured and models are importable. Review the generated file: verify all six tables appear in `upgrade()`, all FK relationships are present, and the three `UniqueConstraint` entries appear. Do not hand-edit the generated file unless autogenerate missed something.

#### 4. `fly.toml` — add release_command

**File:** `fly.toml`

**Intent:** Tell Fly to run `alembic upgrade head` in a temporary container before routing traffic to the new app version on every deploy. If the migration fails, the deploy is aborted and the previous version keeps serving.

**Contract:** Add a `[deploy]` section with `release_command = "alembic upgrade head"`. The command runs inside the app's Docker image (where `uv run alembic` is available). No other fly.toml changes needed.

#### 5. `app/main.py` — remove placeholder, confirm health route

**File:** `app/main.py`

**Intent:** Remove the placeholder `index` route body and confirm the `/health` endpoint is the app's only active route until S-01 adds real routes. No DB import needed in main.py at this stage — the engine is initialised lazily.

**Contract:** `app/main.py` exports the `app: FastAPI` instance. The `GET /health` route returns `{"status": "ok"}`. The `GET /` route can return the same or be removed. No other changes.

### Success Criteria

#### Automated Verification

- `uv run alembic upgrade head` applies the migration cleanly against a local Postgres or via `fly proxy 5432 -a crochet-tracker-db` tunnel
- `uv run alembic downgrade -1` reverts it without errors
- `uv run alembic upgrade head` again re-applies cleanly (idempotency check)
- `uv run python -c "from app.models import *; from sqlmodel import SQLModel; print(len(SQLModel.metadata.tables))"` prints `6`

#### Manual Verification

- `fly deploy` completes successfully — check the Fly deploy log for the `release_command` step showing `alembic upgrade head` exit 0
- Connect to the DB and verify all six tables exist: `fly proxy 5432 -a crochet-tracker-db` then `psql $DATABASE_URL -c "\dt"`
- Verify the RowState unique constraint exists on `(element_repetition_id, row_id)`

---

## Testing Strategy

### Automated

- Import smoke tests for all models (see Phase 2 verification)
- Alembic round-trip: upgrade → downgrade → upgrade (Phase 3 verification)

### Manual Testing Steps

1. Run `fly deploy` and confirm the release command log shows `alembic upgrade head` succeeded
2. Open a psql session via `fly proxy` and run `\dt` — all six tables should be present
3. Run `\d row_state` — verify `state` column is an enum type, `stitch_position` is nullable, and the unique constraint on `(element_repetition_id, row_id)` is listed

## Migration Notes

This is the first migration — there is no existing data. Downgrade (`-1`) drops all tables; it is safe to run during development but should never be run against production once S-01 adds data.

## References

- Roadmap: `context/foundation/roadmap.md` — F-01
- GitHub issue: [#1 — DB schema: SQLModel models + Alembic migrations](https://github.com/patrycja-gurdak/CrochetTracker/issues/1)
- Alembic asyncio runner docs: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- SQLModel docs: https://sqlmodel.tiangolo.com

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands.

### Phase 1: Dependencies + Configuration + DB Engine

#### Automated

- [x] 1.1 `uv sync` completes without error after adding sqlmodel, asyncpg, alembic — b44924b
- [x] 1.2 `uv run python -c "from app.db import engine, get_session; print('db ok')"` prints `db ok` — b44924b
- [x] 1.3 `uv run python -c "from app.config import DATABASE_URL; assert 'asyncpg' in DATABASE_URL"` passes — b44924b

#### Manual

- [x] 1.4 `fly secrets list` shows DATABASE_URL present — b44924b
- [x] 1.5 App starts without errors when DATABASE_URL is set locally — b44924b

### Phase 2: SQLModel Models

#### Automated

- [x] 2.1 `uv run python -c "from app.models import User, Project, Element, ElementRepetition, Row, RowState; print('models ok')"` prints `models ok`
- [x] 2.2 `uv run python -c "from sqlmodel import SQLModel; from app.models import *; print(list(SQLModel.metadata.tables.keys()))"` lists all 6 tables

#### Manual

- [x] 2.3 All model files have correct FK references, UniqueConstraints, and nullable fields as specced

### Phase 3: Alembic Setup + Migration + Fly Release Command

#### Automated

- [ ] 3.1 `uv run alembic upgrade head` applies migration cleanly
- [ ] 3.2 `uv run alembic downgrade -1` reverts without errors
- [ ] 3.3 `uv run alembic upgrade head` re-applies cleanly (idempotency)
- [ ] 3.4 Model count check: `from app.models import *; from sqlmodel import SQLModel; len(SQLModel.metadata.tables) == 6`

#### Manual

- [ ] 3.5 `fly deploy` log shows release_command `alembic upgrade head` exit 0
- [ ] 3.6 `fly proxy` + psql `\dt` shows all 6 tables
- [ ] 3.7 `\d row_state` confirms unique constraint on (element_repetition_id, row_id) and nullable stitch_position
