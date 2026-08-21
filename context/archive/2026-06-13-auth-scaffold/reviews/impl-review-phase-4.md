<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Auth Scaffold (F-02)

- **Plan**: context/changes/auth-scaffold/plan.md
- **Scope**: Phase 4 of 5
- **Date**: 2026-06-23
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — Email sent after DB commit; SMTP failure leaves orphaned token

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:118-121
- **Detail**: `session.commit()` on line 118 writes the `MagicLinkToken` row, then `send_magic_link_email` is called on line 121. If SMTP raises (bad credentials, timeout), the exception propagates unhandled — the user sees the 500 page, the "check your email" page never renders, but the token row is already committed. Seen live during testing with wrong Gmail credentials.
- **Fix A ⭐ Recommended**: Catch SMTP errors and render a user-facing error page
  - Approach: Wrap `send_magic_link_email` in try/except; on failure, re-render `magic_link_request.html` with an error message ("Could not send the email — please try again."). Token stays committed but expires in 15 min — harmless.
  - Strength: User gets an actionable error instead of 500. Minimal code change, matches real failure mode already observed.
  - Tradeoff: Does not prevent the orphaned DB row; just hides it from the user gracefully.
  - Confidence: HIGH
  - Blind spot: None significant.
- **Fix B**: Move email send before commit; only commit if send succeeds
  - Approach: Call `send_magic_link_email` before `session.commit()`. If send raises, session is rolled back by `get_session` — no row committed.
  - Strength: Eliminates the orphaned row entirely.
  - Tradeoff: Network call inside an open DB transaction is an anti-pattern (holds the connection during I/O). If commit then fails after a successful send, the user gets an email but no DB row.
  - Confidence: MEDIUM — both orderings have a failure window; Fix A's window is smaller in practice.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — `app/routes/auth.py` now wraps `send_magic_link_email` in try/except; on failure, re-renders `magic_link_request.html` with "Could not send the email — please try again."

### F2 — Any email silently creates a user account (no rate limiting)

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:106-109
- **Detail**: The get-or-create pattern avoids email enumeration (correct) but means submitting any email creates a `User` row with `password_hash=NULL`. A script submitting many fake emails would fill the user table with phantom accounts. No rate limiting exists anywhere in the codebase.
- **Fix A ⭐ Recommended**: Accept as-is, add a code comment documenting the tradeoff
  - Approach: Add a comment near the get-or-create block noting the phantom-account risk and the MVP decision to defer rate limiting.
  - Strength: Rate limiting requires infrastructure (Redis or per-IP in-memory store) out of scope for this phase. A personal hobby app with a single real user is not a realistic spam target.
  - Tradeoff: Leaves the vector open.
  - Confidence: HIGH — consistent with the MVP scope in the plan's "What We're NOT Doing".
  - Blind spot: None significant for this app's threat model.
- **Fix B**: Defer user creation to the verify route
  - Approach: Store the email in the token row (new nullable column) instead of the User table. Create the User row only when the link is verified.
  - Strength: Eliminates phantom rows entirely.
  - Tradeoff: Requires schema migration and significant redesign of the token model.
  - Confidence: MEDIUM — more work than this phase warrants.
  - Blind spot: None significant.
- **Decision**: FIXED via alternative approach — `POST /auth/magic-link` now only sends email if user already exists; unknown emails return the same "check your email" page silently. No phantom accounts created. Magic link is login-only, not a registration path. Recorded as plan amendment in `change.md`.

### F3 — Magic-link routes have no exception handling (inconsistent with signup/login)

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency / Safety & Quality
- **Location**: app/routes/auth.py:103-152
- **Detail**: `signup` uses `try/except IntegrityError` around `session.commit()` and renders a user-facing error. The magic-link request route has no `try/except` at all — any DB error or SMTP error hits the 500 handler. Directly related to F1: catching the SMTP error fixes both findings simultaneously.
- **Fix**: Add `try/except` around `session.commit()` and the email send, re-rendering `magic_link_request.html` with an error on failure. (This subsumes F1's Fix A.)
- **Decision**: FIXED — subsumed by F1 (try/except on email send) and F2 (login-only removes the no-exception-handling path for the create-user branch entirely).

### F4 — @app.exception_handler(Exception) and HTTPException interaction

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/main.py:29-31
- **Detail**: A concern was raised that the catch-all `Exception` handler might swallow `HTTPException` (401/404) and return 500 HTML instead. In practice FastAPI registers a built-in `HTTPException` handler and Starlette's MRO lookup finds it before the generic `Exception` handler. Manual tests confirmed 401 redirect and 404 behaviour are correct. Flagged for awareness; no action needed unless behaviour changes.
- **Fix**: N/A — observe only. Verify again if HTTPException handling ever appears broken.
- **Decision**: ACCEPTED — behaviour confirmed correct in manual testing; FastAPI's built-in HTTPException handler takes precedence.

### F5 — Double-commit pattern: route commits, then get_session commits again

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: app/routes/auth.py:118; app/db.py (get_session commit on yield-exit)
- **Detail**: Routes that call `session.commit()` manually are followed by `get_session`'s commit-on-success yield-exit. SQLAlchemy handles the no-op second commit gracefully, but the pattern is inconsistent — someone adding post-commit logic to `get_session` could be surprised. Benign now.
- **Fix**: N/A — acceptable for now. Document which layer owns the commit if this becomes confusing.
- **Decision**: ACCEPTED — no-op second commit is harmless; get_session's commit is the normal case for routes that don't commit manually.

### F6 — itsdangerous serializer provides integrity/expiry, not confidentiality

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/auth/tokens.py:17
- **Detail**: `URLSafeTimedSerializer` HMAC-signs the payload but does not encrypt it. The raw token is recoverable from the URL (base64-encoded inside the serialized string). This is normal for magic-link flows — the URL IS the secret. Worth a one-line comment so a future reader doesn't assume the token is encrypted.
- **Fix**: Add a short comment in `tokens.py` clarifying that the serializer provides tamper-detection and expiry, not confidentiality.
- **Decision**: FIXED — one-line comment added above `_serializer` in `app/auth/tokens.py`.

### F7 — lru_cache mailer holds credentials for process lifetime

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/auth/mail.py:15
- **Detail**: The `lru_cache` mailer is constructed once and reused. In tests, if env vars are patched after import, the cached mailer uses stale credentials. Not a production concern. Add `_get_mailer.cache_clear()` to test teardown when tests are introduced (Module 3 territory).
- **Fix**: N/A — note only; handle in Module 3 test setup.
- **Decision**: ACCEPTED — not a production concern; add `_get_mailer.cache_clear()` to test teardown when tests are introduced.
