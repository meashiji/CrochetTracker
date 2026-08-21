# Auth Boundary Integration Tests — Implementation Plan

## Overview

Bootstrap the integration test infrastructure and implement auth boundary tests for R2 (middleware
regression) and R4 (tampered session + orphaned user_id). This is Phase 1 of the test rollout
defined in `context/foundation/test-plan.md`.

## Current State Analysis

No test infrastructure beyond `tests/test_pattern.py` exists. There is no `conftest.py`, no
async client fixture, and no test DB. Dev dependencies have only `pytest` and `pip-audit`.

The app uses two auth layers: a global `AuthRedirectMiddleware` (ASGI, runs before routing) and
per-route `Depends(get_current_user)` (DB lookup). The middleware covers all routes automatically;
the real regression surface for R2 is `_PUBLIC_PATHS` at `app/auth/middleware.py:6`.

Password login exists at `POST /auth/login` — tests can authenticate by POSTing credentials and
letting the httpx client store the resulting session cookie automatically.

## Desired End State

`uv run pytest tests/test_auth_boundary.py -v` passes four tests:
- unauthenticated GET /projects/ → 303 to /auth/login
- tampered session cookie GET /projects/ → 303 to /auth/login
- valid session + user in DB GET /projects/ → 200
- valid session + user deleted GET /projects/ → 401

`context/foundation/test-plan.md §6.2` is filled in with the exact run command and a pointer to
the reference test.

### Key Discoveries

- `app/db.py:7` — `engine` is created at module level from `DATABASE_URL`; setting `DATABASE_URL`
  env var before `app.*` import routes the entire app to the test DB automatically
- `app/config.py:4-24` — all env vars read at module level with `os.environ["..."]`; conftest
  must set them before any `app.*` import
- `app/main.py:19-20` — `SessionMiddleware` with `https_only=True`; httpx will not send `Secure`
  cookies on `http://` requests; `base_url="https://testserver"` is required
- `app/routes/auth.py:63-84` — `POST /auth/login` accepts form fields `email` + `password` and
  sets `request.session["user_id"]` on success; tests can authenticate this way without crafting
  signed cookies manually
- `app/routes/auth.py:29-55` — `POST /auth/signup` also creates a session; usable for test user
  creation in one step
- `app/db.py:16-23` — `get_session` yields from `AsyncSessionLocal` (app engine); since env var
  points app engine at test DB, route handlers naturally use the test DB in tests — no
  `dependency_overrides` needed

## What We're NOT Doing

- Testing Starlette's internal session signing / itsdangerous internals
- Testing magic-link flow (not needed for auth boundary coverage)
- Testing ownership (IDOR) — that is Phase 2
- Writing e2e or browser tests
- Wiring CI (deferred to Module 2 Lesson 5)
- Filling in §6.1 (unit test cookbook) — stays TBD until a unit test use-case lands

## Implementation Approach

Set env vars → import app → tests call the actual ASGI app in-process via httpx + ASGITransport.
Test DB is a dedicated Postgres database (`crochet_tracker_test`) on the same local instance as
the dev DB. Tables are created via `SQLModel.metadata.create_all` at session start and dropped at
session end. Test users are created via `POST /auth/signup` (which also sets the session cookie)
and deleted in fixture teardown.

## Critical Implementation Details

**Import ordering in conftest.py**: `os.environ[...]` assignments must appear before any
`from app.* import` statement. Even a top-level type annotation that references an app model
triggers `app.config` and the `KeyError`. Place env-var setup at the very top of the file,
before all other imports.

**`base_url` for httpx**: Use `base_url="https://testserver"` (not `http://`). `SessionMiddleware`
sets the `Secure` flag because `https_only=True`; httpx drops `Secure` cookies on plain-http
requests, making session tests fail silently.

**Test DB prerequisite**: The database `crochet_tracker_test` must be created manually before
running tests for the first time. Run once:
```
createdb -h 127.0.0.1 -p 5433 -U crochet_tracker crochet_tracker_test
```
After that, the session-scoped fixture handles table creation/teardown automatically.

**Cleanup between tests**: Route handlers commit via the app's own session (independent of the
test session). Cleanup is done per-fixture: the `test_user` fixture deletes the row via a
separate `_TestSessionLocal` session after each test.

---

## Phase 1: Bootstrap test infrastructure

### Overview

