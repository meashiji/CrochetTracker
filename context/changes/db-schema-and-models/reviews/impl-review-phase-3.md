<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Database Schema + SQLModel Models Implementation Plan

- **Plan**: context/changes/db-schema-and-models/plan.md
- **Scope**: Phase 3 of 3
- **Date**: 2026-06-13
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Unplanned Dockerfile + app/config.py changes

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: Dockerfile, app/config.py
- **Detail**: Phase 3's "Changes Required" lists 5 items; commit 1269ace also touches Dockerfile (`COPY alembic.ini`/`alembic/`) and app/config.py (sslmode→ssl translation). Neither is in the plan's file list. Both were required to make Phase 3's own success criterion (`fly deploy` exit 0) actually pass — discovered live during deployment (missing script_location, then asyncpg rejecting `sslmode`). Verified: asyncpg's `ssl=` kwarg accepts libpq-style strings via `SSLMode.parse()` (disable/allow/prefer/require/verify-ca/verify-full), so the translation is correct for all sslmode values, not just "disable".
- **Fix**: Add a short addendum note to plan.md's Phase 3 section documenting these two files as in-scope fixes discovered during deployment verification (so the plan stays an accurate record). No code change needed — already correct.
- **Decision**: FIXED — added section "4b. Dockerfile + app/config.py — deploy-time fixes" to plan.md Phase 3 Changes Required

### F2 — Initial migration's downgrade() is fully destructive

- **Severity**: 👀 OBSERVATION
- **Dimension**: Safety & Quality (Data Safety)
- **Location**: alembic/versions/eb719c984d34_initial_schema.py
- **Detail**: `downgrade()` drops all 6 tables and the `rowstateenum` enum — standard for revision 1 (down_revision=None), but nothing in the migration file itself flags this as destructive. The plan's "Migration Notes" section already documents that downgrade should never run against production once S-01 adds data, so the risk is covered at the plan level, not the code level. No fix proposed — plan-level documentation is sufficient for an initial migration.
- **Decision**: ACCEPTED-AS-RULE — recorded in context/foundation/lessons.md ("Destructive initial-migration downgrade should be flagged in the migration file itself"); not applied to current migration file

### F3 — No retry on release_command DB connection

- **Severity**: 👀 OBSERVATION
- **Dimension**: Safety & Quality (Reliability)
- **Location**: alembic/env.py:61-70
- **Detail**: `run_async_migrations()` opens one connection with no retry/backoff. A transient DB hiccup during `fly deploy` would fail the release_command and abort the deploy (Fly keeps the previous version running, so this fails safe — just noisy). Acceptable for MVP scale; no action needed now.
- **Decision**: SKIPPED
