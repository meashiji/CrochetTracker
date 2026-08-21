---
date: 2026-07-03T12:00:00+02:00
researcher: patrycja-gurdak
git_commit: 5353715
branch: main
repository: CrochetTracker
topic: "Write-path and ownership integration tests — R1, R3, R6 route grounding"
tags: [research, testing, ownership, idor, pattern-paste, row-mark, routes]
status: complete
last_updated: 2026-07-03
last_updated_by: patrycja-gurdak
---

# Research: Write-path and ownership integration tests (Phase 2)

**Date**: 2026-07-03
**Researcher**: patrycja-gurdak
**Git Commit**: 5353715
**Branch**: main
**Repository**: CrochetTracker

## Research Question

For Phase 2 of the test rollout (risks R1, R3, R6): what routes exist to test against, how does ownership
verification work, what does the row-mark endpoint do on failure, and what DB records does the pattern-paste
route create?

## Summary

**All three Phase 2 risks depend on routes that are not yet implemented.** The data models are fully in place,
and one analogous write endpoint exists (`POST /projects/new`), but the routes needed for R1 (row-mark), R3
(IDOR via project detail), and R6 (pattern paste) are in `project-and-pattern-display` Phases 2 and 3 — which
have not yet been started. The plan for `testing-write-path-ownership` must account for this sequencing
dependency.

### Route availability today

| Route | Status | Risk needs it |
|-------|--------|---------------|
| `POST /projects/new` | ✓ Implemented | (write-path pattern only — not a direct risk target) |
| `GET /projects/` | ✓ Implemented | (list — user-scoped; IDOR not testable via list) |
| `GET /projects/{project_id}` | ❌ Missing — in p&pd Phase 3 | R3 IDOR |
| `GET /projects/{project_id}/elements/{element_id}` | ❌ Missing — in p&pd Phase 2 | R3 (element IDOR), R6 (pattern paste GET) |
| `POST /projects/{project_id}/elements/{element_id}` | ❌ Missing — in p&pd Phase 2 | R6 (pattern paste write) |
| `POST …/rows/{row_id}/mark` (or equivalent) | ❌ Missing — not in any current plan | R1 (row-mark) |

`p&pd` = `context/changes/project-and-pattern-display/`

### Implication for the plan

- **R6 tests** can be written once `project-and-pattern-display` Phase 2 ships.
- **R3 tests** can be written once `project-and-pattern-display` Phase 3 ships.
- **R1 tests** must wait for a future change that adds the row-mark endpoint — no current plan covers it.
- The test plan Phase 2 (`testing-write-path-ownership`) should be **scoped to R3 + R6 only, and sequenced
  after the feature routes land**. R1 should be deferred to a future rollout phase.

---

## Detailed Findings

### R1 — Row-mark endpoint (does not exist)

No route exists for marking a row. The endpoint is risk-documented in the test plan but has no
corresponding implementation or implementation plan. It is not in `project-and-pattern-display`.

**Models in place** (`app/models/progress.py:8–27`, `app/models/pattern.py:5–12`,
`app/models/project.py:38–44`):

```
RowState (id, element_repetition_id, row_id, state: RowStateEnum, stitch_position, updated_at)
Row (id, element_id, position, content)
ElementRepetition (id, element_id, repetition_number)
```

`RowStateEnum` values: `not_started`, `in_progress`, `done`.

**HTMX pattern** — no templates with HTMX directives exist yet. When the route is eventually built,
test-plan §2 R1 guidance applies: the test must verify both the HTTP response fragment AND the DB state
after a POST, especially when the server returns a non-2xx status.

**Recommendation**: Defer R1 to a future rollout phase (Phase 4 or later, after the row-mark feature ships).

---

### R3 — Cross-user IDOR (route missing; ownership pattern established)

The only resource-scoped route today is `GET /projects/` at `app/routes/projects.py:18–28`. It already uses
the correct query-time ownership pattern:

```python
result = await session.execute(
    select(Project)
    .where(Project.user_id == user.id)         # ← ownership filter at query time
    .order_by(Project.updated_at.desc())
    .limit(500)
)
```

This is the **correct pattern**: ownership is enforced in the WHERE clause, not by fetching first and
comparing. The IDOR risk is untestable via the list endpoint (it simply omits cross-user records).

**The per-resource route `GET /projects/{project_id}` is in `project-and-pattern-display` Phase 3**
(`context/changes/project-and-pattern-display/plan.md:244–248`):

```python
# Spec from plan.md:
# Fetch Project; 404 if not found or ownership fails.
# WHERE Project.id == project_id AND Project.user_id == user.id  (single query, returns None → 404)
```

**Ownership chain** (FK structure):

```
User.id
  └─ Project.user_id (FK → user.id)
       └─ Element.project_id (FK → project.id)
            └─ Row.element_id (FK → element.id)
                  └─ RowState.row_id (FK → row.id)
                       └─ RowState.element_repetition_id (FK → element_repetition.id)
```

