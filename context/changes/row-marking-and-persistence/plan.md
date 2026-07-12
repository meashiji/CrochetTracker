# Row marking + persistence (S-02, north star) Implementation Plan

## Overview

Implements the smallest end-to-end flow that proves CrochetTracker's product hypothesis: a user taps a row to cycle it through three states (not started → in-progress → done), the mark persists immediately with no manual save, and reopening the element view auto-jumps to the first unmarked row. This closes FR-006, FR-007, and US-01.

## Current State Analysis

- `app/routes/projects.py` has ownership-check helpers `_get_project` (23-27) and `_get_project_and_element` (30-40), and an established convention (`element_create:153`, `element_save_pattern:250`) of calling `await session.commit()` explicitly before a `RedirectResponse`, because `get_session` (`app/db.py:16-23`) commits during dependency teardown, *after* the handler returns — late enough that a 303's follow-up GET can race it.
- `RowState` (`app/models/progress.py:14-27`) already has `state: RowStateEnum` (`not_started`/`in_progress`/`done`) and `stitch_position` (unused, S-03). `element_save_pattern` (`app/routes/projects.py:216-242`) already seeds one `RowState` per `(ElementRepetition, Row)` pair at `not_started` on every pattern save — so a `RowState` row is guaranteed to exist for every row before this plan's route ever runs. **No migration is needed.**
- Every `Element` is created with `repeat_count=1` hard-coded (`app/routes/projects.py:81,146`); there is no route or form to change it. So exactly one `ElementRepetition` exists per element today — this plan can address "the row's state" as effectively 1:1 with `Row`, without building repetition-selection UI (that's S-03's job).
- `element_detail` (`app/routes/projects.py:158-175`) currently queries only `Row`, with no `RowState` join, and renders a static, non-interactive `<li>` per row (`app/templates/projects/element_detail.html:76-81`) — the grey dot is decorative CSS, not state-driven.
- The codebase has **zero** client-side JS or HTMX today (confirmed repo-wide: no `<script>` tags, no `.js` files, no `hx-*` attributes). However, `context/foundation/tech-stack.md:29` already commits this project to "FastAPI with Jinja2 templates + HTMX + Tailwind" — S-01 deliberately shipped without HTMX and named S-02 as where it lands (`context/changes/project-and-pattern-display/plan.md:47,50`). Introducing HTMX here executes a decision already on record, not one this plan is opening fresh.
- No CSRF protection exists anywhere in the app (confirmed via grep) — this plan does not add any, matching the existing convention.
- `tests/test_project_routes.py` establishes the test shape this plan follows: `(test_user, async_client, db_session)` fixtures, `follow_redirects=False`, DB-state assertions via a **fresh** `db_session.execute(select(...))` query, manual FK-ordered teardown.
- Full grounding: `context/changes/row-marking-and-persistence/research.md`.

## Desired End State

A signed-in user opens an element's pattern page and sees each row rendered with a tappable state control (not started / in-progress / done, in that cycle). Tapping it updates the row's visual state within roughly 100ms with no full-page reload, and the new state is durably committed before the response returns. Reopening the same element (fresh page load, another day, another device) shows every row's exact last-saved state and auto-scrolls to the first row that isn't `done` yet.

**Verification**: manually mark a row done, close the tab, reopen `/projects/{id}/elements/{id}` — the mark is still there and the view has scrolled to the first non-done row. Automated tests cover cycling, persistence, ownership, and the auto-jump computation.

### Key Discoveries:

- `app/db.py:16-23` — `get_session`'s commit runs strictly after the handler returns; the commit-before-redirect convention is established twice already and reviewed (`context/changes/project-and-pattern-display/reviews/impl-review-phase-3.md:29`, F1).
- `app/routes/projects.py:216-242` — `RowState` rows are pre-seeded at pattern-save time; the toggle route only ever needs to `SELECT ... FOR UPDATE`-then-update, never insert-or-create.
- `app/models/project.py:31` + grep confirmation — `repeat_count` is always `1` today; exactly one `ElementRepetition` per element.
- `context/foundation/tech-stack.md:29` — HTMX + Tailwind are the named stack; this plan introduces HTMX only (Tailwind is P-01's scope, out of scope here — the existing hand-written CSS system stays).
- `context/foundation/roadmap.md:118` — the 100ms NFR is the reason HTMX is warranted; this plan treats it as a phase of its own (Phase 3) layered on top of a working, if slower, Phase 1.

## What We're NOT Doing

- Multi-repetition tracking UI or `repeat_count` editing (FR-003, S-03).
- Recording `stitch_position` within an in-progress row (FR-010, S-03). The toggle route only ever writes `RowState.state`.
- A project-detail-page progress summary/aggregate indicator (not required by FR-006/FR-007; `project_detail`'s existing row-count display is untouched).
- Designing the final live-sync error UX (toast/banner/modal) — PRD Open Question 1 is user-owned and not blocking. This plan guarantees only that a failed row-mark visibly signals failure and never silently discards state.
- A no-JS / progressive-enhancement fallback for the row-toggle control once HTMX ships in Phase 3. Phase 1's plain-form mechanism is an interim implementation, fully superseded (not kept as a fallback) once Phase 3 lands — matching the product's existing "active connection required, live sync only" access-control model (PRD Access Control section), which already assumes JS-capable, connected clients.
- Live re-jump/re-highlighting of the "current row" within an already-open page after a toggle. FR-007 says "on opening a project" — auto-jump is computed once, at page load, not re-derived after every in-session toggle.
- Rate limiting or debouncing rapid repeated taps on the same row.
- CSRF protection (not present anywhere else in this app today).
- Tailwind adoption, stitch reference panel, account recovery — separate roadmap slices (P-01, S-04, open question 2).

## Implementation Approach

Three phases, each independently shippable and each ending in a manually-verifiable improvement to the same user-facing flow:

1. **Phase 1** ships FR-006 end-to-end with the simplest possible mechanism — a per-row POST that cycles state and redirects back to a full page reload. This alone proves persistence (the core hypothesis) even before the NFR is met.
2. **Phase 2** adds FR-007 — the auto-jump computation and the scroll/highlight behavior — on top of Phase 1's already-working persistence, independent of how the toggle is transported.
3. **Phase 3** replaces Phase 1's redirect-based toggle with an HTMX fragment swap to meet the 100ms NFR, and adds a minimal (not final-design) failure indicator so a failed write is never silent.

This mirrors the project's existing "ship the simplest version first, enhance after" convention (S-01's parser: "ship the simplest split first, make boundaries editable in a follow-up").

## Critical Implementation Details

**Timing & lifecycle**: The toggle route's response shape changes between phases — Phase 1 returns a `RedirectResponse` (303) to `element_detail`; Phase 3 replaces this with a direct fragment `TemplateResponse` (200) carrying just the updated `<li>`. Phase 3 must therefore update Phase 1's tests (which assert `303` + `Location`) to assert `200` + fragment content instead — this is expected rework, not a regression. In both phases, call `await session.commit()` explicitly before returning, even in Phase 3 where there's no redirect to race: nothing in `get_session` guarantees the commit fires before the response body is transmitted, and the fragment response must reflect durably-committed state for consistency with the rest of the codebase's established discipline.

**Performance constraints**: HTMX must be vendored into `app/static/js/htmx.min.js` (downloaded once, committed to the repo) rather than loaded from a CDN. A third-party CDN adds an external network hop directly on the 100ms-critical path and a runtime dependency this Python-only, self-contained deploy (Dockerfile + Fly.io) doesn't otherwise have.

## Phase 1: Row-state toggle route + persistence (full-page)

### Overview

Adds the mutating route that cycles a row's state and a plain-form UI to trigger it. No HTMX yet — full page reload after each tap. This alone satisfies FR-006's data-model and persistence requirements.

### Changes Required:

#### 1. Ownership + state helpers

**File**: `app/routes/projects.py`

**Intent**: Add a helper that resolves and ownership-checks a `(project, element, row)` triple, and a helper that fetches the element's single `ElementRepetition`, mirroring the existing `_get_project_and_element` pattern.

**Contract**: `async def _get_project_element_and_row(project_id, element_id, row_id, user, session) -> tuple[Project, Element, Row]` — raises `HTTPException(404)` if the row doesn't belong to the element (reuses `_get_project_and_element` internally). `async def _get_element_repetition(element_id, session) -> ElementRepetition` — `select(ElementRepetition).where(ElementRepetition.element_id == element_id)`, `.scalar_one()` (safe today since `repeat_count` is always 1; will need revisiting when S-03 allows >1).

#### 2. Row-state cycle constant

**File**: `app/routes/projects.py`

**Intent**: Define the fixed 3-state cycle order used by the toggle route.

**Contract**: `ROW_STATE_CYCLE: dict[RowStateEnum, RowStateEnum] = {not_started: in_progress, in_progress: done, done: not_started}` — module-level constant near `MAX_PATTERN_LENGTH`.

#### 3. Toggle route

**File**: `app/routes/projects.py`

**Intent**: A POST route that advances one row's `RowState.state` by one step in the cycle, touches `project.updated_at` (matching the existing convention that any project mutation bumps it), commits explicitly, and redirects back to the element detail page.

**Contract**: `@router.post("/{project_id}/elements/{element_id}/rows/{row_id}/state")`. Resolves ownership via the new helper; fetches the row's `RowState` via `select(RowState).where(RowState.row_id == row_id, RowState.element_repetition_id == repetition.id)`, `.scalar_one()` (guaranteed to exist per Key Discoveries); looks up the next state via `ROW_STATE_CYCLE`; sets `row_state.state`; `session.add(row_state)`; sets `project.updated_at = datetime.now(timezone.utc)`, `session.add(project)`; `await session.commit()`; returns `RedirectResponse(url=f"/projects/{project_id}/elements/{element_id}", status_code=303)`. Does not touch `stitch_position`.

#### 4. Row-state query on GET

**File**: `app/routes/projects.py`

**Intent**: `element_detail` must know each row's current state to render it. Extract this as a shared helper (not inlined in the route) because a second call site needs the identical data — see item 4a.

**Contract**: `async def _build_row_states(element_id, rows, session) -> dict[int, RowStateEnum]`. If `rows` is empty, return `{}` immediately (an element with no pattern saved yet has zero `ElementRepetition` rows — do not query for one, `.scalar_one()` would raise `NoResultFound`). Otherwise fetch the element's `ElementRepetition` (`.scalar_one()` is safe here since `rows` being non-empty guarantees `element_save_pattern` has run at least once) and query `RowState` rows for it, building the dict keyed by `row_id` (default `not_started` if somehow missing, defensively). In `element_detail`, call this helper after fetching `rows` and pass the resulting `row_states` into the template context alongside `rows`.

#### 4a. Same context in the pattern-save error path

**File**: `app/routes/projects.py`

**Intent**: `element_save_pattern`'s `_rerender_with_error` closure (lines 189-205) re-renders `projects/element_detail.html` on validation failure, using the element's *existing* rows (the save was rejected, so old rows are still current). Once `element_detail.html` requires `row_states` for its `_row.html` include (item 6), this closure must supply it too, or a validation failure on an element that already has rows will crash with a Jinja `UndefinedError` instead of showing the intended error banner.

**Contract**: In `_rerender_with_error`, after fetching `rows` (line 191-193), call the same `_build_row_states(element.id, rows, session)` helper from item 4 and add `row_states` (and `current_row_id`, once Phase 2 introduces it — see Phase 2 item 1) to the context dict passed to `TemplateResponse`.

#### 5. Row partial template

**File**: `app/templates/projects/_row.html` (new)

**Intent**: A single reusable Jinja partial rendering one row's `<li>`, its current-state indicator, and the toggle control — used both by the full-page row list and (from Phase 3 onward) as the HTMX fragment response, so both render paths can never drift.

**Contract**: Expects `row` (Row), `state` (RowStateEnum), `project`, `element` in context. Renders `<li id="row-{{ row.id }}" class="row-item row-item--{{ state.value }}">` containing a `<form method="post" action="/projects/{{ project.id }}/elements/{{ element.id }}/rows/{{ row.id }}/state">` with a submit button showing a state glyph (○ not_started / ◐ in_progress / ● done) plus an `aria-label` naming the current state and row content text.

#### 6. Element detail template update

**File**: `app/templates/projects/element_detail.html`

**Intent**: Replace the static `<li>` loop with `{% include "projects/_row.html" %}` per row, passing `state=row_states.get(row.id)`.

**Contract**: Existing `.row-list`/`.row-dot` CSS is replaced with row-state–aware styling (`.row-item`, `.row-item--not_started`, `.row-item--in_progress`, `.row-item--done`) added to the page's existing local `<style>` block (element_detail.html:4-52) — no changes to `base.html`/`styles.css` in this phase.

### Success Criteria:

#### Automated Verification:

- New/updated tests pass: `uv run pytest tests/test_row_state_routes.py -v`
- Full suite still passes: `uv run pytest`

#### Manual Verification:

- Opening an element with a saved pattern shows every row with a visible not-started indicator.
- Tapping a row's control cycles it not_started → in_progress → done → not_started, with the page reloading and showing the new state each time.
- Restarting the dev server (or reconnecting from another browser session as the same user) and reopening the element shows the exact same states as last set.

---

## Phase 2: Auto-jump to first unmarked row

### Overview

Adds FR-007: on opening an element, the view scrolls to and highlights the first row that isn't `done`. If every row is `done`, no scroll/highlight happens (the page simply opens at the top, its natural default).

### Changes Required:

#### 1. Auto-jump computation

**File**: `app/routes/projects.py`

**Intent**: Compute which row (if any) is "current" — the first row, in `position` order, whose state is not `done`. Extract as a small helper alongside `_build_row_states` (Phase 1 item 4) since both call sites (`element_detail` and `_rerender_with_error`, Phase 1 item 4a) need it.

**Contract**: `def _first_unmarked_row_id(rows, row_states) -> int | None` — iterate `rows` in their existing `position`-ordered sequence and return the `id` of the first whose `row_states.get(row.id) != RowStateEnum.done`; `None` if all rows are `done` or `rows` is empty. Call this from both `element_detail` and `_rerender_with_error`, passing `current_row_id` into each's template context.

#### 2. Highlight + scroll in template

**File**: `app/templates/projects/_row.html`

**Intent**: Let the partial mark itself as the current row when applicable, so both the full-page render and later fragment renders stay consistent.

**Contract**: Accept an additional `is_current` boolean in context (`is_current = (row.id == current_row_id)` computed by the caller); when true, add a `row-item--current` class to the `<li>`.

**File**: `app/templates/projects/element_detail.html`

**Intent**: Pass `is_current` into each `_row.html` include, and add a tiny inline script that scrolls the current row into view on page load — the first vanilla JS in this codebase, intentionally minimal.

**Contract**: Add `{% block scripts %}` (new block, see Phase 3 item 1 for the matching `base.html` change) containing: if `current_row_id` is set, a `DOMContentLoaded` listener that calls `document.getElementById("row-" + current_row_id).scrollIntoView({block: "center"})` guarded by a null check.

#### 3. `base.html` scripts block

**File**: `app/templates/base.html`

**Intent**: Add the extension point Phase 2's inline script needs, ahead of Phase 3's HTMX script tag landing in the same block region.

**Contract**: Add `{% block scripts %}{% endblock %}` immediately before `</body>` (after `</div>` closing `.app-shell`, base.html:431).

### Success Criteria:

#### Automated Verification:

- New tests pass: `uv run pytest tests/test_row_state_routes.py -v` (auto-jump cases: mixed states, all-done, no-rows)
- Full suite still passes: `uv run pytest`

#### Manual Verification:

- An element with rows 1-2 done and rows 3+ not started: opening it scrolls the page so row 3 is visible and visually distinct from the rest.
- An element with every row done: opening it shows the full list from the top, no scroll jump, no error.
- An element with no pattern pasted yet: opening it behaves exactly as before (unaffected).

---

## Phase 3: HTMX fragment swap for the 100ms NFR

### Overview

Replaces Phase 1's redirect-based toggle with an HTMX-driven fragment swap so a tap updates the DOM without a full page reload, meeting the PRD's 100ms NFR. Also adds a minimal, visible failure indicator so a failed write is never silent (PRD guardrail), without designing the final error-UX treatment (Open Question 1, deferred to the user).

### Changes Required:

#### 1. Vendor HTMX

**File**: `app/static/js/htmx.min.js` (new)

**Intent**: Commit a pinned copy of HTMX 2.0.4 into the repo's static assets (no CDN, no npm build step — matches the project's Python-only, no-JS-tooling baseline).