Add `httpx` and `pytest-asyncio` dev dependencies, configure `asyncio_mode = "auto"`, and create
`tests/conftest.py` with the env-var setup, test DB fixtures, and the async client fixture.

### Changes Required

#### 1. Dev dependencies and pytest config

**File**: `pyproject.toml`

**Intent**: Add `httpx>=0.28` and `pytest-asyncio>=0.24` to the `[dependency-groups] dev` group;
add a `[tool.pytest.ini_options]` table with `asyncio_mode = "auto"` so that every `async def
test_*` runs under asyncio without a per-test decorator.

**Contract**: Two new entries in the `dev` list; new `[tool.pytest.ini_options]` section. After
editing, run `uv sync` to update the lockfile.

#### 2. conftest.py — env vars, test engine, fixtures

**File**: `tests/conftest.py` (create)

**Intent**: Set all required env vars at the very top (before any `app.*` import), create a
session-scoped fixture that builds the test engine and creates all tables via
`SQLModel.metadata.create_all`, provide a function-scoped `db_session` fixture for direct DB
access in teardown helpers, and expose an `async_client` fixture (httpx `AsyncClient` with
`ASGITransport(app=app)` and `base_url="https://testserver"`).

**Contract**:

```python
# -- top of file, before any other import --
import os
os.environ.setdefault("DATABASE_URL",
    "postgresql+asyncpg://crochet_tracker:dupa123@127.0.0.1:5433/crochet_tracker_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("MAIL_USERNAME", "test")
os.environ.setdefault("MAIL_PASSWORD", "test")
os.environ.setdefault("MAIL_FROM", "test@example.com")
```

The snippet above is load-bearing — placement before imports is the constraint, not the values.
Everything else (fixture bodies, imports) follows standard pytest-asyncio patterns and can be
derived from the intent.

The module-level test engine and session factory:
```python
_test_engine = create_async_engine(os.environ["DATABASE_URL"])
_TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
```

Session-scoped fixture creates tables on first run and drops them after the last test.
Function-scoped `db_session` yields from `_TestSessionLocal` and rolls back on exit.
`async_client` fixture wraps `AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")`.

### Success Criteria

#### Automated Verification

- `uv sync` installs `httpx` and `pytest-asyncio` without errors
- `uv run pytest --collect-only` exits 0 with no import errors
- `uv run pytest --collect-only` shows `tests/test_pattern.py` tests still collected (no regression)

#### Manual Verification

- `crochet_tracker_test` database exists on local Postgres at :5433
- Running `uv run pytest tests/ --co -q` shows no collection warnings about missing fixtures

**Implementation Note**: After completing this phase, verify that the collection step passes
before writing any test functions.

---

## Phase 2: No-DB auth boundary tests (R2 + R4a)

### Overview

Write two tests that hit the middleware layer without touching the DB. Both tests use only the
`async_client` fixture (no `db_session`, no `test_user`).

### Changes Required

#### 1. Auth boundary test file

**File**: `tests/test_auth_boundary.py` (create)

**Intent**: Two async test functions:

1. **`test_unauthenticated_request_redirects`** — GET `/projects/` with no cookies sent.
   The middleware sees `user_id=None` and returns 303. Assert `response.status_code == 303` and
   `response.headers["location"]` ends with `/auth/login`. Use `follow_redirects=False` on the
   client so the redirect is not followed automatically.

2. **`test_tampered_session_cookie_redirects`** — GET `/projects/` with the header
   `Cookie: session=<garbage_string>`. Starlette's SessionMiddleware discards the invalid HMAC and
   treats the session as empty; the middleware returns 303. Assert the same status and location as
   above.

**Contract**: Both functions are `async def`, accept `async_client` as their only fixture
argument, and call `await async_client.get(...)`. No DB setup, no user creation.

### Success Criteria

#### Automated Verification

- `uv run pytest tests/test_auth_boundary.py -k "unauthenticated or tampered" -v` → 2 passed, 0 failed

#### Manual Verification

- Test output shows both test names and `PASSED`
- No warnings about asyncio or fixture scope

---

## Phase 3: DB-backed auth tests (R4b + happy path) + cookbook update

### Overview

Two additional tests that require a real user in the test DB. Then update §6.2 in
`context/foundation/test-plan.md` with the exact run command and a pointer to the reference test.

### Changes Required

#### 1. DB-backed tests

**File**: `tests/test_auth_boundary.py` (extend)

**Intent**: Two more async test functions using a `test_user` fixture:

