# Sequential Row & Repeat Progress Implementation Plan

## Overview

Enforce crochet ordering on row/repeat state: a row may only advance toward `done`
when the previous row in the same repetition is `done`, and a repetition's rows may
only advance when the previous repetition is fully `done`. Reverts (`done →
not_started`) stay always allowed; no cascade on revert. Blocked states are shown in
the UI, and opening an element auto-navigates to the first not-fully-done repetition.

## Current State Analysis

- `RowState` rows are stored per `(element_repetition_id, row_id)` with a `state`
  enum `not_started / in_progress / done` (`app/models/progress.py:8`, `:14`).
- Rows belong to an element with a 1-based `position` (`app/models/pattern.py:5`)
  and are fetched ordered by `position` asc (`app/routes/projects.py:513`).
- `ElementRepetition` has a `repetition_number` (1-based) unique per element
  (`app/models/project.py:38`); reps are seeded independently by the repeat-count
  stepper.
- The row toggle endpoint `row_state_toggle` (`app/routes/projects.py:896`) blindly
  applies `ROW_STATE_CYCLE` (`:23`): `not_started→in_progress→done→not_started`,
  with no predecessor or prior-rep check.
- `_render_element_detail` (`:500`) already computes `current_row_id` via
  `_first_unmarked_row_id` (`:197`) — the first non-`done` row — and passes
  `row_progress` (per-rep `RowState` dict) and `rep_numbers` to the template.
- `_row.html` renders each row as a toggle `<button class="row-toggle">` that posts
  to the state URL and cycles; there is no disabled/locked variant.
- `element_detail.html` renders a `rep-pills` nav (one `<a class="rep-pill">` per
  rep, active highlighted) and the `row-list`.
- Existing tests in `tests/test_row_state_routes.py` assume any row in any rep can
  be toggled freely (e.g. `test_per_rep_toggle_isolation:463`) and must be updated.
- Baseline: `uv run pytest -q` → 75 passed.

## Desired End State

- A row in a repetition can be advanced (`not_started→in_progress` or
  `in_progress→done`) only when the previous row in the same repetition is `done`,
  and (for rep N>1) only when every row of rep N-1 is `done`. Revert
  (`done→not_started`) is always allowed.
- Blocked rows render with a dimmed, inactive toggle (when the row's next cycle
  transition would be a blocked advance). Revertable `done` rows are not blocked.
- Rep pills show a lock affordance when rep N>1 requires rep N-1 fully `done`;
  clicking a locked pill still opens the (read-only, rows locked) view.
- Opening an element auto-navigates to the first rep not fully `done` (when that
  differs from the last-viewed rep).
- No cascade: reverting a middle row leaves later rows' states untouched.

### Key Discoveries:

- The advance gate is pure server logic — no data model / migration change. The
  cost is two extra queries (predecessor `RowState`, prior-rep completion).
- The "locked" condition for rendering is precisely: the row's current state's
  next transition is an advance **and** that advance is gated. `done` rows are
  never locked (their next transition is a revert).
- `_first_unmarked_row_id` already targets the first non-`done` row; within a rep
  the only advanceable row under the new rule is exactly that row, so the existing
  auto-scroll stays correct.
- An element with no pasted rows has no reps/states; with zero rows every rep is
  trivially "done" and nothing is blocked.

## What We're NOT Doing

- No data-model or schema change; no migration. Ordering is enforced in logic.
- No cascade/un-revert propagation to later rows when a middle row is reverted.
- No blocking of *viewing* reps or rows — navigation stays free; only writes are
  gated.
- No change to the `stitch_position` feature (still only on `in_progress` rows).
- No change to `ROW_STATE_CYCLE` semantics per-se; the gate intercepts advances
  only.
- No change to the repeat-count stepper (still freely adjusts rep count).

## Implementation Approach

Three sequential phases, each independently testable:

1. **Gate logic (server)** — add a rep-completeness helper and gate the advance
   transitions in `row_state_toggle`. Server rejects blocked advances (unchanged
   state) even before UI disables buttons.
2. **UI row lock** — compute per-row locked flags in the render and pass them to
   the template; `_row.html` renders blocked rows dimmed/inactive; add CSS.
3. **Rep lock + auto-jump** — lock affordance on rep pills (when prior rep not
   done) + auto-navigate to first not-fully-done rep on element open; add CSS.

## Critical Implementation Details

