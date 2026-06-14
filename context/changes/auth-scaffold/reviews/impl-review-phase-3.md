<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Auth Scaffold (F-02)

- **Plan**: context/changes/auth-scaffold/plan.md
- **Scope**: Phase 3 of 5
- **Date**: 2026-06-14
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Same tz-aware/tz-naive bug left unfixed in project/element/row_state

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Scope Discipline / Safety & Quality
- **Location**: app/models/project.py:13,15-16,28; app/models/progress.py:24-25
- **Detail**: This phase fixed the tz-aware-default vs. tz-naive-column mismatch (the cause of the signup 500) for `user` and `magic_link_token` only. `Project.created_at/updated_at`, `Element.created_at`, and `RowState.updated_at` use the identical `datetime.now(timezone.utc)` default_factory but their columns are still plain `TIMESTAMP` (no `sa_type=DateTime(timezone=True)`). Verified `project`/`element`/`row_state` are currently empty in the dev DB, so fixing now is a pure schema change with zero data to convert.
- **Fix A ⭐ Recommended**: Fix it now while the tables are empty
  - Strength: Same migration shape as 583dfd4fd36a, applied while zero rows exist — cheapest possible time to fix, and closes the exact bug class that just caused a 500.
  - Tradeoff: Slightly expands Phase 3's footprint into F-01's tables, outside auth-scaffold's stated scope.
  - Confidence: HIGH — same fix, same verification path already proven in this phase.
  - Blind spot: None significant (tables confirmed empty).
- **Fix B**: Defer to a follow-up / lesson, fix at start of S-01
  - Strength: Keeps Phase 3 scoped strictly to auth.
  - Tradeoff: Risk of forgetting until S-01 hits the same 500 with real project data already inserted, making the fix more involved.
  - Confidence: MEDIUM — depends on discipline to revisit before S-01.
  - Blind spot: None significant.
- **Decision**: PENDING

### F2 — Login timing oracle reveals account existence

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:65
- **Detail**: When `user is None`, `verify_password` is short-circuited and never called — the unknown-email path skips an argon2 hash verification (~tens of ms), making it measurably faster than the wrong-password path. Classic user-enumeration timing oracle.
- **Fix**: Always call `verify_password` (against a fixed dummy hash when `user is None`) so both paths take comparable time.
- **Decision**: PENDING

### F3 — "No password set" message confirms account existence

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:58-63
- **Detail**: For a magic-link-only account (`password_hash is None`), login returns a distinct message ("This account has no password set...") vs. "Invalid email or password" for an unknown email — directly confirming the email is registered. This matches the plan's contract (plan explicitly asks for this message), but is a deliberate enumeration tradeoff worth a conscious decision.
- **Fix A ⭐ Recommended**: Keep as-is (matches plan intent)
  - Strength: Plan explicitly specified this UX — helpful guidance to magic-link users outweighs the minor enumeration risk for a single-user-per-account hobby app with no sensitive data.
  - Tradeoff: Email enumeration is possible via the login form.
  - Confidence: HIGH — plan's contract is unambiguous on this point.
  - Blind spot: None significant.
- **Fix B**: Collapse to generic "Invalid email or password" everywhere
  - Strength: Removes the enumeration vector entirely.
  - Tradeoff: Magic-link-only users get a confusing generic error instead of guidance toward `/auth/magic-link`.
  - Confidence: MEDIUM — would require a plan amendment since this contradicts the Phase 3 contract.
  - Blind spot: None significant.
- **Decision**: PENDING

### F4 — No minimum password length / non-empty check on signup

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:24-25
- **Detail**: `password: str = Form(...)` only enforces presence, not minimum length — an empty string is a valid form value and would be hashed and stored as-is.
- **Fix**: Add a minimum-length check (e.g. 8 chars) before `hash_password`, re-rendering `signup.html` with an error on failure.
- **Decision**: PENDING

### F5 — No email normalization (case sensitivity)

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:28,55
- **Detail**: `"Foo@x.com"` and `"foo@x.com"` are distinct accounts. Consider lowercasing/stripping email on signup and login lookups.
- **Fix**: Lowercase/strip email before storage and lookup.
- **Decision**: PENDING

### F6 — No CSRF token on state-changing auth forms

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/templates/auth/signup.html, login.html; app/main.py
- **Detail**: `SessionMiddleware(same_site="lax")` provides reasonable baseline protection. Likely an accepted gap at this MVP stage — flagged for awareness, not blocking.
- **Fix**: N/A — accept as-is unless threat model changes.
- **Decision**: PENDING

### F7 — Only IntegrityError is caught on signup commit

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/auth.py:30-38
- **Detail**: Other exceptions (e.g. connection drop) propagate as an unhandled 500. `get_session` rolls back safely either way; acceptable for MVP without a custom error page.
- **Fix**: N/A — acceptable for now.
- **Decision**: PENDING

### F8 — TIMESTAMP→TIMESTAMPTZ cast is session-timezone-dependent

- **Severity**: 👁️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: alembic/versions/583dfd4fd36a_user_and_magic_link_timestamps_to_.py:24-39
- **Detail**: `ALTER COLUMN TYPE ... TIMESTAMPTZ` interprets existing naive values using the DB session's timezone (dev DB: `Europe/Warsaw`, not UTC). Verified `user`/`magic_link_token` were empty at migration time, so no values were actually affected this time. Worth remembering if a future TIMESTAMP→TIMESTAMPTZ migration runs against tables with existing data.
- **Fix**: N/A — no action needed now; keep in mind for future migrations of this shape.
- **Decision**: PENDING
