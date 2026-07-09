<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Write-Path and Ownership Integration Tests

- **Plan**: context/changes/testing-write-path-ownership/plan.md
- **Scope**: Phase 1 + Phase 2 (full plan)
- **Date**: 2026-07-09
- **Verdict**: APPROVED (after one fix applied during review)
- **Findings**: 0 critical, 1 warning (fixed), 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS (was FAIL pre-fix — see F1) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Test cleanup only ran on the happy path, risking a cascading leak

- **Severity**: was ❌ CRITICAL (test-suite-only blast radius, not production) — now FIXED
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `tests/test_pattern_paste.py` (all 7 tests, pre-fix)
- **Detail**: Each test called a `_teardown(db_session, element.id)` helper as the *last line* of the test
  body. Since no FK cascades exist in this schema, an assertion failure anywhere earlier in the test
  (e.g. the record-count check at line 49 in the original draft) would skip teardown, leaving
  `RowState`/`Row`/`ElementRepetition`/`Element` rows behind. `test_user`'s own fixture teardown
  (`delete(Project).where(...)`) would then hit a live FK violation from the orphaned `Element` row,
  aborting *that* teardown before it reached `delete(User)` — leaking the `test@example.com` user row too,
  and breaking every subsequent test's signup with a duplicate-email error. This risk pattern pre-dates this
  change (the existing `test_project_routes.py` manually cleans `Row`/`Element` the same way), but this PR
  meaningfully widened the blast radius by adding two more dependent tables (`ElementRepetition`,
  `RowState`) beneath the existing chain.
- **Fix**: Converted the `_make_project_and_element`/`_teardown` helper pair into a single pytest fixture
  `project_and_element(test_user, db_session)` that yields `(project, element)` and does the cleanup after
  the `yield` — pytest runs fixture-teardown code unconditionally once the test's call phase completes,
  regardless of pass/fail/error, unlike a plain function call at the end of a test body.
  - Verified empirically: temporarily forced an assertion failure in
    `test_pattern_paste_creates_matching_db_records` (mid-session, run against `crochet_tracker_test_writepath`)
    — result was "1 failed, 6 passed" with no cascading `IntegrityError` or duplicate-signup failures in the
    other 6 tests of the same session. Reverted the deliberate failure afterward; full suite (`pytest tests/ -v`)
    passes 26/26.
- **Decision**: FIXED

### F2 — `second_user` yields a tuple while `test_user` yields a bare `User`

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/conftest.py` (`second_user` fixture)
- **Detail**: Intentional and documented in the fixture's docstring (the shared `async_client` can only hold
  one session, so `second_user` must own its client) — a reasonable, explained divergence, not an
  inconsistency introduced by accident.
- **Decision**: SKIPPED (acceptable as documented; not worth a `NamedTuple` wrapper for one call-site pattern
  used identically in both new test files)

### F3 — `updated_at` bump assertion relies on wall-clock ordering

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/test_pattern_paste.py::test_pattern_paste_bumps_project_updated_at`
- **Detail**: Asserts `project.updated_at > updated_before` based on two `datetime.now(timezone.utc)` calls
  separated by an HTTP round-trip + DB write. Theoretically flaky under extremely fast/coarse clock
  resolution, but this is the same risk class as any timestamp-ordering assertion and not unique to this
  test. No precedent in the codebase for a different approach (e.g. freezing time).
- **Decision**: ACCEPTED (risk is negligible in practice; ran the full suite 3x during implementation with no
  flakes observed)

## Success Criteria Verification

- `uv run pytest tests/test_project_routes.py -v` — 8/8 passed (3 new IDOR tests, no regressions).
- `uv run pytest tests/test_pattern_paste.py -v` — 7/7 passed.
- `uv run pytest tests/ -v` — 26/26 passed (full suite, no regressions), run 3x for stability, plus once more
  after the F1 fix.
- All Phase 1 and Phase 2 "Automated Verification" Progress checkboxes are `[x]` with commit shas attached.
- No Manual Verification items in this plan (test-only change, no user-facing behavior).
