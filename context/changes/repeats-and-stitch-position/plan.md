# Repeats + stitch position (S-03) Implementation Plan

## Overview

Ships the last two must-have tracking FRs on top of S-02's working row-toggle machinery: FR-003 (user sets a repeat count on an element; each repetition is tracked independently) and FR-010 (user records the stitch position they stopped at within an in-progress row). No schema migration — F-01 deliberately over-built `Element.repeat_count`, `ElementRepetition`, and `RowState.stitch_position` for exactly this slice.

## Current State Analysis

- Every `Element` is created with `repeat_count=1` hard-coded (`app/routes/projects.py:327,442`); no route or form can change it, so exactly one `ElementRepetition` exists per element today.
- Single-repetition assumptions are baked into S-02 code: `_get_element_repetition` (`app/routes/projects.py:109-128`) uses `.scalar_one()` and **raises** the moment 2+ repetitions exist; the toggle route (`projects.py:674-714`) and `_row.html`'s `hx-post` URL carry no repetition identity; `_build_row_states` (`projects.py:131-152`) and `_first_unmarked_row_id` (`projects.py:155-162`) are repetition-blind.
- `element_save_pattern` (`projects.py:593-671`) already deletes all `ElementRepetition`s and re-seeds `RowState`s for `range(1, element.repeat_count + 1)` on every save (`projects.py:644-659`) — the seeding side of FR-003 is done; only `repeat_count` can never differ from 1 when it runs.
- Invariant this plan relies on and preserves: **whenever an element has rows, its `ElementRepetition` rows exactly match `repeat_count`** (numbered 1..N). Before the first pattern save there are no rows and no repetitions.
- `RowState.stitch_position` (`app/models/progress.py:22`) exists but is read/written by nothing. The unique constraint on `(element_repetition_id, row_id)` (`progress.py:16`) already supports per-repetition state.
- `_render_element_detail` (`projects.py:456-485`) is the single render path for the element page (GET + every error re-render) — one place to add repetition context.
- `project_detail`'s state-count aggregation (`projects.py:358-366`) already joins through all `ElementRepetition`s, so it silently sums across reps — the desired semantics, left untouched.
- Template/test conventions are established: HTMX fragment swap for the toggle with `hx-on::responseError` error styling (`app/templates/projects/_row.html`), commit-before-return on every mutating route, destructive-action JS `confirm()` precedent (`element_detail.html:266`), and the test fixture/assertion shape in `tests/test_row_state_routes.py`.

## Desired End State

A signed-in user opens an element, sets its repeat count to ×3 via an inline −/+ stepper next to the title, and sees "Rep 1 | Rep 2 | Rep 3" pills above the row list. Each repetition has fully independent row states: marking a row done in Rep 1 leaves it untouched in Rep 2. Switching reps is a full-page navigation (`?rep=N`); reopening the element later lands on the last-viewed rep (per-device cookie), scrolled to that rep's first non-done row. Decreasing the count asks for confirmation, then deletes the highest-numbered reps and their progress. On any in-progress row an inline stitch input appears; entering "14" saves immediately (HTMX fragment swap, no reload) and survives reloads and state cycles — it is displayed only while the row is in-progress.

**Verification**: set ×2, mark rows in both reps, reload and switch reps to confirm independence; enter a stitch position, reload, confirm it's still there; decrease the count and confirm the top rep's progress is gone after the confirm dialog. Automated tests cover seeding/deletion on count change, per-rep isolation, rep resolution (query/cookie/404), stitch set/clear/invalid, and stitch persistence across state cycles.

### Key Discoveries:

- `app/routes/projects.py:109-128` — `_get_element_repetition().scalar_one()` is the single point that breaks with N reps; replaced by a by-number lookup.
- `app/routes/projects.py:644-659` — pattern save already seeds `RowState`s for `range(1, repeat_count+1)`; with the stepper in place this "just works" for N reps.
- `app/routes/projects.py:456-485` — `_render_element_detail` is the one render path all element-page routes share; repetition context is added exactly once here.
- `app/models/progress.py:16,22` — unique `(element_repetition_id, row_id)` + `stitch_position` column: per-rep state and stitch recording need **no migration**.
- `app/templates/projects/element_detail.html:266` — existing `confirm()` precedent for destructive actions; the repeat-count decrease reuses this pattern.
- `tests/test_row_state_routes.py:9-71` — `project_element_rows` fixture + `_row_state` fresh-query helper are the shape new tests mirror; the `populate_existing=True` discipline (comment at lines 60-64) applies to any new fresh-query assertions.

