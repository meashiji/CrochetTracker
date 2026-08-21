---
date: 2026-06-27T14:47:57+00:00
researcher: claude-sonnet-4-6
git_commit: 3d972d48d0e838694ef2e2de95769eaa5f4663fc
branch: main
repository: CrochetTracker
topic: "Auth boundary testing: route protection and session validation (test-plan Phase 1, R2 + R4)"
tags: [research, auth, testing, middleware, session, httpx, pytest]
status: complete
last_updated: 2026-06-27
last_updated_by: claude-sonnet-4-6
---

# Research: Auth boundary testing — route protection and session validation

**Date**: 2026-06-27T14:47:57+00:00
**Git Commit**: 3d972d48d0e838694ef2e2de95769eaa5f4663fc
**Branch**: main
**Repository**: CrochetTracker

## Research Question

Ground rollout Phase 1 of `context/foundation/test-plan.md`. Verify or correct the response guidance for R2 (auth middleware regression — project route inadvertently unprotected) and R4 (expired/tampered session accepted). Identify the real failure path in code, the cheapest test layer, and any test setup constraints.

## Summary

The auth layer is a **two-layer ASGI + dependency stack**. A global `AuthRedirectMiddleware` intercepts unauthenticated requests before routing; per-route `Depends(get_current_user)` provides a secondary check and supplies the `User` object. The session is a **Starlette `SessionMiddleware` signed cookie** — HMAC-protected but not encrypted, no expiry configured. Two corrections to the test plan's risk guidance are required before planning:

1. **R2 correction**: the middleware approach makes "forgetting a Depends()" impossible as an attack vector — the global middleware catches all non-public paths. The real regression risk is `_PUBLIC_PATHS` being accidentally widened.
2. **R4 correction**: "Expired session accepted" is not a real scenario — `SessionMiddleware` is configured without `max_age`, so sessions never expire. The testable variant is: tampered session cookie is rejected. The "expired" framing should be dropped.

One material **test setup constraint** requires planning attention: `https_only=True` on `SessionMiddleware` sets the `Secure` cookie flag; `httpx.AsyncClient` will not re-send a `Secure` cookie on `http://` requests. The test client must use `base_url="https://testserver"`.

---

## Detailed Findings

### Auth protection mechanism

**Two-layer architecture:**

#### Layer 1 — `AuthRedirectMiddleware` (ASGI, global)

`app/auth/middleware.py:9-14`

```python
class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_public = path in _PUBLIC_PATHS or path.startswith("/static/")
        if request.session.get("user_id") is None and not is_public:
            return RedirectResponse(url="/auth/login", status_code=303)
        return await call_next(request)
```

The middleware runs on **every request** before routing. Public paths are an explicit allowlist:

```python
_PUBLIC_PATHS = {"/health", "/auth/login", "/auth/signup", "/auth/magic-link", "/auth/magic-link/verify"}
```

(`app/auth/middleware.py:6`)

Middleware execution order (`app/main.py:15-20`): Starlette processes middleware in reverse registration order. `SessionMiddleware` is registered last (outermost) → runs first, parses the session cookie → `AuthRedirectMiddleware` runs second, reads `request.session`. The comment at `app/main.py:15-17` explains this explicitly.

#### Layer 2 — `get_current_user` dependency (per-route)

`app/auth/dependencies.py:8-15`

```python
async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401)
    return user
```

Secondary protection and `User` object provider. If `user_id` is in the session but the user was deleted from the DB, this raises HTTP 401. All current project routes carry this dependency: `app/routes/projects.py:21,32,40`.

#### R2 failure path — corrected

The test plan assumed the risk was "forgetting a Depends() on a new route." That framing is wrong for this codebase. Because the middleware is global, any new route added to any router is **automatically protected**. The route handler does not even run for unauthenticated requests.

The real regression failure paths for R2 are:
- `_PUBLIC_PATHS` accidentally gains a private path (e.g. `/projects/`) — middleware passes the request through
- The `is_public` condition logic is changed (e.g., prefix check widened beyond `/static/`)
- `AuthRedirectMiddleware` is removed from `app.add_middleware(...)` entirely

Test implication: the test should verify the middleware's behavior on key paths, not enumerate every route's `Depends()`.

---

### Session mechanism

#### Session type: Starlette `SessionMiddleware` (signed cookie)

`app/main.py:4,19-20`:

```python
from starlette.middleware.sessions import SessionMiddleware
...
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=True)
```

