---
date: 2026-06-13T17:11:35Z
researcher: Claude Sonnet 4.6
git_commit: 9c0fd261342e6d9afbbd5888880bc1a59ea15e21
branch: main
repository: CrochetTracker
topic: "Auth library selection for F-02 auth-scaffold"
tags: [research, codebase, auth, fastapi, sessions, magic-link]
status: complete
last_updated: 2026-06-13
last_updated_by: Claude Sonnet 4.6
---

# Research: Auth library selection for F-02 auth-scaffold

**Date**: 2026-06-13T17:11:35Z
**Researcher**: Claude Sonnet 4.6
**Git Commit**: 9c0fd261342e6d9afbbd5888880bc1a59ea15e21
**Branch**: main
**Repository**: CrochetTracker

## Research Question

Pick an auth library for F-02 (`auth-scaffold`), keeping to the agreements recorded in `context/foundation/roadmap.md`: email + password OR magic link, session middleware protecting all project routes, per-user data isolation, FastAPI + Jinja2/HTMX server-rendered stack, solo 4-week timeline.

## Summary

**Recommendation: a custom/minimal session-cookie + magic-link flow**, built directly on Starlette's built-in `SessionMiddleware` (itsdangerous-backed signed cookies), `pwdlib`/argon2 (or `passlib`+bcrypt) for password hashing, and `itsdangerous.URLSafeTimedSerializer` for time-limited magic-link tokens, with **Resend** for transactional email delivery.

This beats the two FastAPI-specific libraries evaluated:
- **fastapi-users** is architected around JWT/OAuth2 token backends for API-first apps, has no built-in magic-link strategy, requires bending its `SQLAlchemyBaseUserTable` mixins onto the existing SQLModel `User` table, and — as of March 2026 — is in **maintenance mode** (security fixes only; successor toolkit unreleased).
- **authlib** is OAuth2/OIDC client/provider tooling only — no first-party email+password or magic-link support; relevant only if "Sign in with Google" is added later (out of scope per PRD's flat single-account model).
- **fastapi-login** is a reasonable lighter-weight fallback (session-cookie wrapper, bring-your-own password check) but has no magic-link support either and is a small, low-activity project.

The custom flow is the standard, well-documented FastAPI + Jinja2 pattern (multiple tutorials, e.g. Scalekit's passwordless guide), integrates with the existing `User` SQLModel via one additive Alembic migration (adds nullable `password_hash`, `magic_link_token`/expiry fields — consistent with the F-01 plan's stated deferral of these fields to F-02), and is estimated at ~100-200 lines total.

## Detailed Findings

### Current codebase state (from F-01)

- `app/models/user.py:9-11` — `User` table has only `id`, `email` (unique, indexed), `created_at`. No `password_hash` or token fields — confirmed as an intentional F-01 deferral (plan.md: "Auth fields ... belong to F-02").
- `app/db.py:7-23` — async engine (`pool_size=3, max_overflow=0`), `AsyncSessionLocal` (`expire_on_commit=False`), `get_session()` FastAPI dependency with commit/rollback. New auth code should follow this same dependency-injection style.
- `app/config.py` — `DATABASE_URL` normalisation (postgres→asyncpg, sslmode→ssl). No `SECRET_KEY` or session-config env var yet — F-02 will need to add one (for `SessionMiddleware` cookie signing and `itsdangerous` magic-link tokens).
- `app/main.py` — minimal FastAPI app, `/health` + `/` only. `app/routes/`, `app/templates/`, `app/static/` exist but are empty — F-02 is the first phase to populate them (Jinja2 setup, login/register/magic-link routes and templates).
- `pyproject.toml` — deps: `alembic`, `asyncpg`, `fastapi==0.136.1`, `sqlmodel`, `uvicorn`. Nothing for Jinja2, sessions, password hashing, or email yet — all need to be added in F-02.
- `alembic/versions/eb719c984d34_initial_schema.py` — current single migration creates exactly the 6 F-01 tables; `user` table (lines 25-31) has no auth fields. F-02's migration must be **additive** (new nullable columns on `user`), per the F-01 plan's "Migration Notes" convention.
- `context/foundation/lessons.md` — one entry: destructive migration downgrades should be flagged in-file. Applies if F-02's migration ever needs a destructive downgrade (it shouldn't — additive columns only).
- `context/changes/auth-scaffold/` — only `change.md` exists (empty Notes); no prior research/plan. No other `context/changes/**` or `context/archive/**` folder references auth, sessions, or magic links.