## What We're NOT Doing

- No schema migration of any kind (F-01 already provisioned every column/constraint this slice needs).
- No cross-device sync of the last-viewed repetition — it's per-device view state held in a cookie, not project data (PRD's cross-device requirement covers row marks, which are already server-side).
- No per-repetition breakdown on the project detail page — the existing aggregate counts already sum across reps, which is the desired semantics.
- No `repeat_count` field on the element-create form — elements still start at ×1; the count is adjusted on the element detail page.
- No stitch-position display for non-in-progress rows — the value is kept in the DB across state cycles (user decision) but only surfaced while the row is `in_progress`.
- No HTMX for rep switching or the stepper — pills are plain links and the stepper is a plain form POST + 303; only row toggle and stitch save stay on the 100ms-critical fragment path.
- No guard preventing stitch input on non-in-progress rows at the route level — the UI only renders the input on in-progress rows; the route accepts and stores whatever valid value is posted (UI-constrained, not policy-enforced).
- No live re-jump within an already-open page (unchanged from S-02); no debouncing of rapid stepper clicks; no CSRF protection (matches existing convention).
- No changes to pattern re-save behavior — it already resets all reps' progress, with its existing confirm dialog.

## Implementation Approach

Two phases, each independently shippable and manually verifiable:

1. **Phase 1** ships FR-003 end-to-end: repeat-count stepper route, rep-scoped helpers and toggle route (`/reps/{rep_number}/` in the path), rep pills with `?rep=N` + last-viewed cookie, and per-rep auto-jump. S-02's tests are updated to the rep-scoped URLs — expected rework, not regression.
2. **Phase 2** ships FR-010 purely additively: a stitch route returning the same row fragment, an inline input rendered by `_row.html` for in-progress rows, and a widening of `_build_row_states` to carry the full `RowState` (state + stitch_position) to the template.

## Critical Implementation Details

**Timing & lifecycle**: All three new/changed mutating routes (stepper, rep-scoped toggle, stitch) keep the established commit-before-return discipline (`projects.py:243,449,552,588,667,701`) — the stitch and toggle routes return fragments, and the stepper returns a 303 whose follow-up GET must see the new rep structure.

**State sequencing**: The stepper route's increase path must `await session.flush()` after adding new `ElementRepetition`s before inserting their `RowState`s (PKs are needed — same pattern as `element_save_pattern:651`). The decrease path deletes `RowState`s before `ElementRepetition`s (FK-safe order, same as `element_delete:572-583`).

**Rep resolution has two distinct failure modes**: an explicit `?rep=N` that's non-integer, <1, or >`repeat_count` is a bad URL → 404 (app convention). A stale `last_rep_*` cookie (e.g., after a decrease) is app-written state going out of date → silently clamp to `[1, repeat_count]`. Do not unify these.

**Cookie write point**: the `last_rep_{element_id}` cookie is set only when the rep came from an explicit `?rep=N` (i.e., a pill click), on the `TemplateResponse` returned by `_render_element_detail` — never on the bare-GET path (which only reads). This keeps "open the element" from re-pinning a rep the user didn't choose this visit.

## Phase 1: Repeat count + per-repetition tracking

### Overview

Adds the repeat-count stepper (route + inline UI), re-scopes every row-state code path from "the element's one rep" to "rep number N", and adds pill navigation with a last-viewed-rep cookie. Ships FR-003.

### Changes Required:

#### 1. Rep-by-number lookup helper

**File**: `app/routes/projects.py`

**Intent**: Replace the single-rep `_get_element_repetition` (which `.scalar_one()`-raises with N reps) with a lookup by `(element_id, repetition_number)` that 404s on miss — the same ownership-helper style as `_get_project_element_and_row`.

