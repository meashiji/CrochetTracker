# Auth Scaffold (F-02) — Plan Brief

> Full plan: `context/changes/auth-scaffold/plan.md`
> Research: `context/changes/auth-scaffold/research.md`

## What & Why

CrochetTracker needs accounts before any project-tracking feature (S-01+) can store per-user data. F-02 adds session-based login via email+password OR magic link, protects every route by default, and gives users a way to recover access if they forget their password — unblocking the whole "critical tracking path" (F-02 → S-01 → S-02, the north star).

## Starting Point

`app/main.py` is a 13-line stub (`/health`, `/` both JSON, no auth). `User` (`app/models/user.py`) has only `id`, `email`, `created_at`. No Jinja2, sessions, hashing, or email deps exist yet. F-01 already established the async SQLModel + Alembic + Fly Postgres baseline this builds on.

## Desired End State

Any route other than `/health`, `/auth/*`, `/static/*` requires a session, enforced by middleware. A visitor can sign up (email+password, immediate login) or request a magic-link email; either way they land on `/` showing "Logged in as ...". A logged-in user can change their password at `/auth/change-password` — the recovery path for a forgotten password.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Auth methods this phase | Both password and magic link | Matches PRD's "email+password OR magic link" exactly, one cohesive migration | Plan |
| Password hashing | `pwdlib[argon2]` | Modern FastAPI-ecosystem-recommended successor to passlib | Research |
| Magic-link token storage | Separate `magic_link_token` table, multiple concurrent valid tokens allowed | Deliberate choice over the research recommendation (columns on `User`) — supports multi-device requests and a token history; the user wanted this pattern as a learning exercise for future projects | Plan (revised) |
| Email delivery | `fastapi-mail` + Gmail SMTP | No new third-party account, reuses existing Gmail via app password | Plan |
| Signup flow | Immediate login, no email verification | Simplest flow for solo MVP, no "pending" state | Plan |
| Account recovery (PRD OQ2) | Magic link in → change password | Reuses magic-link infra; just adds one small page | Plan |
| Route protection | Global middleware (allowlist), not per-route deps | Future routes (S-01+) are protected by default | Plan |

## Scope

**In scope:**
- Additive migration: `password_hash` on `user`, plus a new `magic_link_token` table (`user_id` FK, `token_hash`, `expires_at`, `used_at`)
- `SessionMiddleware` + `AuthRedirectMiddleware` (global route protection)
- Jinja2 base layout + authenticated `/`
- Signup, login, logout (password)
- Magic-link request + verify (email via Gmail SMTP)
- Change-password page (recovery path)

**Out of scope:**
- Email verification on signup
- Separate "forgot password" token flow
- Cleanup job for expired/used `magic_link_token` rows
- OAuth / social login
- S-01 project views (only a placeholder authenticated `/`)
- `.env`/dotenv tooling

## Architecture / Approach

`SessionMiddleware` (itsdangerous-signed cookies) holds `user_id`. `AuthRedirectMiddleware` runs after it and redirects to `/auth/login` for any non-allowlisted path without a session — so every future route is protected by default. Password and magic-link flows both end by setting `session["user_id"]` and redirecting to `/`. Magic-link tokens are signed with `itsdangerous.URLSafeTimedSerializer` (tamper/expiry-proof independent of the DB) and additionally hashed+stored as rows in a new `magic_link_token` table (FK to `user`) for single-use enforcement — each row tracks its own `used_at`, so multiple concurrent valid tokens per user are allowed.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Foundation | Deps, config (`SECRET_KEY`, Gmail SMTP), additive migration: `password_hash` on `User` + new `magic_link_token` table | Migration must be tested against a dev DB, not prod (per lessons.md habit) |
| 2. Session + protection + templates | `SessionMiddleware`, `AuthRedirectMiddleware`, base layout, authenticated `/` | Middleware ordering (session must parse before redirect check) |
| 3. Password auth | Signup, login, logout | Duplicate-email and wrong-password error handling |
| 4. Magic-link auth | Request + verify via Gmail SMTP | Gmail app-password setup is a manual gate; single-use/expiry correctness |
| 5. Change password | Recovery path for logged-in users | Must work for both magic-link-only and password accounts |

**Prerequisites:** F-01 done (✓). Manual gate: Gmail account with 2FA enabled + app password generated, then `fly secrets set SECRET_KEY=... MAIL_USERNAME=... MAIL_PASSWORD=... MAIL_FROM=...`.
**Estimated effort:** ~5 sessions, one per phase.

## Open Risks & Assumptions

- Gmail SMTP's ~500/day sending limit is assumed sufficient for a solo-user MVP; revisit (e.g. move to Resend) if that ever becomes a constraint.
- No test framework exists; automated verification per phase is limited to import/startup/migration checks — manual verification carries most of the confidence.

## Success Criteria (Summary)

- An unauthenticated visitor cannot reach any page except `/health` and `/auth/*`.
- A user can sign up, log in, log out, and recover access via magic link + change password — all verified manually per phase.
- `fly deploy` succeeds with the new migration and Fly secrets in place.