Element and Row have **no direct user_id** — ownership is verified by querying through the chain.
For element routes, the spec (`project-and-pattern-display` Phase 2) requires:
- Fetch Project by `project_id`, 404 if not found or `user_id != user.id`
- Fetch Element by `element_id`, 404 if not found or `project_id` doesn't match

**No shared ownership helper exists** — each route enforces it independently via the query WHERE clause.

**`get_current_user`** (`app/auth/dependencies.py:8–15`):
- Returns a `User` model with fields: `id`, `email`, `password_hash`
- Raises HTTP 401 if `user_id` in session maps to no DB row

**Multi-user test pattern** (once the routes exist): two independent `async_client` instances or two test
users with fresh clients. The conftest `test_user` fixture creates a user and stores the session cookie on
the shared `async_client`. For IDOR testing, user B needs a separate client with a separate session.

---

### R6 — Pattern paste DB write (route missing; spec is authoritative)

**`parse_pattern()`** (`app/services/pattern.py`):

```python
def parse_pattern(text: str) -> list[tuple[int, str]]:
    lines = [line.strip() for line in text.splitlines()]
    non_blank = [line for line in lines if line]
    return [(i + 1, content) for i, content in enumerate(non_blank)]
```

Returns `list[tuple[int, str]]` — 1-based position + stripped content, one tuple per non-blank line.
Empty list for blank/whitespace-only input.

**Paste route spec** (from `project-and-pattern-display/plan.md:180–196`):

`POST /projects/{project_id}/elements/{element_id}` — form field `pattern_text`

DB write sequence (single transaction, auto-committed by `get_session`):

```
If element already has rows:
  1. Bulk-delete RowState WHERE element_repetition_id IN (SELECT id FROM element_repetition WHERE element_id = ?)
  2. Bulk-delete Row WHERE element_id = ?
  3. Bulk-delete ElementRepetition WHERE element_id = ?

Always:
  4. UPDATE element.pattern_text = pattern_text.strip()
  5. INSERT Row × len(parse_pattern(pattern_text)) — one per (position, content)
  6. INSERT ElementRepetition × element.repeat_count — for S-01 always 1 (repetition_number=1)
  7. await session.flush()  ← forces PKs onto in-memory objects before RowState references them
  8. INSERT RowState × (len(rows) × repeat_count) — one per (element_repetition, row), state=not_started
  9. UPDATE project.updated_at = datetime.now(timezone.utc)

On empty parse result: re-render form with error; do not write to DB.
On success: 303 redirect to GET /projects/{project_id}/elements/{element_id}.
```

**Tables written, in order of insertion**:

| Table | Count | Key fields set |
|-------|-------|----------------|
| `element` | 1 (UPDATE) | `pattern_text` |
| `row` | N (one per non-blank line) | `element_id`, `position`, `content` |
| `element_repetition` | R (always 1 for S-01) | `element_id`, `repetition_number` |
| `row_state` | N×R (always N for S-01) | `element_repetition_id`, `row_id`, `state=not_started` |
| `project` | 1 (UPDATE) | `updated_at` |

**Key constraint**: `session.flush()` at step 7 is load-bearing. Without it, the RowState inserts cannot
reference the Row and ElementRepetition PKs (still `None` in SQLModel before flush). Tests that bypass the
route and try to construct this manually must also call `session.flush()` before adding RowStates.

**Integration test recipe** (once the route exists):

```python
async def test_pattern_paste_creates_db_records(test_user, async_client, db_session):
    from sqlalchemy import select
    from app.models.pattern import Row
    from app.models.project import Element, ElementRepetition
    from app.models.progress import RowState, RowStateEnum
    from app.services.pattern import parse_pattern

    pattern_text = "Row 1\nRow 2\nRow 3"

    # get the auto-created element for this user's project
    result = await db_session.execute(select(Element))
    element = result.scalar_one()
    project_id = element.project_id
    element_id = element.id

    response = await async_client.post(
        f"/projects/{project_id}/elements/{element_id}",
        data={"pattern_text": pattern_text},
        follow_redirects=False,
    )
    assert response.status_code == 303

    expected = parse_pattern(pattern_text)   # [(1,"Row 1"),(2,"Row 2"),(3,"Row 3")]

    rows = (await db_session.execute(
        select(Row).where(Row.element_id == element_id).order_by(Row.position)
    )).scalars().all()
    assert len(rows) == len(expected)
    for row, (pos, content) in zip(rows, expected):
        assert row.position == pos
        assert row.content == content

    reps = (await db_session.execute(
        select(ElementRepetition).where(ElementRepetition.element_id == element_id)
    )).scalars().all()
    assert len(reps) == 1
    assert reps[0].repetition_number == 1

    states = (await db_session.execute(select(RowState))).scalars().all()
    assert len(states) == len(rows)
    assert all(s.state == RowStateEnum.not_started for s in states)
```

---

### Write-path DB verify pattern — what's testable NOW

