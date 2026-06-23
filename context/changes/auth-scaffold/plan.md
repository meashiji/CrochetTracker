# Auth Scaffold (F-02) Implementation Plan

## Overview

Add session-based authentication to CrochetTracker: users can sign up and log in with email + password, or via a magic-link email; an `AuthRedirectMiddleware` protects every route except the public auth/health endpoints; a logged-in "change password" page doubles as the account-recovery path. This unlocks S-01 (project views require an authenticated user) and S-04.

## Current State Analysis

- `app/models/user.py:9-11` — `User` has only `id`, `email` (unique, indexed), `created_at`. No auth fields.
- `app/db.py:7-23` — async `get_session()` DI pattern; new auth code follows this.
- `app/config.py` — fail-fast `os.environ[...]` pattern for required config (`DATABASE_URL`); same pattern applies to `SECRET_KEY` and mail config.
- `app/main.py` — 13-line stub: `/health` (JSON) and `/` (JSON), no middleware, no templates, no routers.
- `app/routes/`, `app/templates/`, `app/static/` — exist, empty.
- `pyproject.toml` — deps: `alembic`, `asyncpg`, `fastapi==0.136.1`, `sqlmodel`, `uvicorn`. No Jinja2, sessions, hashing, mail, or form-parsing deps.
- `alembic/versions/eb719c984d34_initial_schema.py` — single migration (F-01), `user` table has no auth columns. New migration must be additive, `down_revision='eb719c984d34'`.
- `context/foundation/lessons.md` — "destructive downgrade should be flagged in-file" — applies to this phase's migration (dropping the new columns in `downgrade()` drops their data).
- No tests, linting, or CI checks beyond `flyctl deploy` exist yet — automated verification in this plan is limited to import/startup checks and migration application.

## Desired End State

