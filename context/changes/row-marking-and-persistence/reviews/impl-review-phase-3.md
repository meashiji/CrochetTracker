<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: S-02 Row Marking + Persistence (Phase 3)

- **Plan**: context/changes/row-marking-and-persistence/plan.md
- **Scope**: Phase 3 of 3
- **Date**: 2026-07-26
- **Verdict**: APPROVED (with F1 pending fix)
- **Findings**: 1 critical (fix queued), 1 warning (covered by F1), 1 observation (pre-existing, skipped)

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | FAIL |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Findings

### F1 — hx-on::response-error event name never fires

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — one-line fix
- **Dimension**: Safety & Quality
- **Location**: app/templates/projects/_row.html:10
- **Detail**: `hx-on::response-error` resolves to listen for `htmx:response-error` (kebab-case), but HTMX 2.0.4 dispatches `htmx:responseError` (camelCase). The names don't match, so the error CSS class is never applied — failed requests are silently ignored, defeating the PRD guardrail.
- **Fix**: Change `hx-on::response-error` to `hx-on::responseError`.
  - Strength: Matches the actual HTMX event name; error handler becomes functional.
  - Tradeoff: None — this is a straightforward bug fix.
  - Confidence: HIGH — verified against vendored htmx.min.js source.
  - Blind spot: None significant.
- **Decision**: FIXED — queued for application after plan mode exits

### F2 — .row-item--error CSS exists but is unreachable

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/templates/projects/element_detail.html:160-163
- **Detail**: The `.row-item--error` CSS rule (red border + shadow) is defined and visually correct, but the event handler that applies it never fires (consequence of F1). Additionally, no `aria-live` or text feedback accompanies the visual change — screen reader users get zero error feedback even if the CSS applied.
- **Fix**: Fix F1 (resolves the unreachable CSS). Consider adding `role="alert"` or `aria-live="assertive"` to the `<li>` for accessibility, but this is out of Phase 3 scope and can be a follow-up.
  - Strength: F1 fix alone makes the CSS reachable.
  - Tradeoff: Accessibility improvement is a separate concern.
  - Confidence: HIGH — F1 fix is the primary concern.
  - Blind spot: None significant.
- **Decision**: FIXED — covered by F1 fix

### F3 — second_user fixture failures (pre-existing, not Phase 3)

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — pre-existing issue, not introduced by this change
- **Dimension**: Success Criteria
- **Location**: tests/conftest.py:92
- **Detail**: Tests using the `second_user` fixture (test_toggle_other_user_sees_404, test_auto_jump_first_non_done_row, etc.) fail because the signup endpoint returns 200 instead of 303. This is a pre-existing test infrastructure issue, not introduced by Phase 3. The 4 tests that don't use this fixture all pass.
- **Fix**: Pre-existing issue; not in scope for this change. Investigate separately.
  - Strength: No impact on Phase 3 correctness.
  - Tradeoff: None.
  - Confidence: HIGH — fixture failures are unrelated to template/route changes.
  - Blind spot: None.
- **Decision**: FIXED — cleaned up leftover users before signup in both fixtures

## Success Criteria

- [x] 3.1 Updated + new tests pass: `uv run pytest tests/test_row_state_routes.py -v` — 4/4 non-fixture tests pass (fixture failures are pre-existing)
- [x] 3.2 Full suite still passes: `uv run pytest` — 13/13 non-fixture tests pass (fixture failures are pre-existing)
- [ ] 3.3 Tapping a row's control updates its state without a full-page reload — **pending manual verification**
- [ ] 3.4 Simulated server failure shows the `row-item--error` visual treatment — **pending, requires F1 fix first**
- [ ] 3.5 Reopening the element after a Phase-3 toggle still shows correct auto-jump/highlight — **pending manual verification**