- **Revert stays free and a `done` row is never "locked".** The render must NOT
  dim a `done` row even when its predecessor isn't done — that row's only next
  transition is `done→not_started` (a revert). Only rows whose next transition is a
  blocked advance are dimmed/inactive. Locking per row = `state != done AND
  (predecessor-not-done OR prior-rep-incomplete)`.
- **Both gates apply to advances in rep N>1**: within-rep predecessor `done` AND
  rep N-1 fully `done`. Rep 1 rows only need the within-rep predecessor check.
- **Server-side enforcement stays** even though the UI disables buttons — the
  toggle is the security/authz boundary; the disabled rendering is UX only.

---

## Phase 1: Gate Logic (server)

### Overview

Add a helper to determine a repetition's completeness (every row `done`) and gate
the advance transitions in `row_state_toggle`: block `not_started→in_progress` and
`in_progress→done` when the previous row in the same rep isn't `done` or (rep N>1)
when rep N-1 isn't fully `done`. Revert `done→not_started` always proceeds. A
blocked advance leaves state unchanged and returns an unchanged fragment (or a
no-op) rather than an error that suggests a broken flow.

### Changes Required:

#### 1. Rep-completeness helper

**File**: `app/routes/projects.py`

**Intent**: Add a small async helper that, given an element, a repetition number,
and the session, returns whether that repetition is fully `done` (every `Row` of
the element has a `RowState` for that rep whose `state == done`; true if the
element has no rows). Also add a helper building the current row's gating context
for a given rep: the `done` status of `position-1` (or None for position 1) and the
`done` status of rep N-1 (or None/True for rep 1).

**Contract**: New helpers next to the existing `_build_row_progress` /
`_first_unmarked_row_id` helpers. Reference the `repetition` and its
`repetition_number` for gating. Return booleans (`True`/`False`), treating an
element with no rows as complete.

#### 2. Gate the advance in `row_state_toggle`

**File**: `app/routes/projects.py` (`row_state_toggle`, ~:896)

**Intent**: Before applying `ROW_STATE_CYCLE`, compute `next_state`. If
`next_state` is `in_progress` or `done` (an advance) and the gate says the advance
is blocked, return the current fragment with state unchanged (no DB write, no
`updated_at` bump). If `next_state` is `not_started` (a revert), always proceed.

**Contract**: The gate requires (a) the previous row (if any) in the same rep is
`done`, and (b) for rep 1 `True`, else rep N-1 is fully `done`. Blocked advance →
no state change and no `project.updated_at` bump. Behavior is enforced
server-side regardless of UI.

#### 3. Update tests for the gate

**Files**: `tests/test_row_state_routes.py`

**Intent**: Keep existing coverage but reflect the sequential contract. Tests that
toggle rows 2+ before row 1 must first mark earlier rows `done`, or be updated to
assert the gate. Add new tests: advancing row N blocked while N-1 not done; revert
of a `done` row always allowed even when predecessor isn't done; rep 2 advance
blocked while rep 1 not fully done; rep 2 advance allowed when rep 1 done.

**Contract**: `uv run pytest -q` continues to pass. All prior behavior tests that
are still valid (authz 404s, persistence, stitch position, stepper) remain green.

### Success Criteria:

#### Automated Verification:

- `uv run pytest -q` passes (full suite).
- New tests assert: row N advance blocked when N-1 not done (`not_started` stays);
  row N advance allowed when N-1 done; `done→not_started` revert allowed even with
  non-done predecessor; rep 2 advance blocked while rep 1 incomplete; rep 2 advance
  allowed once rep 1 fully done; blocked advance does not bump `project.updated_at`.

#### Manual Verification:

- Via API/UI: with 3 rows, marking row 2/3 done without row 1 results in unchanged
  state.

**Implementation Note**: After all automated verification passes, pause for manual
confirmation before Phase 2.

---

## Phase 2: UI Row Lock

### Overview

Make blocked rows visually distinct: dimmed + inactive toggle. Compute each row's
locked flag during render and pass it to `_row.html` so the button is rendered
disabled when its next transition is a blocked advance.

### Changes Required:

#### 1. Compute and pass per-row locked flags

**File**: `app/routes/projects.py` (`_render_element_detail`, ~:500)

**Intent**: Build a set (or dict) of row ids whose current state's next transition
is a blocked advance, and pass it into the template context as part of the
per-row rendering data (e.g. a lookup, so `_row.html` can branch without extra DB
work).