Starlette's `SessionMiddleware` stores session data as a **signed (HMAC-protected) cookie** using `itsdangerous` internally. The cookie is **not encrypted** — the `user_id` integer is readable — but any modification to the payload invalidates the HMAC signature, and Starlette discards the cookie silently.

- **Cookie name**: `"session"` (Starlette default; not overridden)
- **Cookie flags**: `Secure` (`https_only=True`), `SameSite=Lax`, `HttpOnly` (Starlette default)
- **Session data stored**: `{"user_id": <int>}` — set at `app/routes/auth.py:53,82,185`

#### No session expiry — critical finding

`SessionMiddleware` is configured **without a `max_age` parameter**. Sessions are indefinitely valid and only invalidated by:
- Explicit logout: `request.session.clear()` (`app/routes/auth.py:87`)
- `SECRET_KEY` rotation (invalidates all sessions)

There is no automatic expiry.

#### Tamper detection

If the `session` cookie payload is tampered with (any byte changed), the HMAC signature fails. Starlette's `SessionMiddleware` discards the cookie silently and treats it as an empty session. `request.session.get("user_id")` returns `None` → `AuthRedirectMiddleware` returns 303 to `/auth/login`.

#### Magic link tokens (separate subsystem)

`app/auth/tokens.py` uses `itsdangerous.URLSafeTimedSerializer` with `salt="magic-link"` — this is **exclusively for magic link URLs**, not for session cookies. Do not conflate the two. The magic link serializer has a 15-minute `max_age=900`. The session cookie signing is handled entirely by Starlette's `SessionMiddleware` internally.

#### R4 failure path — corrected

The test plan's R4 framing included "expired session accepted" — this is not a real scenario in the current code. Sessions don't expire. The two testable variants of R4 are:

1. **Tampered session cookie**: send `Cookie: session=<garbage_or_modified_value>` → Starlette discards the cookie → `user_id` is None → middleware returns 303
2. **Valid user_id in session, user deleted from DB**: `get_current_user` performs `session.get(User, user_id)` → returns None → raises HTTP 401

The "expired session" line in the test plan's R4 risk description should be dropped. The plan can be backported before the planning phase.

---

### Test infrastructure status

#### Missing dev dependencies

`pyproject.toml` dev group has only `pytest>=9.1.1` and `pip-audit`. Missing:

| Dependency | Why needed | Recommended version |
|------------|-----------|---------------------|
| `httpx` | `httpx.AsyncClient` + `ASGITransport` for in-process route testing | `>=0.28` |
| `pytest-asyncio` | Run `async def test_*` functions | `>=0.24` |

No `conftest.py` exists. No fixtures are defined.

#### Async DB engine

`app/db.py` uses `create_async_engine` with asyncpg. All route handlers are async and use `AsyncSession`. Tests must be async.

#### `https_only=True` cookie constraint — critical

`SessionMiddleware` with `https_only=True` sets `Secure` on the `session` cookie. `httpx.AsyncClient` respects the `Secure` attribute and **will not send a `Secure` cookie on `http://` requests**. Tests that set a session (e.g., sign in → then call a protected route) will silently fail to send the cookie if `base_url="http://testserver"`.

**Fix**: use `base_url="https://testserver"` with `ASGITransport(app=app)`.

#### Environment variables required at import time

`app/config.py` reads all env vars at module level using `os.environ["..."]` (fails with `KeyError` if missing). Importing `app.main` requires all of these to be set:

| Var | Why required at import | Minimum test value |
|-----|------------------------|-------------------|
| `DATABASE_URL` | `config.py:4-15` reads and rewrites the URL | `postgresql+asyncpg://user:pw@localhost:5433/test_db` |
| `SECRET_KEY` | `config.py:17` | any non-empty string |
| `MAIL_USERNAME` | `config.py:19` | any string (e.g. `"test"`) |
| `MAIL_PASSWORD` | `config.py:20` | any string |
| `MAIL_FROM` | `config.py:21` | any valid email string |

Tests must set these env vars **before** any `app.*` import. The cleanest pattern: set `os.environ[...]` at the top of `conftest.py` before any app imports.

#### Which tests need a real DB

| Test scenario | DB needed? | Rationale |
|---------------|-----------|-----------|
| No session → 303 redirect | No | Middleware intercepts before route handler runs |
| Tampered session → 303 redirect | No | Middleware intercepts before route handler runs |
| Valid session + existing user → 200 | Yes | `get_current_user` hits DB for user lookup |
| Valid user_id in session + user deleted → 401 | Yes | `get_current_user` hits DB, gets None, raises 401 |

