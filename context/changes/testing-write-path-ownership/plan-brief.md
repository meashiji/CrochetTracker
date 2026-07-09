# Write-Path and Ownership Integration Tests — Plan Brief

> Full plan: `context/changes/testing-write-path-ownership/plan.md`
> Research: `context/changes/testing-write-path-ownership/research.md`

## What & Why

Prove two of the three risks assigned to test-plan Phase 2: cross-user IDOR at the element/pattern-paste
level (risk #3) and pattern-paste DB write correctness (risk #6). The blocker that parked this change —
missing routes — is resolved: `project-and-pattern-display` shipped all 3 phases, so the routes exist and
can be tested against real code instead of a spec.

## Starting Point

`app/routes/projects.py` implements project/element CRUD and pattern-paste with query-time ownership checks
(`_get_project`, `_get_project_and_element`). `tests/test_project_routes.py` already covers project-level
IDOR and basic element-creation flows. No test yet exercises the element-detail or pattern-paste routes, no
test crosses ownership at the element level, and no test verifies the pattern-paste DB write against
`parse_pattern()`'s actual output.

## Desired End State

Two risks get automated proof: element-level IDOR (own-project mismatches too, not just cross-user) returns
404 with no side-effect writes, and pattern-paste writes exactly the Row/ElementRepetition/RowState records
`parse_pattern()` implies — on first paste, on re-paste (full replacement), and definitely-not on a rejected
paste (blank or oversized input leaves the DB untouched).

## Key Decisions Made

| Decision | Choice | Why | Source |
|----------|--------|-----|--------|
| Risk #1 (row-mark) scope | Deferred, out of scope | No row-mark route exists anywhere in `app/`; testing it would leave the change permanently `implementing` | Research |
| Risk #1 substitute | All-or-nothing write verification on the pattern-paste route | Closest reachable analogue to "silent write failure" without mocking infra | Plan |
| Multi-user pattern | New `second_user` fixture: independent `AsyncClient` + real signup session | A raw second `User` DB row (as the existing project-IDOR test does) proves DB-level ownership but not the full authenticated-attacker path needed for element/pattern-paste IDOR | Plan |
| Test file layout | Extend `tests/test_project_routes.py` for IDOR; new `tests/test_pattern_paste.py` for DB-write correctness | Matches existing one-file-per-concern convention (`test_auth_boundary.py`, `test_project_routes.py`) | Plan |
| Ownership edge case | Add a same-owner, mismatched project/element test | Exercises the second half of `_get_project_and_element` (project_id match), which the existing cross-user test doesn't reach | Plan |

## Scope

**In scope:**
- Element-level cross-user IDOR (GET + POST), including a same-owner/wrong-project 404 case.
- Pattern-paste DB write correctness: create, re-paste replacement, `project.updated_at` bump.
- Pattern-paste rejection paths (blank result, oversized input) proven to write nothing.
- Cross-user pattern-paste attempt proven to write nothing (IDOR × write-path intersection).

**Out of scope:**
- Risk #1 (row-mark) — no route exists.
- `repeat_count > 1` scenarios — S-01 always uses 1.
- Any change to `app/` — test-only work, unless implementation surfaces a real bug (documented separately).

## Architecture / Approach

Two phases: (1) add the `second_user` fixture and element-level IDOR tests, reusing the existing
`test_project_routes.py` file and conventions; (2) add a new `test_pattern_paste.py` covering the DB-write
correctness risk, reusing the Phase 1 fixture for the cross-user paste case.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|-------|-------------------|----------|
| 1. Second-user fixture + element IDOR | 3 new tests proving element-level IDOR, incl. wrong-project case | Fixture teardown ordering (FK constraints, no cascade) |
| 2. Pattern-paste DB write correctness | 7 new tests proving write correctness, replacement, and all-or-nothing rejection | Getting the exact Row/RowState count math right for re-paste |

**Prerequisites:** `project-and-pattern-display` fully shipped (confirmed — all 3 phases `[x]`); test DB
`crochet_tracker_test_writepath` reachable at 127.0.0.1:5433.
**Estimated effort:** Single session, ~10 new tests total across 2 phases.

## Open Risks & Assumptions

- Assumes no cascade delete exists on any FK in the chain Project→Element→Row/ElementRepetition→RowState —
  confirmed from `project-and-pattern-display/plan.md`'s "Re-parse deletion order" note; test teardowns must
  delete children before parents, same as the existing `test_project_routes.py` teardowns.
- Assumes the shared test infrastructure (`_dispose_engines`, session-scoped `CREATE ALL`/`DROP ALL`) needs
  no changes — Phase 1 of the rollout already validated it works.

## Success Criteria (Summary)

- `uv run pytest tests/ -v` passes with all new tests green, run against `crochet_tracker_test_writepath`.
- Risks #3 and #6 in `context/foundation/test-plan.md` §2 have a corresponding automated test each.
- §6.3 and §6.4 cookbook entries in `test-plan.md` are filled in with the reference test and pattern used.