**Contract**: `async def _get_element_repetition_by_number(element_id: int, repetition_number: int, session: AsyncSession) -> ElementRepetition` — `select(ElementRepetition).where(ElementRepetition.element_id == element_id, ElementRepetition.repetition_number == repetition_number)`; `.scalar_one_or_none()`; raise `HTTPException(404)` if `None`. `_get_element_repetition` is deleted; its two call sites (toggle route, `_build_row_states`) are reworked per items 3 and 5.

#### 2. Requested-rep resolution helper

**File**: `app/routes/projects.py`

**Intent**: One pure function deciding which rep number a given element-page request shows — explicit query param wins, then the last-viewed cookie, then 1 — encoding the two distinct failure modes from Critical Implementation Details.

**Contract**: `def _resolve_requested_rep(request: Request, element: Element) -> tuple[int, bool]` returning `(rep_number, is_explicit)`. Reads `request.query_params.get("rep")`: if present, parse as int; non-integer, `<1`, or `> element.repeat_count` → raise `HTTPException(404)`; return `(n, True)`. Otherwise read `request.cookies.get(f"last_rep_{element.id}")`, parse int, clamp into `[1, element.repeat_count]` (unparseable → 1); return `(n, False)`. No DB access.

#### 3. `_build_row_states` re-scoped to a repetition

**File**: `app/routes/projects.py`

**Intent**: Row states are per-repetition; the helper takes the already-resolved repetition instead of re-deriving "the" rep from the element.