**`test_user` fixture** (add to `conftest.py`): Creates a test user via `POST /auth/signup`
(which sets the session cookie on the client). The fixture yields the user record fetched via
`db_session`. On teardown, deletes the user row and commits via `db_session`. Accepts both
`async_client` and `db_session` as arguments so it can both drive the signup endpoint and clean up
directly.

3. **`test_valid_session_returns_200`** — uses `test_user` fixture (which signs in via signup,
   setting the session cookie on `async_client`). GET `/projects/` with the stored cookie returns
   200. Asserts `response.status_code == 200`.

4. **`test_orphaned_user_id_returns_401`** — uses `test_user` fixture to create and sign in a
   user, then deletes that user via `db_session` (committing the delete), then GET `/projects/`.
   `get_current_user` looks up the user_id from the session, gets `None` from the DB, raises HTTP
   401. Asserts `response.status_code == 401`.

**Note on `test_user` fixture scope**: Keep it function-scoped. The `async_client` fixture is
function-scoped (new client per test, clean cookie jar). Reusing a user across tests would share
session state, which undermines test isolation.

#### 2. §6.2 cookbook entry

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the `§6.2 Adding an integration test for a route` TBD placeholder with the
canonical pattern: location convention (`tests/test_auth_boundary.py` as the reference),
fixture dependencies (`async_client`, optional `db_session` + `test_user` for DB-backed tests),
and the exact run command (`uv run pytest tests/ -v`).

### Success Criteria

#### Automated Verification

- `uv run pytest tests/test_auth_boundary.py -v` → 4 passed, 0 failed
- `uv run pytest tests/ -v` → all 10 tests pass (6 existing + 4 new), 0 failed

#### Manual Verification

- `§6.2` in `test-plan.md` no longer reads "TBD" — it has the fixture pattern and run command
- `context/foundation/test-plan.md §3` Phase 1 row status updated from `researched` to `complete`

---

## Testing Strategy

### Integration Tests

All tests in `tests/test_auth_boundary.py` are integration tests — they call the real ASGI app
in-process via httpx + ASGITransport against the test DB. No mocking.

### Edge Cases Covered

- No session cookie at all (R2 baseline)
- Session cookie present but HMAC-invalid (R4a — distinct from "no cookie")
- Valid session, user exists (happy path — proves test infra works)
- Valid session, user deleted from DB (R4b — proves `get_current_user` is the failure point, not
  the middleware)

### What Is Not Tested Here

- `_PUBLIC_PATHS` enumeration (e.g. `/auth/login` accessible without session) — out of Phase 1
  scope; could be added as R2 extension in Phase 2
- Magic-link flow
- Ownership / IDOR (Phase 2)

## References

- Research: `context/changes/testing-auth-boundary/research.md`
- Test plan: `context/foundation/test-plan.md` §2 R2, R4; §3 Phase 1
- Auth middleware: `app/auth/middleware.py:6-14`
- Auth dependency: `app/auth/dependencies.py:8-15`
- DB layer: `app/db.py:7` (module-level engine), `app/db.py:16-23` (get_session)
- Password login: `app/routes/auth.py:63-84`

---

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands.

### Phase 1: Bootstrap test infrastructure

#### Automated

- [x] 1.1 `uv sync` installs httpx and pytest-asyncio without errors — f747266
- [x] 1.2 `uv run pytest --collect-only` exits 0 with no import errors — f747266
- [x] 1.3 `uv run pytest --collect-only` still collects `tests/test_pattern.py` tests — f747266

#### Manual

- [x] 1.4 `crochet_tracker_test` database exists and collection step passes without fixture warnings — f747266

### Phase 2: No-DB auth boundary tests

#### Automated

- [x] 2.1 `uv run pytest tests/test_auth_boundary.py -k "unauthenticated or tampered" -v` → 2 passed — f747266

#### Manual

- [x] 2.2 Test output shows both test names with PASSED, no asyncio warnings — f747266

### Phase 3: DB-backed auth tests + cookbook update

#### Automated

- [x] 3.1 `uv run pytest tests/test_auth_boundary.py -v` → 4 passed, 0 failed — f747266
- [x] 3.2 `uv run pytest tests/ -v` → 10 tests pass (6 existing + 4 new) — f747266

#### Manual

- [x] 3.3 `§6.2` in `test-plan.md` filled in with fixture pattern and run command — f747266
- [x] 3.4 `§3` Phase 1 row status updated to `complete` in `test-plan.md` — f747266