- An unauthenticated visitor hitting any path other than `/health`, `/auth/*`, or `/static/*` is redirected to `/auth/login`.
- A new user can sign up with email + password (immediate login, no email verification) or request a magic-link email; clicking the link logs them in (creating the account if it didn't exist).
- A logged-in user can change their password from `/auth/change-password` — this is the account-recovery path (forgot password → magic link in → change password).
- `user` table has an additive nullable `password_hash` column; a new `magic_link_token` table stores hashed, time-limited magic-link tokens (one row per request, multiple concurrent valid tokens allowed per user).
- `fly deploy` succeeds with the new migration applied via `release_command`, and the new env vars (`SECRET_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`) set as Fly secrets.

### Key Discoveries:

- `app/config.py`'s `DATABASE_URL` normalization establishes the "required env var via `os.environ[...]`, fail fast" convention — `SECRET_KEY` and mail config follow it.
- The existing `get_session()` dependency (`app/db.py:16-23`) is the only DB-access pattern in the codebase; auth routes use it directly, no new session abstraction.
- Because both password and magic-link auth are in scope, and magic link can be the *first* sign-in for a new email (passwordless registration), the magic-link "request" step must get-or-create the `User` row — not assume it exists.

## What We're NOT Doing

- Email verification on password signup (signup = immediate login).
- A separate "forgot password" email/token flow — magic link is the recovery path.
- A cleanup job for expired/used `magic_link_token` rows — rows accumulate but are harmless; pruning can be added later if table size becomes a concern.
- OAuth / social login (authlib, "Sign in with Google") — out of scope per PRD's flat single-account model.
- Building S-01 project views — `/` becomes a minimal authenticated landing page only, just enough to prove the auth shell works.
- `.env` / dotenv tooling — env vars are provided the same way `DATABASE_URL` already is (process environment / Fly secrets).

## Implementation Approach

Five phases, each independently deployable and verifiable:

1. **Foundation** — dependencies, config, additive migration (`User` model gets the three new columns).
2. **Session + route protection + templates** — `SessionMiddleware`, `AuthRedirectMiddleware`, Jinja2 base layout, authenticated `/`.
3. **Password auth** — signup, login, logout.
4. **Magic-link auth** — request + verify, email via `fastapi-mail`/Gmail SMTP.
5. **Change password** — logged-in page, the recovery path.

Phases 3-5 each add routes to the same `app/routes/auth.py` router and templates under `app/templates/auth/` — they build incrementally on phase 2's middleware and phase 1's schema, so each phase is a thin, demoable slice rather than a rewrite.

## Critical Implementation Details

### Magic-link token design

Each request creates a new `MagicLinkToken` row (`user_id`, `token_hash`, `expires_at`, `used_at`). The emailed link encodes `{"tok": <random-token>}` via `itsdangerous.URLSafeTimedSerializer(SECRET_KEY, salt="magic-link")`; only `sha256(tok).hexdigest()` is stored as `token_hash` (unique-indexed). Verification: unsign with `max_age=900` (raises on tamper/expiry independent of the DB), then look up the row by `sha256(tok)`, confirm `used_at IS NULL` and `expires_at` hasn't passed, then set `used_at = now()` (single-use per token) and load the `User` via `user_id`. Multiple concurrent valid tokens per user are allowed (e.g. requested from two devices) — a new request does not invalidate previous unused tokens.

### Route protection via middleware, not per-route dependencies

`AuthRedirectMiddleware` (added after `SessionMiddleware` in `app/main.py`) inspects `request.session.get("user_id")` for every request. An allowlist of path prefixes (`/health`, `/auth/`, `/static/`) bypasses the check; everything else redirects (303) to `/auth/login` if `user_id` is absent. This matches the PRD's "session middleware protects all project routes" requirement without requiring every future route (S-01+) to remember to add a dependency.

## Phase 1: Foundation — dependencies, config, migration

### Overview

Add the new dependencies, extend `app/config.py` with the auth/mail env vars, add the three new columns to the `User` model, and write the additive Alembic migration.

### Changes Required:

#### 1. `pyproject.toml` — new dependencies

**File**: `pyproject.toml`

**Intent**: Add the libraries this feature needs: password hashing, session-cookie signing, templating, form parsing, and email sending.

**Contract**: Add to `dependencies`: `pwdlib[argon2]`, `itsdangerous`, `jinja2`, `python-multipart`, `fastapi-mail`.

#### 2. `app/config.py` — auth and mail configuration

**File**: `app/config.py`

**Intent**: Establish `SECRET_KEY` (session signing + magic-link token signing) and Gmail SMTP settings, following the existing fail-fast `os.environ[...]` pattern used for `DATABASE_URL`.

**Contract**: Export `SECRET_KEY: str` (required, `os.environ["SECRET_KEY"]`), `MAIL_USERNAME: str`, `MAIL_PASSWORD: str`, `MAIL_FROM: str` (all required), `MAIL_SERVER: str` (default `"smtp.gmail.com"`), `MAIL_PORT: int` (default `587`).

#### 3. `app/models/user.py` — new column

**File**: `app/models/user.py`

**Intent**: Add the storage needed for password auth, nullable so existing rows (and magic-link-only accounts) remain valid.

**Contract**: Add field `password_hash: str | None = Field(default=None)`.

#### 4. `app/models/magic_link_token.py` — new model

**File**: `app/models/magic_link_token.py` (new)

**Intent**: Storage for magic-link tokens as a separate table — supports multiple concurrent in-flight tokens per user and keeps a token history (the "lesson for future projects" alternative to single-column-on-`User`).

**Contract**: `MagicLinkToken(SQLModel, table=True)`, `__tablename__ = "magic_link_token"`: `id: int | None` (PK), `user_id: int = Field(foreign_key="user.id", index=True)`, `token_hash: str = Field(index=True, unique=True)`, `expires_at: datetime`, `used_at: datetime | None = Field(default=None)`, `created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))`.

#### 5. New Alembic migration — `password_hash` column + `magic_link_token` table

**File**: `alembic/versions/<generated-hash>_add_auth_fields.py` (generate via `uv run alembic revision --autogenerate -m "add auth fields"`)

**Intent**: Apply the model changes from #3 and #4 to the database, additively.

**Contract**: `down_revision = 'eb719c984d34'`. `upgrade()` adds a nullable `password_hash` varchar column to `user`, and creates the `magic_link_token` table (FK to `user.id`, unique index on `token_hash`, index on `user_id`). Per the lessons.md rule on destructive downgrades, `downgrade()` must include a comment noting that dropping `password_hash` destroys stored password hashes and dropping `magic_link_token` destroys in-flight tokens — should only run before real user data exists.

### Success Criteria:

#### Automated Verification:

- [ ] `uv sync` installs the new dependencies cleanly
- [ ] `uv run python -c "from app.models.user import User"` imports without error
- [ ] `uv run alembic upgrade head` applies cleanly against a local/dev Postgres (per the migration-testing lesson: use a dev/staging DB, not the production Fly Postgres, for this check)
- [ ] `uv run alembic downgrade -1` then `uv run alembic upgrade head` round-trips cleanly on the same dev DB

#### Manual Verification:

- [ ] `psql`/asyncpg check on the dev DB: `user` has the new nullable `password_hash` column, and `magic_link_token` table exists with the expected columns/indexes/FK

---

## Phase 2: Session middleware, route protection, base templates

### Overview

Wire up `SessionMiddleware`, add `AuthRedirectMiddleware`, set up Jinja2 templates with a base layout, and convert `/` into a minimal authenticated landing page.

### Changes Required:

#### 1. `app/auth/__init__.py`, `app/auth/middleware.py` — route protection

**File**: `app/auth/middleware.py` (new package `app/auth/`)

**Intent**: Enforce "every route requires a session except a small allowlist" at the middleware layer, so future feature routes (S-01+) are protected by default.

**Contract**: `AuthRedirectMiddleware` (Starlette `BaseHTTPMiddleware` subclass) — for requests where `request.session.get("user_id")` is absent and `request.url.path` doesn't start with `/health`, `/auth/`, or `/static/`, return a 303 redirect to `/auth/login`. Otherwise call `call_next`.

#### 2. `app/auth/dependencies.py` — current-user lookup

**File**: `app/auth/dependencies.py`

**Intent**: Give routes a way to load the full `User` row for the session's `user_id`.

**Contract**: `async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User` — reads `request.session["user_id"]`, loads the `User` by primary key. Since `AuthRedirectMiddleware` already guarantees a `user_id` exists for protected routes, this raises `HTTPException(401)` only in the should-never-happen case (e.g. user deleted mid-session).

#### 3. `app/main.py` — middleware, templates, static files, routers

**File**: `app/main.py`

**Intent**: Assemble the app: session handling, route protection, templating, and the authenticated landing page.

**Contract**: Add `SessionMiddleware(app, secret_key=SECRET_KEY, same_site="lax", https_only=True)` then `AuthRedirectMiddleware` (order matters — session must be parsed first). Mount `/static` via `StaticFiles`. Create a module-level `Jinja2Templates(directory="app/templates")`. Replace the JSON `/` handler with one that renders `templates/index.html`, passing the current user (via `get_current_user`). `/health` stays JSON and public.

#### 4. `app/templates/base.html`, `app/templates/index.html`

**File**: `app/templates/base.html`, `app/templates/index.html`

**Intent**: Minimal shared layout (nav with logged-in email + logout link) and a landing page proving the authenticated shell works.

**Contract**: `base.html` defines `{% block content %}`; `index.html` extends it and shows "Logged in as {{ user.email }}" plus a logout link/form. No styling requirements beyond plain HTML.

### Success Criteria:

#### Automated Verification:

- [ ] `uv run python -c "from app.main import app"` imports without error
- [ ] `uv run uvicorn app.main:app` starts without error and `/health` returns 200 JSON without a session

#### Manual Verification:

- [ ] Visiting `/` without a session cookie redirects (303) to `/auth/login` (route doesn't exist yet until Phase 3 — confirm the redirect happens, a 404 on `/auth/login` afterward is expected at this point)
- [ ] `/health` is reachable without a session

---

## Phase 3: Password auth — signup, login, logout

### Overview

Add `/auth/signup`, `/auth/login`, `/auth/logout` with Jinja2 forms, using `pwdlib[argon2]` for hashing.

### Changes Required:

#### 1. `app/auth/security.py` — password hashing

**File**: `app/auth/security.py`

**Intent**: Centralize password hash/verify so routes don't touch `pwdlib` directly.

**Contract**: `hash_password(password: str) -> str` and `verify_password(password: str, hashed: str) -> bool`, built on `pwdlib.PasswordHash.recommended()` (argon2).

#### 2. `app/routes/auth.py` — auth router

**File**: `app/routes/auth.py` (new)

**Intent**: Signup creates a `User` with a hashed password and starts a session immediately (no email verification, per the agreed signup flow). Login verifies credentials and starts a session. Logout clears the session.

**Contract**:
- `GET /auth/signup` renders `auth/signup.html`; `POST /auth/signup` (form: `email`, `password`) creates the user, sets `request.session["user_id"]`, redirects to `/`. On duplicate email (unique constraint violation), re-render the form with an error.
- `GET /auth/login` renders `auth/login.html`; `POST /auth/login` (form: `email`, `password`) looks up the user by email, verifies the hash (treat `password_hash is None` — a magic-link-only account — as invalid credentials with a message pointing at magic-link login), sets the session, redirects to `/`. On failure, re-render with a generic "invalid email or password" error (don't reveal which field was wrong).
- `POST /auth/logout` clears `request.session` and redirects to `/auth/login`.

#### 3. `app/templates/auth/signup.html`, `app/templates/auth/login.html`

**File**: `app/templates/auth/signup.html`, `app/templates/auth/login.html`

**Intent**: Minimal forms for the routes above; login page links to `/auth/signup` and (once Phase 4 lands) `/auth/magic-link`.

**Contract**: Plain HTML forms posting to the routes in #2, extending `base.html`.

#### 4. `app/main.py` — register the auth router

**File**: `app/main.py`

**Intent**: Wire the new router into the app.

**Contract**: `app.include_router(auth_router)`.

### Success Criteria:

#### Automated Verification:

- [ ] `uv run python -c "from app.main import app"` imports without error
- [ ] `uv run alembic upgrade head` still applies cleanly (no new migration this phase, but confirms no model/migration drift)

#### Manual Verification:

- [ ] Sign up with a new email + password → redirected to `/` and shown "Logged in as ..."
- [ ] Log out → redirected to `/auth/login`; visiting `/` redirects back to `/auth/login`
- [ ] Log in with the same credentials → redirected to `/`
- [ ] Sign up again with the same email → form re-renders with a duplicate-email error
- [ ] Log in with a wrong password → form re-renders with a generic invalid-credentials error

---

## Phase 4: Magic-link auth — request + verify

### Overview

Add `/auth/magic-link` (request form + send) and `/auth/magic-link/verify` (consume token), sending email via `fastapi-mail` over Gmail SMTP.

### Changes Required:

#### 1. `app/auth/tokens.py` — magic-link token helpers

**File**: `app/auth/tokens.py`

**Intent**: Generate and verify the signed, time-limited magic-link token described in "Critical Implementation Details".

**Contract**: `create_magic_link_token() -> tuple[str, str, datetime]` returns `(serialized_token, token_hash, expires_at)` — generates a random token via `secrets.token_urlsafe(32)`, hashes it with `sha256` (`token_hash`/`expires_at` = now + 15 min, for the caller to persist as a `MagicLinkToken` row), and signs `{"tok": token}` with `itsdangerous.URLSafeTimedSerializer(SECRET_KEY, salt="magic-link")` (`serialized_token`, for the email link). `verify_magic_link_token(serialized: str, max_age: int = 900) -> str | None` unsigns and returns the raw `token`, or `None` on `BadSignature`/`SignatureExpired`.

#### 2. `app/auth/mail.py` — email sending

**File**: `app/auth/mail.py`

**Intent**: Send the magic-link email via Gmail SMTP.

**Contract**: `FastMail` configured from `ConnectionConfig(MAIL_USERNAME=..., MAIL_PASSWORD=..., MAIL_FROM=..., MAIL_SERVER=..., MAIL_PORT=..., MAIL_STARTTLS=True, MAIL_SSL_TLS=False, USE_CREDENTIALS=True, VALIDATE_CERTS=True)` reading from `app.config`. `async def send_magic_link_email(to_email: str, link_url: str) -> None` sends a plain-text message containing `link_url`.

#### 3. `app/routes/auth.py` — magic-link routes

**File**: `app/routes/auth.py`

**Intent**: Request flow gets-or-creates the user by email, stores the token hash + expiry, and emails the verify link. Verify flow validates the token and the stored hash/expiry, then logs the user in and invalidates the token (single-use).

**Contract**:
- `GET /auth/magic-link` renders `auth/magic_link_request.html`; `POST /auth/magic-link` (form: `email`) — load `User` by email or create one (`password_hash=None`) if absent, call `create_magic_link_token`, persist a new `MagicLinkToken` row (`user_id`, `token_hash`, `expires_at`), send the email with a link to `/auth/magic-link/verify?token=<serialized>`, render `auth/magic_link_sent.html` (same response regardless of whether the account existed, to avoid leaking account existence).
- `GET /auth/magic-link/verify?token=...` — call `verify_magic_link_token`; on `None`, render an error page. Otherwise look up `MagicLinkToken` by `sha256(token)`; if no row, `used_at` is set, or `expires_at` has passed, render an error page. Otherwise set `used_at = now()`, load the `User` via `user_id`, set `request.session["user_id"]`, redirect to `/`.

#### 4. `app/templates/auth/magic_link_request.html`, `app/templates/auth/magic_link_sent.html`, `app/templates/auth/magic_link_error.html`

**File**: `app/templates/auth/magic_link_request.html`, `app/templates/auth/magic_link_sent.html`, `app/templates/auth/magic_link_error.html`

**Intent**: Request form, "check your email" confirmation, and an error page for expired/invalid/replayed links (with a link back to `/auth/magic-link` to request a new one).

**Contract**: Plain HTML, extending `base.html`. `login.html` (Phase 3) gets a link to `/auth/magic-link`.

### Success Criteria:

#### Automated Verification:

- [ ] `uv run python -c "from app.main import app"` imports without error

#### Manual Verification:

- [ ] Requesting a magic link for a *new* email sends a real email (Gmail SMTP) and creates a `User` row with `password_hash=NULL`
- [ ] Clicking the link logs the user in and redirects to `/`
- [ ] Re-clicking the same (now-consumed) link shows the error page
- [ ] Requesting a magic link for an *existing* (password) account, then logging in via the link, also works
- [ ] Requesting a second magic link does not invalidate the first — both links independently log the user in (until each is used once)

---

## Phase 5: Change password (recovery path)

### Overview

Add a logged-in-only `/auth/change-password` page so a user who recovered access via magic link can set/update their password — satisfying PRD Open Question 2 (account recovery).

### Changes Required:

#### 1. `app/routes/auth.py` — change-password route

**File**: `app/routes/auth.py`

**Intent**: Let an authenticated user set a new password, covering both "magic-link-only" accounts (no password yet) and existing password accounts (change).

**Contract**: `GET /auth/change-password` renders `auth/change_password.html` (protected by `AuthRedirectMiddleware` since it's not in the allowlist); `POST /auth/change-password` (form: `password`, `password_confirm`) — if the two don't match, re-render with an error; otherwise hash and set `current_user.password_hash`, commit, re-render with a success message.

#### 2. `app/templates/auth/change_password.html`

**File**: `app/templates/auth/change_password.html`

**Intent**: Form for the route above; linked from `index.html` (Phase 2) so it's reachable from the landing page.

**Contract**: Plain HTML form extending `base.html`, two password fields.

### Success Criteria:

#### Automated Verification:

- [ ] `uv run python -c "from app.main import app"` imports without error

#### Manual Verification:

- [ ] Visiting `/auth/change-password` while logged out redirects to `/auth/login`
- [ ] A magic-link-only account (no password) can set a password here, then log out and log back in with email + password
- [ ] An existing password account can change its password here, then log out and log back in with the new password (old password no longer works)

---

## Testing Strategy

### Unit Tests:

No test framework exists yet (out of scope to introduce here — Module 3 territory per `CLAUDE.md`). Automated verification per phase is limited to import/startup/migration checks.

### Integration Tests:

None — covered by Manual Verification per phase.

### Manual Testing Steps:

See per-phase Manual Verification above; together they cover: signup, login, logout, duplicate-email, wrong-password, magic-link for new and existing accounts, link replay/expiry, single-active-link invalidation, and password change/recovery.

## Performance Considerations

None beyond existing constraints (`pool_size=3, max_overflow=0` in `app/db.py` is unchanged and sufficient for auth queries).

## Migration Notes

- The Phase 1 migration is additive only (one nullable column on `user`, plus a new `magic_link_token` table) — safe to apply to the production Fly Postgres without data loss.
- Per the migration-testing habit recorded in memory, run the upgrade/downgrade round-trip (Phase 1 automated verification) against a local/dev database first, not directly against the production Fly Postgres.
- `downgrade()` must carry an in-file comment per the `lessons.md` rule: dropping `password_hash` destroys stored password hashes, and dropping `magic_link_token` destroys in-flight tokens.

## References

- Related research: `context/changes/auth-scaffold/research.md`
- F-01 migration pattern: `alembic/versions/eb719c984d34_initial_schema.py`
- DB session pattern: `app/db.py:16-23`
- Config pattern: `app/config.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Foundation — dependencies, config, migration

#### Automated

- [x] 1.1 `uv sync` installs the new dependencies cleanly — 2190d64
- [x] 1.2 `uv run python -c "from app.models.user import User"` imports without error — 2190d64
- [x] 1.3 `uv run alembic upgrade head` applies cleanly against a local/dev Postgres — 2190d64
- [x] 1.4 `uv run alembic downgrade -1` then `uv run alembic upgrade head` round-trips cleanly on the same dev DB — 2190d64

#### Manual

- [x] 1.5 `user` has the new nullable `password_hash` column, and `magic_link_token` table exists with expected columns/indexes/FK (dev DB) — 2190d64

### Phase 2: Session middleware, route protection, base templates

#### Automated

- [x] 2.1 `uv run python -c "from app.main import app"` imports without error — e1ef7ac
- [x] 2.2 `uv run uvicorn app.main:app` starts; `/health` returns 200 JSON without a session — e1ef7ac

#### Manual

- [x] 2.3 Visiting `/` without a session redirects (303) to `/auth/login` — e1ef7ac
- [x] 2.4 `/health` is reachable without a session — e1ef7ac

### Phase 3: Password auth — signup, login, logout

#### Automated

- [x] 3.1 `uv run python -c "from app.main import app"` imports without error — bd09749
- [x] 3.2 `uv run alembic upgrade head` still applies cleanly — bd09749

#### Manual

- [x] 3.3 Sign up with a new email + password → redirected to `/`, shown "Logged in as ..." — bd09749
- [x] 3.4 Log out → redirected to `/auth/login`; `/` redirects back to `/auth/login` — bd09749
- [x] 3.5 Log in with the same credentials → redirected to `/` — bd09749
- [x] 3.6 Sign up again with the same email → duplicate-email error — bd09749
- [x] 3.7 Log in with a wrong password → generic invalid-credentials error — bd09749

### Phase 4: Magic-link auth — request + verify

#### Automated

- [x] 4.1 `uv run python -c "from app.main import app"` imports without error — 0e95c5b

#### Manual

- [x] 4.2 Magic link for a new email sends a real email and creates a `User` with `password_hash=NULL` — 0e95c5b
- [x] 4.3 Clicking the link logs the user in and redirects to `/` — 0e95c5b
- [x] 4.4 Re-clicking the consumed link shows the error page — 0e95c5b
- [x] 4.5 Magic link for an existing password account also works — 0e95c5b
- [x] 4.6 Requesting a second link does not invalidate the first — both independently log the user in (until each used once) — 0e95c5b

### Phase 5: Change password (recovery path)

#### Automated

- [x] 5.1 `uv run python -c "from app.main import app"` imports without error

#### Manual

- [x] 5.2 `/auth/change-password` while logged out redirects to `/auth/login`
- [x] 5.3 Magic-link-only account can set a password, then log in with email + password
- [x] 5.4 Existing password account can change password, old password stops working