**Contract**: Downloaded verbatim from the official htmx 2.0.4 release; served as-is via the existing `/static` mount (`app/main.py:27`).

#### 2. Load HTMX site-wide

**File**: `app/templates/base.html`

**Intent**: Make HTMX available on every page (row-marking is the first consumer; later slices can use it without re-adding the script tag).

**Contract**: Add `<script src="{{ url_for('static', path='js/htmx.min.js') }}"></script>` immediately before the `{% block scripts %}{% endblock %}` added in Phase 2, inside `<body>`.

#### 3. Toggle route returns a fragment

**File**: `app/routes/projects.py`

**Intent**: The same toggle route from Phase 1 now returns the updated row's rendered fragment instead of redirecting, so HTMX can swap it in place.

**Contract**: Replace the `RedirectResponse` return with `templates.TemplateResponse(request, "projects/_row.html", {"project": project, "element": element, "row": row, "state": row_state.state, "is_current": False}, status_code=200)`. The toggled row's fragment always renders with `is_current=False` — a fixed value, not recomputed. The explicit `await session.commit()` before this return is unchanged from Phase 1.

Decision on `is_current` in the fragment response: the current-row highlight is a page-load-only "where do I resume" cue (Phase 2, FR-007's literal "on opening a project"). Recomputing it live on every toggle would mean re-running the whole auto-jump scan per request, which the "Live re-jump ... out of scope" item above deliberately excludes. Hard-coding `False` is correct in every case that matters: if the toggled row *was* the current row, the user is actively acting on it — the highlight has already served its purpose for this visit, and it's fine for it to disappear until the next full page load recomputes it; if it *wasn't* the current row, `False` is simply correct.

#### 4. Row partial becomes an HTMX control

**File**: `app/templates/projects/_row.html`

**Intent**: Convert the plain form button into an HTMX-driven control that posts to the same route, swaps itself, and visibly flags a failed request instead of doing nothing.

**Contract**: Replace the `<form method="post">` with a `<button type="button" hx-post="{{ toggle_url }}" hx-target="closest li" hx-swap="outerHTML" hx-on::response-error="this.closest('li').classList.add('row-item--error')">` (where `toggle_url` is the same URL Phase 1's form used). Add a `.row-item--error` CSS rule (element_detail.html's local `<style>` block) giving a visible red outline/inline text — the minimal, non-final failure signal the PRD guardrail requires ("does not silently lose a row mark ... surfaces a clear retry signal").

#### 5. Update Phase 1's tests for the new response shape

**File**: `tests/test_row_state_routes.py`

**Intent**: Phase 1's tests asserted `303` + `Location`; the route no longer redirects.

**Contract**: Update those assertions to `response.status_code == 200` and check the fragment body contains the new state's glyph/aria-label; DB-state assertions via a fresh `db_session` query are unchanged.

### Success Criteria:

#### Automated Verification:

- Updated + new tests pass: `uv run pytest tests/test_row_state_routes.py -v`
- Full suite still passes: `uv run pytest`

#### Manual Verification:

- Tapping a row's control updates its visible state without a full-page flash/reload, subjectively near-instant.
- Stopping the app server mid-request (or pointing the client at a broken URL temporarily) and tapping a row shows the `row-item--error` visual treatment rather than silently doing nothing; the DB state is confirmed unchanged by a fresh query afterward.
- Reopening the element after a Phase-3 toggle still shows Phase 2's auto-jump/highlight behavior correctly on the next full load.

---

## Testing Strategy

### Unit Tests:

- `ROW_STATE_CYCLE` produces the exact expected next-state for all three inputs.

### Integration Tests (in `tests/test_row_state_routes.py`, mirroring `tests/test_project_routes.py`'s fixture/assertion conventions):

- Toggling a row cycles `not_started` → `in_progress` → `done` → `not_started` across three sequential POSTs, each verified via a fresh `db_session` query.
- Toggling a row owned by another user's element returns 404 (mirrors `test_project_detail_other_user_sees_404`).
- Toggling a `row_id` that exists but belongs to a different element than the one in the URL returns 404.
- `element_detail` GET reflects each row's persisted state (e.g., a row seeded as `done` renders its done indicator).
- Auto-jump: rows 1-2 seeded `done`, rows 3-4 `not_started` → `element_detail` response identifies row 3 as current (Phase 2).
- Auto-jump edge case: all rows `done` → no current row identified, page renders without error (Phase 2).
- Auto-jump edge case: element has no pattern/rows yet → `element_detail` renders unchanged (no crash on empty row list; `_build_row_states` must short-circuit before querying `ElementRepetition`).
- Saving an invalid pattern (too long, or produces no rows) on an element that already has rows and mixed states → `_rerender_with_error`'s re-render succeeds (200, error banner shown) rather than raising a Jinja `UndefinedError` for a missing `row_states`/`current_row_id` context.
- Phase 3: toggling returns `200` with the fragment body (not a redirect); DB state still updates and is verified via a fresh query.

### Manual Testing Steps:

1. Create a project + element, paste a short pattern, open the element page — every row starts not-started.
2. Tap through a row's three states and confirm each persists across a page reload.
3. Mark several rows done in order, reload the page, confirm the view has jumped to the first non-done row.
4. Mark every row done, reload, confirm no scroll/error and the list still renders top-to-bottom.
5. After Phase 3 ships: tap a row and confirm the update feels instant with no full-page reload; then simulate a failure (e.g., stop the server briefly) and confirm a visible error indicator appears rather than silence.

## Performance Considerations

The 100ms NFR is addressed structurally by Phase 3's HTMX fragment swap (single small HTML response instead of a full page) combined with vendoring HTMX locally (no CDN round-trip on the critical path). No caching or async job queue is needed — this is a single-row UPDATE plus a single-row SELECT-and-render, well within budget on the project's stated `qps: low` / `data_volume: small` target scale.

## Migration Notes

None. `RowState`, `RowStateEnum`, and `ElementRepetition` already exist from F-01 with the exact fields this plan needs; confirmed via grep that no route or model change to `repeat_count` handling is required.

## References

- Related research: `context/changes/row-marking-and-persistence/research.md`
- Commit-before-redirect precedent: `app/routes/projects.py:153,250`; enforced again in `context/changes/project-and-pattern-display/reviews/impl-review-phase-3.md:29` (F1)
- Ownership-check pattern to extend: `app/routes/projects.py:23-40`
- Test conventions to mirror: `tests/test_project_routes.py:62-99`
- HTMX/Tailwind stack decision: `context/foundation/tech-stack.md:29`
- HTMX deferral from S-01 to S-02: `context/changes/project-and-pattern-display/plan.md:47,50`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Row-state toggle route + persistence (full-page)

#### Automated

- [x] 1.1 New/updated tests pass: `uv run pytest tests/test_row_state_routes.py -v`
- [x] 1.2 Full suite still passes: `uv run pytest`

#### Manual

- [x] 1.3 Opening an element with a saved pattern shows every row with a visible not-started indicator
- [x] 1.4 Tapping a row's control cycles it not_started → in_progress → done → not_started, page reloading and showing new state each time
- [x] 1.5 Reopening the element (fresh session) shows the exact same states as last set

### Phase 2: Auto-jump to first unmarked row

#### Automated

- [ ] 2.1 New tests pass: `uv run pytest tests/test_row_state_routes.py -v` (auto-jump cases)
- [ ] 2.2 Full suite still passes: `uv run pytest`

#### Manual

- [ ] 2.3 Element with rows 1-2 done, 3+ not started: opening scrolls to row 3, visually distinct
- [ ] 2.4 Element with every row done: opens at the top, no scroll jump, no error
- [ ] 2.5 Element with no pattern pasted yet: unaffected

### Phase 3: HTMX fragment swap for the 100ms NFR

#### Automated

- [ ] 3.1 Updated + new tests pass: `uv run pytest tests/test_row_state_routes.py -v`
- [ ] 3.2 Full suite still passes: `uv run pytest`

#### Manual

- [ ] 3.3 Tapping a row's control updates its state without a full-page reload, subjectively near-instant
- [ ] 3.4 Simulated server failure shows the `row-item--error` visual treatment; DB state confirmed unchanged via fresh query
- [ ] 3.5 Reopening the element after a Phase-3 toggle still shows correct auto-jump/highlight on next full load