The `POST /projects/new` route (`app/routes/projects.py:36–58`) is implemented and creates two records
in one transaction: a `Project` and an auto-created `Element` (with `repeat_count=1`, `name=None`,
`pattern_text=None`). This is the only write endpoint currently available.

A test for this route would:
1. Use `test_user` fixture (authenticated via signup)
2. POST `/projects/new` with a project name
3. Assert 303 redirect
4. Query DB: verify `Project` exists with `user_id == user.id`, `name` matches input
5. Query DB: verify one `Element` exists with `project_id == project.id`, `repeat_count == 1`

This test establishes the §6.4 cookbook pattern (POST → DB verify) against an existing route, even though
it doesn't directly cover R1/R3/R6. It is a useful "warm-up" that proves the multi-table write infrastructure
works before the feature routes ship.

---

## Code References

- `app/routes/projects.py:18–28` — `GET /projects/` with user-scoped query (ownership pattern reference)
- `app/routes/projects.py:36–58` — `POST /projects/new` (only implemented write endpoint; creates Project + Element)
- `app/auth/dependencies.py:8–15` — `get_current_user()` returns `User`; raises 401 for orphaned user_id
- `app/auth/middleware.py:9–15` — `AuthRedirectMiddleware`; global ASGI, public paths: `/health`, `/auth/*`, `/static/*`
- `app/services/pattern.py` — `parse_pattern(text: str) -> list[tuple[int, str]]`
- `app/models/project.py:24–35` — `Element` (project_id FK, pattern_text, repeat_count)
- `app/models/project.py:38–44` — `ElementRepetition` (element_id FK, repetition_number)
- `app/models/pattern.py:5–12` — `Row` (element_id FK, position, content)
- `app/models/progress.py:8–27` — `RowState` (element_repetition_id FK, row_id FK, state, updated_at)
- `context/changes/project-and-pattern-display/plan.md:158–226` — Phase 2 spec (element detail + paste route)
- `context/changes/project-and-pattern-display/plan.md:230–258` — Phase 3 spec (project detail + IDOR surface)
- `tests/conftest.py` — `async_client`, `db_session`, `test_user` fixtures (reusable for Phase 2)

## Architecture Insights

**Ownership enforcement is at query time, not post-fetch.** The single implemented example (`GET /projects/`)
uses `.where(Project.user_id == user.id)` in the SELECT. The spec for the missing routes follows the same
pattern: a 404 is returned when the WHERE clause finds nothing, which covers both "doesn't exist" and
"belongs to someone else" in a single branch. There is no shared helper — each route author must apply the
filter manually.

**`session.flush()` is a required step** in the pattern paste write sequence. Between inserting Rows and
inserting RowStates, a flush is needed so that the ORM populates the auto-increment PKs on the in-memory Row
and ElementRepetition objects. Tests that need to construct this state manually (outside the route) must
replicate this.

**Session-scoped engine issue from Phase 1 applies here too.** The `_dispose_engines` autouse fixture in
conftest.py disposes asyncpg pools after each test. Multi-user tests (two test users, two clients) are safe
within a single test function since they share the same event loop — the pool disposal fires after the
function returns.

**No HTMX yet.** No templates use HTMX directives. The test plan §7 explicitly excludes template testing,
so tests should assert HTTP status codes and DB state, not rendered HTML content.

## Historical Context (from prior changes)

- `context/changes/testing-auth-boundary/plan.md` — Phase 1 reference: `base_url="https://testserver"`,
  `_dispose_engines` autouse fixture, session-scoped table creation via `asyncio.run()`. All fixtures are
  reusable for Phase 2 without modification.
- `context/changes/project-and-pattern-display/plan.md:158–226` — authoritative spec for the paste route
  (tables written, order, flush requirement, ownership checks). Research trusts this spec until the route
  is implemented and any deviations become apparent.

## Related Research

- `context/changes/testing-auth-boundary/research.md` — Phase 1 research (auth middleware, session, httpx
  `base_url` constraint)

## Open Questions

1. **Multi-user client pattern**: for R3 IDOR tests, user B needs its own session cookie. The current
   `test_user` fixture writes the session cookie onto the shared `async_client`. A second user can be
   created via a second `async_client` (from a fresh `AsyncClient` context manager within the test), or a
   separate `second_user` fixture with its own client. The plan should decide which pattern to canonicalize
   in §6.3.

2. **R1 deferred — no current owner**: The row-mark feature has no implementation plan. The test plan Phase
   2 originally included R1. Research recommends moving R1 out of this change's scope. If retained, R1
   tests cannot be written until the feature ships and would leave the change permanently `implementing`.

3. **project-and-pattern-display Phase 2 status**: confirmed NOT started (all Progress items unchecked in
   `context/changes/project-and-pattern-display/plan.md`). The `testing-write-path-ownership` plan should
   declare this as a prerequisite and specify what to implement first (or reference the existing p&pd plan).
