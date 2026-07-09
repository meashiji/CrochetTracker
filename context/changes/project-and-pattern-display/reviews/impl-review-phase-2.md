<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: S-01 Project Creation + Pattern Display

- **Plan**: context/changes/project-and-pattern-display/plan.md
- **Scope**: Phase 2 of 3
- **Date**: 2026-07-05
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

## Plan Adherence Note

Three deliberate deviations from the plan — all justified:
- `Form(default="")` instead of `Form(...)`: correct fix; `Form(...)` rejects empty string before the route body runs, bypassing the error path.
- Unconditional bulk-delete (vs "if element already has rows"): DELETE on empty rows is a SQL no-op; simpler code, same result.
- `await session.commit()` before redirect: necessary; `get_session`'s own commit runs after the 303 is sent; the follow-up GET arrives before the write is durable without this.

## Findings

### F1 — No input ceiling on pattern_text

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:67
- **Detail**: `pattern_text` has no size cap. A very large submit cascades through parse_pattern into a nested RowState insert loop, holding one of three DB connections (pool_size=3, max_overflow=0). A few concurrent large submissions exhaust the pool and hang all requests.
- **Fix A ⭐ Recommended**: Add early rejection in the POST handler before parse_pattern:
  ```python
  if len(pattern_text) > 50_000:
      return templates.TemplateResponse(..., {"error": "Pattern too large — max 50 000 characters."})
  ```
  - Strength: Single-line guard; mirrors the name-length check already in project_create.
  - Tradeoff: 50 000 chars is a rough heuristic; can be tightened later.
  - Confidence: HIGH — same shape as existing name-length guard.
  - Blind spot: Doesn't prevent valid but deeply nested patterns if those become possible.
- **Fix B**: Add `maxlength="50000"` to the textarea (browser-side only, must pair with Fix A).
  - Strength: Zero server cost.
  - Tradeoff: Bypassed by direct HTTP; not a substitute for server-side guard.
  - Confidence: MED — incomplete without Fix A.
  - Blind spot: None as an addition to Fix A.
- **Decision**: Fix A applied — `MAX_PATTERN_LENGTH = 50_000` guard added in `element_save_pattern` (app/routes/projects.py:130). Fix B not applied.

### F2 — Ownership check duplicated verbatim in GET and POST

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Pattern Consistency
- **Location**: app/routes/projects.py:62 and :80
- **Detail**: The 8-line ownership check (fetch project, check user_id, fetch element, check project_id, raise 404) is copy-pasted into both element_detail and element_save_pattern. Phase 3 will add more routes needing the same check. If access rules change, all sites must stay in sync.
- **Fix A ⭐ Recommended**: Extract a private async helper now:
  ```python
  async def _get_project_and_element(
      project_id: int, element_id: int,
      user: User, session: AsyncSession
  ) -> tuple[Project, Element]:
      project = await session.get(Project, project_id)
      if project is None or project.user_id != user.id:
          raise HTTPException(status_code=404)
      element = await session.get(Element, element_id)
      if element is None or element.project_id != project.id:
          raise HTTPException(status_code=404)
      return project, element
  ```
  - Strength: One place to update; Phase 3 routes use it for free.
  - Tradeoff: ~10 lines of indirection.
  - Confidence: HIGH — pattern used elsewhere in auth.py for similar helpers.
  - Blind spot: Phase 3 may land before this is extracted, multiplying duplication.
- **Fix B**: Leave as-is, extract during Phase 3.
  - Strength: Zero change now; Phase 3 will add more call sites making extraction more obvious.
  - Tradeoff: Phase 3 may copy-paste again if not flagged explicitly.
  - Confidence: MED — requires discipline at Phase 3 time.
  - Blind spot: Phase 3 reviewer may not notice the pre-existing duplication.
- **Decision**: Fix A applied — `_get_project_and_element()` helper added (app/routes/projects.py:23), used by both `element_detail` and `element_save_pattern`. Phase 3 routes will use it too.

### F3 — RowState inserts use individual session.add() calls

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:140
- **Detail**: Nested loop emits one INSERT per RowState. Plan explicitly noted "ORM adds are acceptable for S-01." At ≤200 rows × 1 rep this is fine; worth replacing with session.add_all() before S-02 ships if the loop is reused for marking.
- **Fix**: Replace individual adds with `session.add_all([RowState(...) for rep in new_reps for row in new_rows])`.
- **Decision**: Applied — RowState inserts now use `session.add_all()` (app/routes/projects.py:161).

### F4 — Jinja2 autoescaping is implicit, not declared

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/templates/projects/element_detail.html:79
- **Detail**: `{{ row.content }}` renders user-supplied text. Starlette enables autoescaping for `.html` by default — safe today. A future custom Jinja2 Environment without autoescaping would re-open stored XSS.
- **Fix**: No code change needed now. Record as a rule: always verify autoescaping is on before adding `| safe` to any template that renders user content.
- **Decision**: No action — documented as a standing rule for future template changes.