Phase 1 can test the first two scenarios without a DB. A minimal DB setup (one test user) is needed for the second two.

---

## Code References

- `app/auth/middleware.py:6` — `_PUBLIC_PATHS` allowlist (the real R2 attack surface)
- `app/auth/middleware.py:9-14` — `AuthRedirectMiddleware.dispatch` — session check + redirect logic
- `app/auth/dependencies.py:8-15` — `get_current_user` — DB lookup + HTTP 401 if user missing
- `app/main.py:13` — `app = FastAPI(title="CrochetTracker")` — the testable app object
- `app/main.py:15-20` — middleware registration order (comment explains Starlette's reverse-order wrapping)
- `app/main.py:19-20` — `SessionMiddleware` config: `https_only=True` (the test setup constraint)
- `app/routes/projects.py:14` — `router = APIRouter(prefix="/projects")` — no router-level dependencies
- `app/routes/projects.py:21,32,40` — all three routes have `Depends(get_current_user)`
- `app/routes/auth.py:53,82,185` — session set: `request.session["user_id"] = user.id`
- `app/routes/auth.py:87` — session cleared: `request.session.clear()`
- `app/config.py:4-24` — all env vars read at module level (import-time requirement)
- `app/db.py` — async engine with `asyncpg`; `DATABASE_URL` from `app.config`
- `tests/test_pattern.py` — only existing test file; no conftest, no fixtures

## Architecture Insights

**Middleware-first protection is more defensive than Depends()-first**: Any new route is automatically protected; the risk surface for R2 is narrow (only `_PUBLIC_PATHS` and the middleware condition). Test coverage should target the allowlist and the middleware logic, not enumerate every route's dependency.

**Sessions are indefinitely valid**: This is the current architectural reality. There is no session expiry, no server-side session revocation (outside of SECRET_KEY rotation). This is a design decision, not a bug, and is out of scope for Phase 1 testing.

**`https_only=True` affects test client setup**: This is the most surprising test infra constraint. Using `http://testserver` as the base URL will cause session cookies to silently not be sent, making tests appear to work (redirect on every request) without actually testing the "valid session → 200" path.

**App import requires all config vars**: The test conftest must set env vars before importing anything from `app.*`. Order matters at module level.

## Historical Context

- `context/changes/auth-scaffold/plan.md` explicitly deferred testing: "No test framework exists yet (out of scope to introduce here — Module 3 territory per CLAUDE.md)." Testing was handled with manual per-phase verification checklists. No test infrastructure was planned or scaffolded during auth-scaffold.
- `context/changes/project-and-pattern-display/plan.md` Phase 1 shipped project routes but similarly deferred testing. No conftest or fixture foundation was laid.
- The absence of test infrastructure is intentional and well-documented; Phase 1 of the test rollout is the correct place to bootstrap it.

## Backport Corrections Required (post-research check)

Two corrections to `context/foundation/test-plan.md §2 Risk Response Guidance` before planning:

**R4 — "Must challenge" correction:**
- Current: "does it check expiry? Does it reject a tampered payload?"
- Corrected: "there is no session expiry (`max_age` not configured) — drop the expiry scenario; the testable case is tampered cookie rejected + valid user_id with deleted user → 401"

**R2 — "Must challenge" and "Context" correction:**
- Current: "a route added to a different router or with a missing dependency may not be covered"
- Corrected: global middleware covers all routes regardless of router or missing Depends(); the real attack surface is `_PUBLIC_PATHS` at `app/auth/middleware.py:6` and the `is_public` condition logic

## Open Questions

1. **Test DB strategy**: Use a real test Postgres DB (separate schema on local Postgres at 5433) vs. SQLite for unit-speed tests. Async SQLModel + asyncpg has SQLite compatibility issues; a real Postgres test DB is the safe choice. Connection string for test DB needs to be established.
2. **Mail env vars in tests**: The five `MAIL_*` vars must be set but are only used if `send_magic_link_email` is actually called. For Phase 1 auth-boundary tests, setting dummy strings suffices — no emails are sent. Confirm this is acceptable for Phase 2 (which may exercise magic-link routes).
3. **`get_current_user` with `user_id=None`**: If somehow `get_current_user` is called when `user_id` is None in the session (shouldn't happen via normal flow due to middleware), `session.get(User, None)` is called. SQLAlchemy async behavior with a `None` primary key is undefined/implementation-dependent. This edge case is unlikely in practice but could be a latent bug worth a single test.
