# Auth Boundary Integration Tests — Plan Brief

> Full plan: `context/changes/testing-auth-boundary/plan.md`
> Research: `context/changes/testing-auth-boundary/research.md`

## What & Why

Bootstrap the integration test infrastructure and prove that the auth layer correctly blocks
unauthenticated access, rejects tampered session cookies, and catches orphaned user_id references.
This is Phase 1 of the `test-plan.md` rollout, covering R2 (middleware regression) and R4
(tampered session + orphaned user).

## Starting Point

No test infrastructure exists beyond `tests/test_pattern.py` (parser unit tests). There is no
`conftest.py`, no async HTTP test client, and no test database. Dev deps have only `pytest`.
The app's session engine is created at module level from `DATABASE_URL` at import time, which
makes test-DB isolation straightforward: set the env var before importing `app.*`.

## Desired End State

Four integration tests in `tests/test_auth_boundary.py` all pass under `uv run pytest`. The
§6.2 cookbook entry in `test-plan.md` is filled in so future test authors know where to look and
what command to run.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Test DB isolation | Dedicated `crochet_tracker_test` Postgres DB | Zero risk of contaminating dev data; safe to truncate freely between tests | Plan |
| asyncio configuration | `asyncio_mode = "auto"` in pyproject.toml | No per-test decorator boilerplate; standard for async-first FastAPI projects | Plan |
| Session setup in tests | POST /auth/signup (drives real login endpoint) | Avoids needing to replicate Starlette's internal HMAC signing format | Research |
| base_url for httpx | `https://testserver` (not `http://`) | `https_only=True` sets Secure flag; httpx drops Secure cookies on plain-http requests | Research |
| Env vars in conftest | Set via `os.environ` before any `app.*` import | `app/config.py` reads all vars at module level; import order is load-bearing | Research |
| Happy path in Phase 1 | Yes — include valid-session → 200 test | R4b already needs DB fixtures; a 200-path test proves the full stack is wired before relying on failure paths | Plan |

## Scope

**In scope:**
- `pyproject.toml` — add httpx, pytest-asyncio, asyncio_mode config
- `tests/conftest.py` — env vars, test engine, async_client, test_user fixtures
- `tests/test_auth_boundary.py` — 4 tests: no session→303, tampered→303, valid→200, orphaned→401
- `test-plan.md §6.2` — fill in cookbook entry
- `test-plan.md §3` — update Phase 1 status to `complete`

**Out of scope:**
- Magic-link flow, signup form, change-password route
- Ownership / IDOR (Phase 2)
- CI pipeline wiring (Module 2 Lesson 5)
- `_PUBLIC_PATHS` enumeration tests (Phase 2 extension)

## Architecture / Approach

All tests call the real ASGI app in-process via `httpx.AsyncClient + ASGITransport`. No mocking.
The app's module-level engine picks up `DATABASE_URL` at import time, so pointing the env var at
`crochet_tracker_test` routes the entire app to the test DB without any `dependency_overrides`.
A session-scoped fixture creates tables once; a function-scoped `test_user` fixture creates and
deletes a user per test.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Bootstrap infra | `conftest.py` + deps + test DB | `crochet_tracker_test` DB must be created manually first |
| 2. No-DB tests | 2 middleware tests (R2 + R4a) — no DB needed | base_url must be `https://` or cookies are silently dropped |
| 3. DB-backed tests + cookbook | 2 DB tests (R4b + happy path) + §6.2 filled in | `test_user` teardown must commit the delete before the next test starts |

**Prerequisites:** `crochet_tracker_test` Postgres database created manually:
```
createdb -h 127.0.0.1 -p 5433 -U crochet_tracker crochet_tracker_test
```
**Estimated effort:** 1 session across 3 phases

## Open Risks & Assumptions

- `SQLModel.metadata.create_all` used for test DB table creation (simpler than alembic in tests);
  assumes model definitions match the latest schema — true at time of writing
- The `test_user` fixture creates users via `POST /auth/signup`, which also sets a session cookie
  on the client; tests that need a fresh unauthenticated client must not use `test_user`

## Success Criteria (Summary)

- `uv run pytest tests/ -v` → 10 tests pass (6 existing pattern tests + 4 new auth boundary tests)
- `§6.2` in `test-plan.md` filled in with fixture pattern and run command
- Phase 1 status in `test-plan.md §3` updated to `complete`