**Contract**: `async def _build_row_states(repetition_id: int, rows: list[Row], session: AsyncSession) -> dict[int, RowStateEnum]` — keep the empty-rows short-circuit returning `{}` (no rep fetch implied by the signature change); query `RowState` filtered by `element_repetition_id == repetition_id`. `_first_unmarked_row_id` is unchanged (operates on the displayed rep's `rows` + `row_states`).

#### 4. `_render_element_detail` rep-aware

**File**: `app/routes/projects.py`

**Intent**: The single render path resolves the requested rep, scopes `row_states`/`current_row_id` to it, passes pill/stepper context, and sets the last-viewed cookie on explicit rep selection.

**Contract**: After fetching `rows`: if `rows` is empty, behave exactly as today (no rep resolution, no pills — context gets `rep_number=1` and no cookie write). Otherwise call `_resolve_requested_rep(request, element)`, fetch the repetition via `_get_element_repetition_by_number` (404 propagates), and build `row_states` from `repetition.id`. New context keys: `rep_number` (int) and `rep_numbers` (`range(1, element.repeat_count + 1)`) for the pills. If `is_explicit` is true, call `response.set_cookie(f"last_rep_{element.id}", str(rep_number), max_age=31_536_000)` on the `TemplateResponse` before returning (assign the response to a variable first). All existing error re-render callers (`element_save_pattern`'s `_rerender_with_error`, `element_rename`) flow through here unchanged.

#### 5. Toggle route rep-scoped

**File**: `app/routes/projects.py`

**Intent**: The row-state toggle targets a specific repetition so per-rep progress is independent; the fragment response carries the rep so the swapped-in row's next `hx-post` keeps it.

**Contract**: Route becomes `@router.post("/{project_id}/elements/{element_id}/reps/{rep_number}/rows/{row_id}/state")`. Ownership via existing `_get_project_element_and_row`; repetition via `_get_element_repetition_by_number(element.id, rep_number, session)`; `RowState` fetch, cycle, `project.updated_at` bump, and explicit commit unchanged. Fragment context gains `rep_number`; `current_row_id` stays `None` in fragments (S-02 decision unchanged).

#### 6. Repeat-count stepper route

**File**: `app/routes/projects.py`

**Intent**: The mutating route behind the −/+ stepper; keeps the reps-match-`repeat_count` invariant for elements with rows, and is a plain field update for elements without.

**Contract**: `@router.post("/{project_id}/elements/{element_id}/repeat-count")` with `repeat_count: int = Form(...)`. If `repeat_count < 1` or `> 99` → re-render via `_render_element_detail(..., repeat_error="Repeat count must be between 1 and 99.")` (200). Load the element's rows (same query as `_render_element_detail`) and existing `ElementRepetition`s. Increase: add `ElementRepetition`s numbered `old+1..new`; if rows exist, `await session.flush()` then seed `RowState(state=not_started)` for every `(new rep, row)` pair. Decrease: for every existing rep with `repetition_number > new`, delete its `RowState`s then the rep (FK-safe order). No-rows element: skip all rep work, just set the field. Set `element.repeat_count`, bump `project.updated_at`, `await session.commit()`, return `RedirectResponse(url=f"/projects/{project_id}/elements/{element_id}", status_code=303)` — bare URL, no `?rep=`, so a stale current-rep cookie is clamped on the next read rather than 404ing the user out of their own page.

#### 7. `_row.html` carries the rep

**File**: `app/templates/projects/_row.html`

**Intent**: The toggle URL embeds the rep number so fragment swaps act on (and re-render) the correct repetition.

**Contract**: `hx-post` becomes `/projects/{{ project.id }}/elements/{{ element.id }}/reps/{{ rep_number }}/rows/{{ row.id }}/state`. `rep_number` becomes required context on every render path (full page and fragment).

#### 8. Element detail template: stepper + pills

**File**: `app/templates/projects/element_detail.html`

**Intent**: Inline −/+ stepper in the `.element-title-row` (alongside the rename pencil interaction), pill navigation above the row list when `repeat_count > 1`, and a `repeat_error` banner line matching the existing `rename_error`/`error` pattern.

**Contract**: Stepper: two small sibling `<form method="post" action=".../repeat-count">` each with a hidden `repeat_count` input (`element.repeat_count - 1` / `+ 1`) and a submit button (`−` / `+`), with `×{{ element.repeat_count }}` text between; the − form is omitted when `repeat_count <= 1`, the + form omitted when `>= 99`; the − form gets `onsubmit="return confirm('...')"` only when `has_rows` (no rows → no progress to lose → no confirm). Pills: when `element.repeat_count > 1`, a `<nav class="rep-pills">` above `.row-list` with `<a href="?rep={{ n }}" class="rep-pill{{ ' rep-pill--active' if n == rep_number }}">Rep {{ n }}</a>` for `n` in `rep_numbers`. CSS for `.rep-pills`/`.rep-pill`/`.rep-pill--active`/stepper goes in the page's existing local `<style>` block. The `{% block scripts %}` auto-jump is untouched — `current_row_id` is already rep-scoped by item 4.

### Success Criteria:

#### Automated Verification:

- Updated + new tests pass: `uv run pytest tests/test_row_state_routes.py -v` (existing tests updated to `/reps/1/` URLs; new: stepper increase seeds reps+states, stepper decrease deletes top rep's states, stepper validation error, per-rep toggle isolation, `?rep=2` rendering, `?rep=99` → 404, cookie set on explicit rep + read on bare GET, per-rep auto-jump)
- Full suite still passes: `uv run pytest`

#### Manual Verification:

- Set an element to ×3: "Rep 1 | Rep 2 | Rep 3" pills appear; each rep shows all rows at not-started.
- Mark rows in Rep 1 and Rep 2 differently, switch between pills — each rep keeps its own states; reload mid-way confirms persistence per rep.
- Open the element's bare URL after clicking Rep 2 — the page shows Rep 2 (last-viewed), scrolled to its first non-done row.
- Decrease ×3 → ×2: confirm dialog appears; after confirming, Rep 3 pill is gone and its progress is deleted.
- Element with no pattern saved: stepper still changes the count, no pills, "No pattern pasted yet" unchanged.

---

## Phase 2: Stitch position recording

### Overview

Adds FR-010: an inline stitch-number input on in-progress rows, saved via HTMX fragment swap, kept across state cycles (user decision: value persists; only its display is limited to in-progress rows).

### Changes Required:

#### 1. `_build_row_states` widened to full row progress

**File**: `app/routes/projects.py`

**Intent**: The template needs `stitch_position` alongside `state`; widen the helper's return rather than adding a second query.

**Contract**: Rename to `_build_row_progress(repetition_id, rows, session) -> dict[int, RowState]` — same query, but the dict maps `row_id` to the whole `RowState` object instead of `.state`. `_first_unmarked_row_id` updates to compare `row_progress.get(row.id).state != RowStateEnum.done` (guard a possible `None` defensively, as today). `_render_element_detail` passes the dict as `row_progress` (template context key renamed accordingly); the toggle route's fragment context passes the single `{row.id: row_state}` entry under the same key.

#### 2. Stitch route

**File**: `app/routes/projects.py`

**Intent**: Persist `stitch_position` for one row's `RowState` (blank clears), returning the updated row fragment; invalid input re-renders the row with the existing error treatment and writes nothing.

**Contract**: `@router.post("/{project_id}/elements/{element_id}/reps/{rep_number}/rows/{row_id}/stitch")` with `stitch_position: str = Form(default="")`. Parse: blank/whitespace → set `row_state.stitch_position = None`; all-digits and `1 <= int <= 9999` → set the int; anything else → return the `_row.html` fragment with `stitch_error=True` added to context, status 200, **no DB write, no commit**. Valid path: ownership + repetition + `RowState` fetch exactly as the toggle route, set the value, bump `project.updated_at`, `await session.commit()`, return the `_row.html` fragment (200) with `rep_number` in context.

#### 3. `_row.html` renders the stitch input for in-progress rows

**File**: `app/templates/projects/_row.html`

**Intent**: The input appears exactly when relevant — state `in_progress` — as a sibling of the toggle button (never nested inside it), saving on change via HTMX with the same fragment-swap and error-styling conventions as the toggle.

**Contract**: Context reads switch from `row_states[row.id]` to `row_progress[row.id]` (`state` and `stitch_position` off the object). After the toggle `<button>`, when `state == RowStateEnum in_progress` (compare via `state.value == "in_progress"`), render a `<label class="row-stitch">stitch <input type="number" min="1" max="9999" value="{{ stitch_position or '' }}" hx-post=".../reps/{{ rep_number }}/rows/{{ row.id }}/stitch" hx-trigger="change" hx-target="closest li" hx-swap="outerHTML" hx-on::responseError="<same handler as toggle>" aria-label="Stitch position for row {{ row.position }}"></label>`. When `stitch_error` is truthy, add `row-item--error` to the `<li>`'s class list (same visual signal as a failed request). The `<li>` layout becomes a flex row (button `flex: 1`, label shrink-0) via the page's local `<style>` block.

### Success Criteria:

#### Automated Verification:

- New tests pass: `uv run pytest tests/test_row_state_routes.py -v` (stitch set → DB + fragment show value; blank clears to NULL; invalid input → 200 error fragment, DB unchanged; stitch kept across not_started/in_progress/done cycles and re-shown on return to in_progress; input rendered only for in_progress rows on full-page GET; second-user POST → 404)
- Full suite still passes: `uv run pytest`

#### Manual Verification:

- Mark a row in-progress: the stitch input appears; type 14 and Tab out — the row updates in place with no reload; reload shows 14.
- Cycle the row to done (input disappears) and back to in-progress — 14 is still there.
- Clear the input and Tab out — the position is removed; reload confirms.
- Enter a non-number / 0 — the row shows the error styling and the stored value is unchanged (confirmed by reload).

---

## Testing Strategy

### Unit Tests:

- None standalone — rep resolution is exercised through route tests (query/cookie/clamp/404 matrix), matching the project's route-test-centric convention.

### Integration Tests (in `tests/test_row_state_routes.py`, mirroring the existing fixture/assertion conventions):

- Phase 1 — stepper: increase 1→3 creates `ElementRepetition`s 2-3 and seeds `not_started` RowStates for every row (fresh-query counts: reps == 3, states == 3 × row count); decrease 3→2 deletes rep 3 and its RowStates only; `repeat_count=0` → 200 with `repeat_error` in body; no-rows element stepper changes the field without creating reps.
- Phase 1 — per-rep isolation: with ×2, toggle row 1 in rep 2; fresh queries show rep 2's RowState `in_progress`, rep 1's still `not_started`.
- Phase 1 — rep resolution: `?rep=2` renders rep 2's states (seed differing states via toggles); `?rep=99` → 404; `?rep=2` response sets `last_rep_{element_id}` cookie, and a subsequent bare GET (client retains cookies) renders rep 2's states; bare GET with no cookie renders rep 1.
- Phase 1 — auto-jump: rep 1 all done, rep 2 row 2 not started → `?rep=2` marks rep 2's row 2 `row-item--current`; `?rep=1` has no current row.
- Phase 1 — existing tests: all toggle/auto-jump URLs updated to `/reps/1/...`; assertions otherwise unchanged.
- Phase 2 — stitch: set 14 on an in_progress row → fresh query `stitch_position == 14`, fragment contains `value="14"`; blank → `stitch_position is None`; `"abc"` / `"0"` → 200 with `row-item--error` in fragment, DB value unchanged; set 14, cycle done → not_started → in_progress, value still 14 and input re-rendered with it; full-page GET shows `.row-stitch` only on in_progress rows; `second_user` POST to stitch route → 404.
- Ownership on the stepper route: `second_user` POST → 404 (mirrors `test_toggle_other_user_sees_404`).

### Manual Testing Steps:

1. Create ×2 on an element with a pattern; confirm pills appear and each rep starts all not-started.
2. Mark different rows in each rep; reload and switch pills — independence holds; reopen the bare element URL — you land on the last-viewed rep, jumped to its first non-done row.
3. Decrease ×2 → ×1 via the stepper; confirm the dialog, then confirm Rep 2's progress is gone.
4. Mark a row in-progress, enter stitch 14, reload — still 14; cycle away and back — still 14; clear it — gone after reload.

## Performance Considerations

No new hot paths: the 100ms NFR scope is unchanged (row toggle + stitch save are both single-row UPDATEs returning one small fragment). Rep switching and the stepper are full-page navigations off the critical path. `_render_element_detail` adds one indexed `ElementRepetition` lookup (`element_id` index, `project.py:43`) per render. Seeding on stepper increase is `reps_added × rows` inserts in one commit — bounded by the 99 rep cap and realistic pattern sizes at the project's stated `qps: low` / `data_volume: small` scale.

## Migration Notes

None. Every column and constraint this plan uses (`Element.repeat_count`, `ElementRepetition` + its unique `(element_id, repetition_number)`, `RowState.stitch_position`, `RowState` unique `(element_repetition_id, row_id)`) exists from F-01. Existing rows are unaffected: every element has `repeat_count=1` and one rep today, which the new code treats as the degenerate case (no pills, `/reps/1/` URLs, cookie defaults to 1).

## References

- Archived S-02 plan/research (conventions this plan extends): `context/archive/2026-07-09-row-marking-and-persistence/plan.md`, `context/archive/2026-07-09-row-marking-and-persistence/research.md`
- Roadmap slice + risk note: `context/foundation/roadmap.md` (S-03)
- PRD requirements: `context/foundation/prd.md` (FR-003, FR-010)
- Rep-scoping ground zero: `app/routes/projects.py:109-128` (`_get_element_repetition`), `674-714` (toggle route)
- Per-rep seeding already in place: `app/routes/projects.py:644-659`
- Destructive-confirm precedent: `app/templates/projects/element_detail.html:266`
- Test conventions to mirror: `tests/test_row_state_routes.py:9-71`, `tests/conftest.py`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Repeat count + per-repetition tracking

#### Automated

- [x] 1.1 Updated + new tests pass: `uv run pytest tests/test_row_state_routes.py -v` — d157bc5
- [x] 1.2 Full suite still passes: `uv run pytest` — d157bc5

#### Manual

- [x] 1.3 Set ×3: pills appear, each rep shows all rows at not-started — d157bc5
- [x] 1.4 Per-rep independence: different marks per rep persist across reloads and pill switches — d157bc5
- [x] 1.5 Bare URL reopens on last-viewed rep, jumped to its first non-done row — d157bc5
- [x] 1.6 Decrease ×3 → ×2: confirm dialog, Rep 3 gone with its progress — d157bc5
- [x] 1.7 No-pattern element: stepper changes count, no pills, page otherwise unchanged — d157bc5

### Phase 2: Stitch position recording

#### Automated

- [x] 2.1 New tests pass: `uv run pytest tests/test_row_state_routes.py -v` (stitch cases)
- [x] 2.2 Full suite still passes: `uv run pytest`

#### Manual

- [x] 2.3 Stitch input appears on in-progress row, saves on change without reload, persists across page reload
- [x] 2.4 Stitch value survives cycling to done and back to in-progress
- [x] 2.5 Clearing the input removes the position (confirmed after reload)
- [x] 2.6 Invalid input shows error styling; stored value unchanged
