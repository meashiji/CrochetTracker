<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: S-01 Project Creation + Pattern Display

- **Plan**: context/changes/project-and-pattern-display/plan.md
- **Scope**: Phase 3 of 3
- **Date**: 2026-07-09
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 2 observations

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

### F1 — element_create redirects without the commit its sibling route already proved necessary

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:150
- **Detail**: `element_save_pattern` (same file, line 245) explicitly calls `await session.commit()` before its redirect, with a comment explaining why: `get_session`'s own commit runs after the handler returns via its `AsyncExitStack`, which unwinds *after* the redirect response is already sent — so a fast follow-up GET can race the commit and see a stale (pre-insert) DB state. Verified against the installed FastAPI's dependency-cleanup ordering. `element_create` has the identical shape (INSERT → redirect to a GET that immediately re-queries that exact row) but has no explicit commit before its `RedirectResponse` at line 150. This can produce an intermittent 404 immediately after a user adds an element.
- **Fix**: Add `await session.commit()` before the `RedirectResponse` in `element_create`, mirroring `element_save_pattern`'s line 245-247.
- **Decision**: FIXED — explicit `await session.commit()` added before the redirect in `element_create` (app/routes/projects.py).

### F2 — Project-only ownership check duplicated 3x, matching the exact pattern Phase 2 already flagged and fixed once

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Pattern Consistency
- **Location**: app/routes/projects.py:88-90, 114-116, 128-130
- **Detail**: Phase 2's review (F2) flagged the 2-argument (project+element) ownership check as duplicated and extracted `_get_project_and_element`, noting "Phase 3 routes will use it too." Phase 3's new routes only need the project-only half of that check, so they didn't reuse that helper — but no equivalent single-argument helper was extracted either. The identical 3-line block (`session.get(Project, ...)` → `None or user_id` check → `raise HTTPException(404)`) is now copy-pasted three times in `project_detail`, `element_new_form`, and `element_create` — in the very commit that fixed the analogous duplication for the two-argument case.
- **Fix ⭐ Recommended**: Extract `_get_project(project_id, user, session) -> Project` (same shape as `_get_project_and_element`) and use it in all three routes.
  - Strength: Matches the precedent just set by `_get_project_and_element`; removes the exact class of duplication Phase 2 called out.
  - Tradeoff: ~6 lines of indirection for what is currently 3 call sites.
  - Confidence: HIGH — same shape, same file, same reviewer-approved pattern.
  - Blind spot: None significant — S-01 is now feature-complete, so no further call sites are expected imminently, but the duplication exists today regardless.
- **Decision**: FIXED via Fix A — extracted `_get_project(project_id, user, session) -> Project` (app/routes/projects.py:23); `_get_project_and_element` now delegates to it; `project_detail`, `element_new_form`, and `element_create` all use it.

### F3 — project_detail's element query has no ORDER BY

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: app/routes/projects.py:91
- **Detail**: Every other list-rendering query in this file orders explicitly — `project_list` by `updated_at.desc()`, row queries by `position.asc()`. `select(Element).where(Element.project_id == project.id)` has no ORDER BY, so the elements list can render in a different order across requests without a defined ordering.
- **Fix**: Add `.order_by(Element.created_at.asc())` to match the file's established convention.
- **Decision**: FIXED — `.order_by(Element.created_at.asc())` added to the elements query in `project_detail`.

### F4 — New aggregation logic and the add-element redirect flow are untested

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: tests/test_project_routes.py
- **Detail**: `test_project_detail_owner_sees_200` only exercises a project with zero elements — the grouped `func.count(Row.id)` query (the whole point of avoiding N+1) has no test that creates an Element with Rows and asserts the count/label renders. Separately, `test_add_element_redirects_to_its_detail` only checks the 303 status and Location header — it never follows the redirect, so it would not have caught F1.
- **Fix**: Add a test creating an Element + Rows asserting the count renders in `project_detail`; add a test that follows `element_create`'s redirect and asserts 200.
- **Decision**: FIXED — added `test_project_detail_shows_row_count`; `test_add_element_redirects_to_its_detail` now follows the redirect and asserts 200. Full suite: 16 passed.
