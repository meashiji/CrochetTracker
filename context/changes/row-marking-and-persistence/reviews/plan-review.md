<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Row marking + persistence (S-02, north star)

- **Plan**: `context/changes/row-marking-and-persistence/plan.md`
- **Mode**: Deep
- **Date**: 2026-07-09
- **Verdict**: SOUND (after fixes)
- **Findings**: 2 critical · 1 warning · 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | FAIL → PASS (F1, F2 fixed) |
| Plan Completeness | WARNING → PASS (F3 fixed) |

## Grounding

7/7 existing paths ✓ (`app/routes/projects.py`, `app/models/progress.py`, `app/models/project.py`, `app/templates/base.html`, `app/templates/projects/element_detail.html`, `app/main.py`, `tests/test_project_routes.py`) · 6/6 symbols ✓ (`_get_project_and_element`, `get_session`, `RowStateEnum`, `ElementRepetition`, `MAX_PATTERN_LENGTH`, `templates.TemplateResponse(request, ...)` call signature) · brief↔plan ✓ · Progress↔phase mechanical check ✓ (all Phase 1-3 Success Criteria bullets have matching `- [ ]` entries in `## Progress`; Phase blocks use plain bullets only)

Also externally verified (not assumed): htmx's default behavior — a 4xx/5xx response is **not** swapped into the DOM by default; it fires `htmx:responseError` instead ([htmx docs](https://htmx.org/docs/#requests)) — and `hx-on::response-error` is valid htmx 2.x inline-event syntax ([htmx docs](https://htmx.org/attributes/hx-on/)). Both facts are load-bearing for Phase 3's error-handling design and check out.

## Findings

### F1 — `_rerender_with_error` would crash once `element_detail.html` requires `row_states`

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 — item 4 (Row-state query on GET)
- **Detail**: `element_save_pattern`'s `_rerender_with_error` closure (`app/routes/projects.py:189-205`) re-renders `projects/element_detail.html` on a validation failure (pattern too long, or produces no rows), passing the element's *existing* rows. Phase 1 makes `element_detail.html` require `row_states` (and, from Phase 2, `current_row_id`) for its new `_row.html` include — but the original plan only updated the `element_detail` GET route's context, not this second call site. On an element that already has rows and a validation failure is triggered, the re-render would hit a Jinja `UndefinedError` on `row_states.get(row.id)` instead of showing the intended error banner — a regression in an existing, working code path.
- **Fix**: Extract row-state computation into a shared helper (`_build_row_states`) and call it from both `element_detail` and `_rerender_with_error`. Added as Phase 1 item 4a; a corresponding test case added to Testing Strategy.
- **Decision**: FIXED

### F2 — `element_detail` GET would crash for an element with no pattern saved yet

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 — item 4 (Row-state query on GET)
- **Detail**: `ElementRepetition` rows are only created inside `element_save_pattern` (`app/routes/projects.py:229-234`), never at element-creation time. An element with no pattern pasted yet has zero `ElementRepetition` rows. The original Phase 1 contract said to "fetch the element's `ElementRepetition`" unconditionally — a literal `.scalar_one()` on zero rows raises `NoResultFound`, breaking the existing "No pattern pasted yet" happy path that `element_detail` currently serves without error.
- **Fix**: `_build_row_states` (the same helper from F1's fix) now returns `{}` immediately when `rows` is empty, before ever querying `ElementRepetition`. A corresponding auto-jump edge-case test ("no pattern/rows yet") already existed in Testing Strategy; clarified to call out that this is exactly the guard being tested.
- **Decision**: FIXED

### F3 — `is_current` handling in the Phase 3 fragment response was left as an unresolved TBD

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 — item 3 (Toggle route returns a fragment)
- **Detail**: The original contract read "`is_current`: <recomputed per Phase 2, or left as whatever it was pre-toggle — see note below>" — this is placeholder-style hedging rather than a decision; per the plan's own "No Open Questions in Final Plan" convention this needed resolving before implementation, not during it.
- **Fix**: Resolved explicitly — the toggled row's fragment always renders `is_current=False` (a fixed value, not recomputed). Rationale folded into the plan: the current-row highlight is a page-load-only cue (FR-007's literal "on opening a project"); recomputing it per-toggle would require re-running the whole auto-jump scan on every request, which the plan's own "Live re-jump ... out of scope" item already excludes, and `False` is correct in both cases that matter (row was current: user is now actively engaging with it, cue has served its purpose for this visit; row wasn't current: `False` is simply correct).
- **Decision**: FIXED

## Notes

No findings raised against End-State Alignment, Lean Execution, or Architectural Fitness:
- **End-State Alignment**: the three phases compose correctly into the stated end state (mark → persist → auto-jump → 100ms swap); no last-mile gap found.
- **Lean Execution**: the shared `_row.html` partial and the two small helper functions (`_build_row_states`, `_first_unmarked_row_id`) are proportionate — no premature abstraction, no unrelated "while we're here" work.
- **Architectural Fitness**: HTMX is introduced as a single vendored file plus one new route pattern, consistent with `context/foundation/tech-stack.md:29`'s already-committed stack choice, not a fresh architectural debate. No pattern proliferation found (RowState/ElementRepetition usage matches how `element_save_pattern` already uses them).

The two CRITICAL findings (F1, F2) were both instances of the same root cause — the plan updated the primary `element_detail` GET route's context but didn't trace the *other* place the same template gets rendered (`_rerender_with_error`), nor the *edge case* where the new query's precondition (rows exist) doesn't hold. Both are now closed by making row-state computation a single shared, edge-case-guarded helper called from every render path, so `element_detail.html` can never be rendered without the context its own template now requires.
