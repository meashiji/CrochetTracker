<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Database Schema + SQLModel Models

- **Plan**: context/changes/db-schema-and-models/plan.md
- **Scope**: Phase 2 of 3
- **Date**: 2026-06-10
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — RowState.updated_at never auto-refreshes

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: app/models/progress.py:23 (and app/models/project.py:14)
- **Detail**: The plan's contract for RowState says `updated_at` is "updated on every write." It was set via `default_factory` only (insert-time), never refreshed on update. Same gap on `Project.updated_at`.
- **Fix**: Add `sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}` to both fields.
- **Decision**: FIXED

### F2 — RowState.row_id missing index

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: app/models/progress.py:20
- **Detail**: Every other FK column (`user_id`, `project_id`, `element_id`, `element_repetition_id`) has `index=True`. `row_id` didn't, despite being frequently joined/filtered alongside `element_repetition_id`.
- **Fix**: Add `index=True` to `RowState.row_id`.
- **Decision**: FIXED

### F3 — No ON DELETE behavior on FKs

- **Severity**: 👀 OBSERVATION
- **Dimension**: Architecture
- **Location**: all FK columns
- **Detail**: No `ondelete=` configured anywhere; Postgres FK default is RESTRICT. Deleting a Project/Element/ElementRepetition will raise FK violations rather than cascading. May be intentional (handled at app layer in S-01+).
- **Decision**: SKIPPED

### F4 — repeat_count >= 1 not enforced at DB level

- **Severity**: 👀 OBSERVATION
- **Dimension**: Safety & Quality
- **Location**: app/models/project.py:24
- **Detail**: `Field(default=1, ge=1)` validates at the Pydantic layer only; direct SQL writes could insert `repeat_count <= 0`. Likely fine for MVP.
- **Decision**: SKIPPED