**Contract**: For the rendering rep, for each `row` in `rows`: `locked` is true iff
`state != done` AND (prev row in this rep not `done` OR rep N-1 not fully `done`).
Expose it in context keyed by `row_id`. The full-page render and the
`row_state_toggle` fragment render must compute it the same way.

#### 2. Render locked rows in `_row.html`

**File**: `app/templates/projects/_row.html`

**Intent**: When the current row is locked, render the toggle button with a
`disabled` attribute and a `row-item--locked` class (dimmed). Keep the same DOM
shape/label so CSS and any tests targeting structure stay stable.

**Contract**: Locked rows expose no clickable state change: `disabled` on the
button, class `row-item--locked`. The `aria-label` should reflect that the row is
locked pending previous work (e.g. "Row N locked — finish previous row first") so
screen readers aren't silent.

#### 3. Add locked CSS state

**File**: `app/static/styles.css` (`.row-item` block, ~:602)

**Intent**: Add a dimmed visual for `.row-item--locked .row-toggle` (reduced
opacity, muted color, `cursor: not-allowed`) consistent with the token-based
palette. Reuse the existing disabled styling pattern (`:disabled` at ~:993).

**Contract**: Locked rows are visually distinct from active/current rows.
No change to active/current/in-progress/done styling.

### Success Criteria:

#### Automated Verification:

- `uv run pytest -q` passes.
- A test asserts the locked fragment renders `disabled` (and `row-item--locked`)
  for a row whose advance is blocked, and does not render `disabled` for a
  revertable `done` row or an advanceable row.

#### Manual Verification:

- In the app: with row 1 not done, rows 2+ appear dimmed and do not respond to
  clicks; row 1 stays active. With row 1 done, row 2 becomes active. A `done` row
  stays clickable (revertable) even when its predecessor is not done.

**Implementation Note**: After all automated verification passes, pause for manual
confirmation before Phase 3.

---

## Phase 3: Rep Lock + Auto-Jump

### Overview

Add a lock affordance to rep pills for reps gated by an incomplete prior rep, and
auto-navigate the element page to the first rep that isn't fully done on open.

### Changes Required:

#### 1. Rep-pill lock affordance

**File**: `app/templates/projects/element_detail.html` (`rep-pills`, ~:84)

**Intent**: For each rep N>1 whose rep N-1 isn't fully `done`, render the pill with
a lock class/icon. Keep the pill a working link (view-only). Requires the render to
expose per-rep "locked/complete" info.

**Contract**: The render (`_render_element_detail`) computes and passes, for each
rep number, whether it is fully `done` (so the template can decide `rep-pill--locked`
and show a lock glyph). Locked pills remain clickable; their rows are shown locked
via Phase 2.

#### 2. Add locked-pill CSS

**File**: `app/static/styles.css` (`.rep-pill` block, ~:794)

**Intent**: Add a muted/lock style for `rep-pill--locked` consistent with the row
lock, while keeping the pill clickable.

**Contract**: Locked pills are visually distinct; active/locked can coexist (the
currently-viewed locked rep shows active + lock).

#### 3. Auto-navigate to first incomplete rep

**File**: `app/routes/projects.py` (`_render_element_detail` / element GET ~:560)

**Intent**: When rendering the element page (non-explicit, no `?rep=`), if the
last-viewed rep is fully `done` and a later rep is not fully `done`, redirect (or
render / re-pin the cookie) to the first not-fully-done rep instead. Keep explicit
`?rep=` and last-viewed behavior otherwise.

**Contract**: "Fully done" = every row of that rep is `done` (or no rows). For a
full GET without `?rep=`: if rep 1 fully done and rep 2+ has an incomplete rep,
show the first incomplete rep (and pin it). Explicit `?rep=N` is never overridden.
A bare GET on an element where all reps done stays on the last viewed rep. Treat an
element with no rows as all-done (no change).

### Success Criteria:

#### Automated Verification:

- `uv run pytest -q` passes.
- Tests assert: a locked rep pill renders the lock class while staying a link; a
  bare GET on an element with rep 1 done redirects/re-pins to rep 2; an explicit
  `?rep=1` is not overridden; all-done element stays on last-viewed rep.

#### Manual Verification:

- In the app: with rep 1 fully done and rep 2 not, opening the element lands on rep
  2; rep 1 shows complete; a locked rep 2 (when rep 1 incomplete) shows the pill
  lock and dimmed rows but still opens for viewing.

---

## Testing Strategy

### Unit Tests:

- Gate logic: predecessor-done and prior-rep-done checks, revert always allowed,
  rep-1 no rep-gate, no-rows elements never blocked.
- Lock flag computation: `done` rows never locked; `not_started`/`in_progress`
  locked when predecessor or prior rep incomplete; rep 1 locked only by
  predecessor.

### Integration Tests:

- Toggle endpoint respects gates (blocked advance unchanged, revert advances).
- Full-page GET renders locked rows/pills; fragment re-render keeps locked state.
- Auto-jump to first incomplete rep (bare GET), overridden by explicit `?rep=`.

### Manual Testing Steps:

1. Mark only row 1 done; confirm rows 2+ dimmed and unclickable; row 1 active.
2. Revert row 1 (now no rows done); confirm all rows not_started, none locked.
3. Mark rows 1-2 done; confirm row 3 active; mark row 1 done→not_started (revert);
   confirm rows 2-3 keep done but are revertable, and row 1 is active again.
4. With repeat_count 2: complete rep 1 → rep 2 unlocks; with rep 1 incomplete, rep
   2 shows pill lock and dimmed rows but opens for viewing.
5. Bare-open element with rep 1 done → lands on rep 2; `?rep=1` still shows rep 1.

## Performance Considerations

- The gate adds at most two small indexed reads per toggle (predecessor `RowState`
  by `(rep, row)`, prior-rep completeness by `(rep)` scalar count). Rendering
  computes lock flags once per page render from already-fetched `row_progress`.
- No new indexes required (existing unique constraints on `(rep, row)` and
  `element_id` cover the lookups).

## Migration Notes

None — no schema change. Existing data (possible orphaned `done` rows) is accepted
as-is; the no-cascade rule is explicit. No backfill needed.

## References

- Frame brief: `context/changes/sequential-progress/frame.md`
- Source: `app/routes/projects.py` (`ROW_STATE_CYCLE:23`, `_build_row_progress:170`,
  `_first_unmarked_row_id:197`, `_render_element_detail:500`, `row_state_toggle:896`)
- Models: `app/models/progress.py`, `app/models/pattern.py`, `app/models/project.py`
- Templates: `app/templates/projects/_row.html`, `app/templates/projects/element_detail.html`
- Tests: `tests/test_row_state_routes.py`

---

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Gate Logic (server)

#### Automated

- [x] 1.1 Add rep-completeness + gating helpers in `app/routes/projects.py` — a3ccb56
- [x] 1.2 Gate advance transitions in `row_state_toggle`; revert always allowed; no `updated_at` bump on blocked — a3ccb56
- [x] 1.3 Update/extend tests for sequential gate; full suite passes — a3ccb56

#### Manual

- [x] 1.4 Blocked advance leaves state unchanged (manual/API check) — a3ccb56

### Phase 2: UI Row Lock

#### Automated

- [x] 2.1 Compute and pass per-row locked flags in render — 8fc7c0a
- [x] 2.2 Render locked rows disabled with `row-item--locked` in `_row.html` — 8fc7c0a
- [x] 2.3 Add `.row-item--locked` CSS — 8fc7c0a
- [x] 2.4 Swap the next row out-of-band on toggle so lock/unlock updates without reload — 8fc7c0a
- [x] 2.5 Test locked rendering (disabled class), revertable-done rendering, OOB unlock/lock; full suite passes (88) — 8fc7c0a

#### Manual

- [x] 2.6 Marking a row done unlocks the next row dynamically (no reload); reverting re-locks — 8fc7c0a

### Phase 3: Rep Lock + Auto-Jump

#### Automated

- [x] 3.1 Expose per-rep completeness for the pill lock; render `rep-pill--locked` lock glyph — ee64823
- [x] 3.2 Add `.rep-pill--locked` CSS — ee64823
- [x] 3.3 Auto-navigate (full GET, no `?rep=`) to first not-fully-done rep; explicit `?rep=` not overridden — ee64823
- [x] 3.4 Tests for rep pill lock + auto-jump; full suite passes (92) — ee64823

#### Manual

- [x] 3.5 Rep pill lock + auto-land on first incomplete rep (manual check) — ee64823
