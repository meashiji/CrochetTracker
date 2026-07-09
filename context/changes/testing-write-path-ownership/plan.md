# Write-Path and Ownership Integration Tests — Implementation Plan

## Overview

Add integration tests that prove two of the three Phase 2 risks are protected: cross-user IDOR at the
element and pattern-paste level (risk #3), and pattern-paste DB write correctness (risk #6). Risk #1
(row-mark silent-failure) has no implementing route yet and stays deferred, per research's recommendation —
substituted with the closest reachable analogue: proving the pattern-paste write path is all-or-nothing
(a rejected submission leaves zero partial DB writes, not a half-written row set).

## Current State Analysis

- `project-and-pattern-display` shipped all 3 phases (`context/changes/project-and-pattern-display/plan.md`,
  all Progress items `[x]`). Routes now exist: `GET/POST /projects/new`, `GET /projects/{id}`,
  `GET/POST /projects/{id}/elements/new`, `GET/POST /projects/{id}/elements/{element_id}`.
- `app/routes/projects.py` implements ownership via two helpers: `_get_project` (404 if project missing or
  `user_id` mismatch) and `_get_project_and_element` (404 if element missing or `project_id` mismatch) —
  confirmed at `app/routes/projects.py:23-40`.
- The pattern-paste route (`app/routes/projects.py:178-252`) does: validate length ≤ `MAX_PATTERN_LENGTH`
  (50 000 chars) → `parse_pattern()` → if empty, re-render with error, no DB write → else bulk-delete old
  RowState/Row/ElementRepetition → insert new Row × N → insert ElementRepetition × repeat_count → `flush()`
  → insert RowState × N×repeat_count → bump `project.updated_at` → `session.commit()` → 303 redirect.
- `tests/test_project_routes.py` already covers: project-detail 200/404 (owner vs. cross-user, project-level
  IDOR only), row-count display, add-element redirect, add-element blank-name validation. It does **not**
  cover: element-detail or pattern-paste routes at all, cross-user IDOR at the element level, or any DB-verify
  test of the pattern-paste write.
- `tests/conftest.py` provides `async_client`, `db_session`, `test_user` (single user, shared client). No
  fixture exists yet for a second, independently-authenticated user — needed for cross-user IDOR tests
  (research Open Question 1).
- No row-mark route exists anywhere in `app/` (confirmed via grep) — risk #1 stays out of scope, consistent
  with `research.md`'s recommendation to defer it to a future rollout phase.

### Key Discoveries

- `app/routes/projects.py:23-40` — `_get_project` / `_get_project_and_element` ownership helpers, shared by
  every project/element route.
- `app/routes/projects.py:178-252` — pattern-paste route; `session.flush()` at line 236 is load-bearing
  (populates PKs before RowState inserts reference them).
- `app/services/pattern.py` — `parse_pattern(text) -> list[tuple[int, str]]`, 1-based position, strips lines,
  drops blanks.
- `tests/conftest.py:70-89` — `test_user` fixture pattern: signup via `async_client`, query the `User` row,
  yield, delete `Project` rows then the `User` row on teardown (no cascade defined on FKs).
- `tests/test_project_routes.py:43-59` — existing project-level IDOR test pattern: create a second `User`
  row directly via `db_session` (not a full second client), assert 404, manual teardown. This works for
  project-level IDOR (no session needed for the *victim*, only the requester), but element/pattern-paste
  cross-user tests need the *attacker* to be a distinct authenticated session — the shared `async_client`
  can only hold one session cookie at a time.

## Desired End State

Two new/extended test files give automated proof of risk #3 and risk #6:

- Cross-user IDOR is proven at the element level (`GET` and `POST` to another user's element, and to an
  element that exists but belongs to a different project than the one in the URL) — all return 404, and no
  DB state changes as a side effect of the rejected request.
- Pattern-paste DB writes are proven correct: after a successful paste, the exact `Row`, `ElementRepetition`,
  and `RowState` records in the DB match `parse_pattern()`'s output — count, position, content, and
  `not_started` state — not just the parser's return value.
- Re-paste (replacing an existing pattern) is proven to fully replace rows, not append or leave orphans.
- Rejected pastes (blank result, oversized input) are proven to leave the DB completely unchanged — the
  write is all-or-nothing.
- `uv run pytest tests/ -v` passes with the new tests included, run against `crochet_tracker_test_writepath`.

### Key Discoveries (verification targets)

- `GET /projects/{project_id}/elements/{element_id}` returns 404 for a non-owning user.
- `POST /projects/{project_id}/elements/{element_id}` returns 404 for a non-owning user, and does not create
  any `Row`/`ElementRepetition`/`RowState` rows as a side effect.
- An `element_id` valid in the DB but belonging to a different project than the `project_id` in the URL
  returns 404 (tests the second half of `_get_project_and_element`, not just the first).
- After a successful pattern-paste POST, `Row` count/positions/content and `ElementRepetition` count and
  `RowState` count/state exactly match `parse_pattern(pattern_text)`.
- A rejected paste (blank parse result or `> MAX_PATTERN_LENGTH`) leaves the row/rep/state counts for that
  element at whatever they were before the request (zero for a fresh element, unchanged for a re-paste
  rejection).

## What We're NOT Doing

- Not testing risk #1 (row-mark) — no route exists; deferred to a future rollout phase per research.md.
- Not adding a shared ownership-check test helper to `app/` — ownership enforcement is already implemented
  and this change only adds tests, no production code changes (unless a real bug is found, per task
  constraints).
- Not testing template rendering/HTML content beyond simple substring assertions already used in
  `test_project_routes.py` (test-plan §7 excludes template rendering as a tested surface).
- Not adding tests for `POST /projects/{id}/elements/new` cross-user IDOR — already implicitly covered by
  the shared `_get_project` helper and out of the R3/R6 scope; the element-creation route is a P2 nice-to-have
  only if time allows, not required for risk coverage.
- Not testing `repeat_count > 1` scenarios (ElementRepetition × N) — S-01 always uses `repeat_count=1`;
  out of scope for this rollout phase, would be revisited if/when repeat-count UI ships (roadmap S-03).
- Not mocking DB failures or infrastructure (task constraint: only test write-path failures reachable without
  mocking infra we don't control — the validation-rejection paths are the reachable analogue).

## Implementation Approach

Two phases, in dependency order: first establish the second-user fixture (needed by both risk areas), then
split test content by risk. Phase 1 covers R3 (cross-user IDOR, element-level) since it only needs the new
fixture plus routes that already exist. Phase 2 covers R6 (pattern-paste DB write correctness) plus the
all-or-nothing write verification, and reuses the Phase 1 fixture for the cross-user pattern-paste case.

## Phase 1: Second-user fixture + cross-user element IDOR tests (Risk #3)

### Overview

Add a `second_user` fixture to `tests/conftest.py` that creates an independently authenticated user with its
own `AsyncClient`/session, then add element-level cross-user IDOR tests to `tests/test_project_routes.py`.

### Changes Required

#### 1. `second_user` fixture

**File**: `tests/conftest.py`

**Intent**: Give tests a second, independently authenticated user + client, so cross-user requests can be
made with a real session rather than by directly inserting a `User` row (which only proves DB-level ownership,
not the full authenticated-request path).

**Contract**: New async fixture `second_user(db_session)` that opens its own `AsyncClient` (same
`ASGITransport`/`base_url="https://testserver"` pattern as `async_client`), signs up a second user
(`email="second@example.com"`), queries the resulting `User` row, yields `(user, client)`, and on teardown
deletes that user's `Project` rows then the `User` row (mirrors `test_user`'s teardown shape). The fixture
manages its own `AsyncClient` context manager internally (it is not the shared `async_client` fixture, since
each client can only hold one session cookie).

#### 2. Cross-user element IDOR tests

**File**: `tests/test_project_routes.py`

**Intent**: Prove that authenticated user B cannot read or write user A's element via direct URL, including
the case where the element and project IDs are individually valid but don't belong to each other.

**Contract**: Add three tests, using `test_user` as the owner (A) and `second_user` as the attacker (B):
- `test_element_detail_other_user_sees_404` — A creates a project + element (via `db_session`); B's client
  `GET`s A's element URL; assert 404.
- `test_element_save_pattern_other_user_sees_404` — B's client `POST`s `pattern_text` to A's element URL;
  assert 404; then query `Row` for that element via `db_session` and assert the count is still 0 (the
  rejected request must not have written anything).
- `test_element_detail_wrong_project_sees_404` — A creates two projects, each with its own element; request
  `GET /projects/{project_A1.id}/elements/{element_belonging_to_project_A2.id}` (same owner, mismatched
  project/element pairing); assert 404. This exercises the second ownership check in
  `_get_project_and_element` (project_id match), not just the first (user_id match).

### Success Criteria

#### Automated Verification

- `uv run pytest tests/test_project_routes.py -v` passes, including the three new tests.
- `uv run pytest tests/ -v` passes in full (no regressions in existing tests from the new fixture).

#### Manual Verification

- None — this phase is pure test code with no user-facing behavior change.

---

## Phase 2: Pattern-paste DB write correctness + all-or-nothing verification (Risk #6)

### Overview

Add a new test file covering the pattern-paste route's DB write behavior: correct record creation on
success, correct replacement on re-paste, and no partial writes on rejection.

### Changes Required

#### 1. Pattern-paste write tests

**File**: `tests/test_pattern_paste.py` (new)

**Intent**: Prove the DB records created by a pattern-paste POST exactly match `parse_pattern()`'s output —
not just that the parser is correct (already covered by `tests/test_pattern.py`) — and that the write is
transactional (all rows written, or none).

**Contract**: Uses `test_user`, `async_client`, `db_session`. Each test creates its own `Project` + `Element`
via `db_session` (mirroring `test_project_routes.py`'s pattern), posts to
`/projects/{project_id}/elements/{element_id}`, then queries `Row`/`ElementRepetition`/`RowState` directly.
Tests:
- `test_pattern_paste_creates_matching_db_records` — POST a 3-line pattern; assert `Row` count/position/content
  match `parse_pattern(pattern_text)` exactly (zip and compare, not just count); assert one `ElementRepetition`
  with `repetition_number == 1`; assert `RowState` count equals `Row` count and every state is
  `RowStateEnum.not_started`.
- `test_pattern_paste_bumps_project_updated_at` — capture `project.updated_at` before, POST a pattern, refresh
  from DB, assert `updated_at` increased (covers the explicit-bump code path called out in
  `project-and-pattern-display/plan.md`'s Critical Implementation Details).
- `test_pattern_repaste_replaces_rows` — POST an initial pattern, capture the `Row.id` set; POST a different
  pattern (different line count) to the same element; assert the new `Row` set has the new content/count and
  none of the original `Row.id`s remain (proves delete-then-insert, not append); assert `RowState` count
  matches the new `Row` count (not the old + new).
- `test_pattern_paste_blank_result_writes_nothing` — POST whitespace-only `pattern_text` to a fresh element
  (no existing rows); assert 200 with the error message in the response body; assert zero `Row` rows exist
  for that element afterward.
- `test_pattern_paste_oversized_writes_nothing` — POST a `pattern_text` longer than `MAX_PATTERN_LENGTH`
  (50 001+ chars) to a fresh element; assert 200 with the length-error message; assert zero `Row` rows exist.
- `test_pattern_paste_rejected_repaste_leaves_existing_rows_intact` — paste a valid pattern first (rows exist);
  then POST a blank pattern to the same element; assert the rejection leaves the *original* rows untouched
  (count and content unchanged) — this is the closest reachable analogue to risk #1 (silent write failure):
  a rejected write must not silently corrupt or partially clear existing state.
- `test_pattern_paste_other_user_sees_404_and_writes_nothing` — using the `second_user` fixture from Phase 1,
  user B POSTs a pattern to user A's element; assert 404; assert zero `Row` rows exist for that element (the
  cross-user + write-path risks intersect here: an IDOR attempt must not have a write side effect either).

### Success Criteria

#### Automated Verification

- `uv run pytest tests/test_pattern_paste.py -v` passes, all seven tests green.
- `uv run pytest tests/ -v` passes in full.

#### Manual Verification

- None — pure test code, no user-facing behavior change.

---

## Testing Strategy

### Integration Tests

- All tests in this plan are integration tests (httpx `AsyncClient` against the real ASGI app, real Postgres
  test DB) — no new unit tests. `parse_pattern()` unit coverage is already complete in `tests/test_pattern.py`
  (test-plan §7 excludes re-testing it here).
- Multi-user tests use two independently authenticated sessions (`test_user` + `second_user`), not just two
  `User` DB rows, so the full authenticated-request path is exercised for both the owner and the attacker.

### Manual Testing Steps

None — this is test-only work with no application behavior change. If a real bug surfaces during
implementation (e.g., a write that isn't actually atomic), it will be documented separately rather than
silently patched, per the task's constraint.

## Performance Considerations

None — test-only change; no new indices, queries, or routes.

## Migration Notes

None — no schema changes.

## References

- Research: `context/changes/testing-write-path-ownership/research.md`
- Test-plan risk map: `context/foundation/test-plan.md` §2 (risks #1, #3, #6) and §6.2 (cookbook conventions)
- Route implementation: `app/routes/projects.py:23-40` (ownership helpers), `:178-252` (pattern-paste route)
- Feature plan: `context/changes/project-and-pattern-display/plan.md` (authoritative spec for the paste route)
- Existing test conventions: `tests/conftest.py`, `tests/test_project_routes.py`, `tests/test_auth_boundary.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Second-user fixture + cross-user element IDOR tests

#### Automated

- [x] 1.1 `uv run pytest tests/test_project_routes.py -v` passes, including 3 new cross-user IDOR tests — 682ce00
- [x] 1.2 `uv run pytest tests/ -v` passes in full (no regressions) — 682ce00

### Phase 2: Pattern-paste DB write correctness + all-or-nothing verification

#### Automated

- [x] 2.1 `uv run pytest tests/test_pattern_paste.py -v` passes, all 7 tests green
- [x] 2.2 `uv run pytest tests/ -v` passes in full