### Library comparison (external research)

| Option | Magic-link fit | Session-cookie fit | SQLModel integration | Maintenance |
|---|---|---|---|---|
| **fastapi-users** | None built-in; would require a custom auth backend bolted onto its token-backend architecture | `CookieTransport` exists but the library is API/JWT-first, awkward for Jinja2 page flows | Needs `SQLAlchemyBaseUserTable` mixins shoehorned onto existing `User` SQLModel | **Maintenance mode since ~March 2026** (v15.0.5) — security fixes only, successor unreleased |
| **authlib** | None — OAuth2/OIDC only | N/A — no app session management | N/A | Active, but out of scope (no first-party email/password/magic-link) |
| **fastapi-login** | None built-in (bring your own) | Good — its core purpose, JWT-in-cookie wrapper with `@login_required` | Trivial — callback-based, ORM-agnostic | Small/low-activity (~672 stars), "sustainable" per Snyk |
| **Custom (SessionMiddleware + pwdlib/argon2 + itsdangerous)** | **This is the standard documented pattern** for magic links in FastAPI (signed, time-limited token emailed, verified on click) | Best — `SessionMiddleware` is built into Starlette, zero extra deps | Zero friction — one additive migration on existing `User` model | Lowest burden — itsdangerous already a Starlette transitive dep |

**Email delivery for magic links**: Resend (clean Python SDK, dedicated FastAPI guide, free tier ~100/day / 3,000/month — plenty for a solo-user MVP) is the simplest option. SMTP via Mailtrap is a vendor-neutral fallback.

## Code References

- `app/models/user.py:9-11` — User model fields, target of the additive auth migration
- `app/db.py:7-23` — async session/engine pattern to mirror for any new DB access in auth routes
- `app/config.py` — env var normalisation pattern; add `SECRET_KEY` here for session/token signing
- `app/main.py:1-13` — current app instance; F-02 adds `SessionMiddleware`, Jinja2 templates, and route routers here
- `alembic/versions/eb719c984d34_initial_schema.py:25-31` — current `user` table definition; F-02 migration adds columns additively
- `context/foundation/lessons.md` — destructive-downgrade lesson (low relevance if F-02 migration is additive-only)

## Architecture Insights

- The project consistently uses async SQLModel + a single shared `get_session()` dependency — new auth dependencies (`get_current_user`, login-required guards) should follow the same DI pattern rather than introducing a parallel auth-framework session model.
- F-01 explicitly deferred auth fields to F-02 "via an additive migration" — this is already the agreed plan; the custom-flow recommendation is consistent with it (add `password_hash: str | None`, `magic_link_token: str | None`, `magic_link_expires_at: datetime | None` as nullable columns).
- No env-var/secrets convention exists yet for non-DB secrets (e.g., `SECRET_KEY`, email API key). F-02 should establish this via Fly secrets (`fly secrets set SECRET_KEY=... RESEND_API_KEY=...`), following the same pattern F-01 used for `DATABASE_URL`.

## Historical Context (from prior changes)

- `context/changes/db-schema-and-models/plan.md` (F-01) — "What We're NOT Doing" explicitly excludes auth fields on User ("those belong to F-02"), and the roadmap's F-01 entry notes F-02 is unlocked once the User model exists. No conflicting prior decisions found.

## Related Research

- None — this is the first research artifact for `auth-scaffold`.

## Open Questions

1. **Email provider account setup** — Resend (or chosen alternative) requires creating an account and API key; this is a manual step similar to F-01's Fly Postgres provisioning (G-gate in a future plan).
2. **Password hashing library choice** — `pwdlib` (argon2) vs `passlib` (bcrypt): `passlib` is in low-maintenance mode upstream; `pwdlib` is the newer FastAPI-ecosystem-recommended successor. Plan should pick one explicitly (lean `pwdlib[argon2]`).
3. **Magic-link token storage** — store the hashed token + expiry on the `User` row (single active magic link at a time) vs. a separate `magic_link_token` table (supports multiple in-flight tokens, e.g., multi-device requests). PRD's "single account, flat model" suggests the simpler single-column approach is sufficient — confirm in `/10x-plan`.
4. **fastapi-login as fallback** — if the custom magic-link flow proves more complex than expected mid-build, `fastapi-login` remains a documented fallback for session-cookie management with password-only login for v1.
