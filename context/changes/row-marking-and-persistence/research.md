---
date: 2026-07-09T21:11:57+02:00
researcher: Claude
git_commit: 682ce008ea4489f6fcf5cab6bf8b095c8ac370a5
branch: worktree-agent-ab2a03f90db06c88d
repository: CrochetTracker
topic: "S-02 row-marking-and-persistence: implementing row-state toggling, auto-jump, and persistence"
tags: [research, codebase, row-state, htmx, persistence, projects-routes]
status: complete
last_updated: 2026-07-09
last_updated_by: Claude
---

# Research: S-02 row-marking-and-persistence

**Date**: 2026-07-09T21:11:57+02:00
**Researcher**: Claude
**Git Commit**: 682ce008ea4489f6fcf5cab6bf8b095c8ac370a5
**Branch**: worktree-agent-ab2a03f90db06c88d
**Repository**: CrochetTracker

## Research Question

How should the north-star slice (S-02, row-marking-and-persistence) be implemented, grounded in current code? Specifically: how does the DB-session commit/redirect pattern work, what test conventions exist, what frontend/JS footprint exists today, has HTMX already been decided as part of the stack, and how does the existing `RowState`/`ElementRepetition` schema constrain the row-marking UI.

## Summary

- `get_session` (app/db.py:16-23) commits **after** the route handler returns, during FastAPI's dependency-generator teardown. The established project pattern (already used twice, in `element_create` and `element_save_pattern`) is an explicit `await session.commit()` before issuing a redirect, because a 303 redirect makes the browser issue a new GET that can race the deferred commit. A plain 200 response (fragment or full page) doesn't trigger this race by itself, but if a row-mark POST needs its own state visible to any subsequent request (including a same-page re-render, an HTMX out-of-band swap that queries fresh state, or a follow-up GET on reload), the same explicit-commit-before-return discipline should be applied defensively — nothing in `get_session` guarantees the commit runs before the response body is transmitted.
- `context/foundation/tech-stack.md:29` **already commits this project to HTMX + Tailwind** as part of the chosen stack ("FastAPI with Jinja2 templates + HTMX + Tailwind for server-rendered web pages"). HTMX is not an ad-hoc new dependency to debate — it's a previously-made, documented stack decision that S-01 explicitly deferred to S-02 (`context/changes/project-and-pattern-display/research.md:173`: "S-01 can introduce it ... or ship plain form-submit first ... Decision for /10x-plan" — and S-01's plan.md:47 explicitly chose "No HTMX — all interactions are full-page form submits" for S-01, naming S-02 as where it lands). Today the codebase has **zero** JS/HTMX footprint: no `<script>` tags, no JS files, no `hx-*` attributes anywhere (confirmed by grep across the whole repo).
- Every `Element` today is created with `repeat_count=1` hard-coded (app/routes/projects.py:81, :146) and there is no UI/route to change it — `repeat_count` is a stored field with no way to edit it yet (FR-003 / S-03 territory). This means **exactly one `ElementRepetition` row exists per element today**, which meaningfully simplifies S-02's scope: the plan does not need to handle "which repetition is the user marking" — there is only ever one.
- `RowState` (app/models/progress.py) already has everything S-02 needs: `state: RowStateEnum` (`not_started`/`in_progress`/`done`) and `stitch_position: int | None` (S-03 territory, not S-02's job), unique on `(element_repetition_id, row_id)`, with an `onupdate` timestamp. **No migration is needed for S-02** — confirmed by grep: `repeat_count` and the RowState schema are unchanged since F-01.
- `element_save_pattern` (app/routes/projects.py:178-252) already seeds a `RowState` row per `(repetition, row)` pair at `not_started` on every pattern save (line 239) — so by the time S-02's route runs, a `RowState` row is guaranteed to exist for every row/repetition pair; no upsert-vs-create ambiguity.
- `context/foundation/test-plan.md:46` already names this exact feature as **Risk #1** in the QA risk map ("Row-mark write silently fails — HTMX POST returns an error, UI updates, DB doesn't"), with a Risk Response Guidance line (`test-plan.md:65`) that explicitly expects an HTMX response and calls for an integration test verifying "DB record and HTMX response fragment" — reinforcing that HTMX is the expected implementation path, not a novel option.
- `project_detail` (app/routes/projects.py:86-109) currently computes only a plain row **count** per element (no RowState aggregation) for `projects/detail.html`. S-02's "auto-jump to first unmarked row" logic needs a new query joining `Row` to `RowState` (via the element's single `ElementRepetition`) ordered by `Row.position`, picking the first row whose `RowState.state != done` (exact semantics — "first unmarked" vs "first not-done" — is a decision for `/10x-plan`, see Open Questions below).
- Test conventions are established and mirror-able: `tests/test_project_routes.py` fixtures `(test_user, async_client, db_session)`, `follow_redirects=False` on all POSTs, asserting status/`Location` header, verifying DB state via a **fresh** `db_session.execute(select(...))` query (not the request's own session), and manual per-test teardown deletes. No test currently exercises `element_save_pattern` or any row-state route; a new test file/section can mirror `test_add_element_redirects_to_its_detail` (tests/test_project_routes.py:62-84).
- Review-document shape is established: `plan-review.md` uses Verdicts table (End-State Alignment / Lean Execution / Architectural Fitness / Blind Spots / Plan Completeness), a Grounding line, and Findings with Severity (❌ CRITICAL / ⚠️ WARNING / 💡 OBSERVATION) / Impact / Dimension / Location / Detail / Fix / Decision fields — the row-marking-and-persistence plan-review should match this shape (see `context/changes/project-and-pattern-display/reviews/plan-review.md`).

## Detailed Findings

### 1. DB session / commit-before-redirect pattern

- `app/db.py:16-23`:
  ```python
  async def get_session() -> AsyncGenerator[AsyncSession, None]:
      async with AsyncSessionLocal() as session:
          try:
              yield session
              await session.commit()
          except Exception:
              await session.rollback()
              raise
  ```
  `AsyncSessionLocal` is built with `expire_on_commit=False` (app/db.py:12), so ORM objects stay usable post-commit without a refresh.
- The commit at line 20 always runs strictly after the route handler returns its response object, as generator-teardown code. This is independent of response type (redirect, template, JSON) — nothing in `get_session` special-cases status codes.
- Existing precedent for explicit pre-return commits: `app/routes/projects.py:153` (`element_create`) and `app/routes/projects.py:250` (`element_save_pattern`), both with comments explaining the redirect race: the 303 tells the browser to issue a new GET immediately, and that GET can reach the app before `get_session`'s deferred commit runs. This exact reasoning is also restated in `context/changes/project-and-pattern-display/reviews/impl-review-phase-3.md:29` (F1), confirming it as an established, reviewed, and enforced project convention — not a one-off comment.
- For S-02: any row-mark endpoint that redirects needs the same explicit commit. If the plan instead has the row-mark endpoint return an HTMX-swapped fragment (200, no redirect), there is no browser-initiated second request to race — but if the same request also needs to recompute and render fresh "first unmarked row" state (e.g., an out-of-band swap of a progress indicator elsewhere on the page) from a requery, an explicit commit before that requery is still the safer, consistent choice given no code in this repo relies on read-your-own-write-within-same-transaction behavior for cross-row aggregates.

### 2. HTMX / Tailwind — already the documented stack choice, currently unused

- `context/foundation/tech-stack.md:29`: "The stack runs FastAPI with Jinja2 templates + HTMX + Tailwind for server-rendered web pages: a Python-only pattern that respects the 4-week timeline and solo constraint."
- S-01 explicitly deferred HTMX to S-02: `context/changes/project-and-pattern-display/plan.md:47` ("No HTMX — all interactions are full-page form submits"), `plan.md:50` ("No row marking or state toggling (S-02).").
- `context/changes/project-and-pattern-display/research.md:171-173,223`: "S-01 can introduce it (the roadmap mentions HTMX for the 100ms row-mark NFR in S-02), or ship plain form-submit first. Decision for /10x-plan." / "HTMX is more relevant in S-02 (row-mark toggling). Safe to skip in S-01 and add in S-02."
- Current footprint (confirmed via repo-wide grep, `app/templates/base.html` full read, `app/static/` listing, `app/main.py` full read): zero `<script>` tags, zero `.js` files, zero `hx-*` attributes, no CDN includes, no `package.json`/npm tooling anywhere. `app/main.py` mounts `StaticFiles(directory="app/static")` at `/static` (app/main.py:27) and only serves `favicon.ico` + `styles.css` today.
- `context/foundation/test-plan.md:46,65` already frames the future row-mark endpoint in HTMX terms: "HTMX POST returns an error, UI updates, DB doesn't" (risk description) and the guidance line explicitly asks "What does the client do on a non-200 response?" and calls for verifying "DB record and HTMX response fragment."
- **Implication for /10x-plan**: introducing HTMX in S-02 is executing a stack decision already made in `tech-stack.md`, not opening a new one — but it is still the *first* time this codebase ships any client-side JS, so the plan should still name it as a concrete decision (which HTMX version/CDN vs vendored, what markup changes, what the fallback/no-JS behavior is) rather than treating it as risk-free.

### 3. Schema readiness — no migration needed

- `app/models/progress.py:8-27`: `RowStateEnum` already has `not_started`/`in_progress`/`done`; `RowState` already has `state`, `stitch_position: int | None`, `updated_at` (auto-`onupdate`), and a unique constraint on `(element_repetition_id, row_id)` (line 16).
- `app/models/project.py:38-44`: `ElementRepetition` has `element_id`, `repetition_number`, unique on `(element_id, repetition_number)`.
- `app/models/project.py:31`: `Element.repeat_count` defaults to 1 (`ge=1`), and **every element-creation call site hard-codes `repeat_count=1`** (app/routes/projects.py:81, :146) — no route or form field exists to change it. Confirmed by grep across `app/`: `repeat_count` only appears at those two creation sites, at the model default, and at `element_save_pattern`'s `range(1, element.repeat_count + 1)` (app/routes/projects.py:231).
- **Consequence**: today, exactly one `ElementRepetition` exists per `Element`. S-02's plan can scope its row-marking route/query to "the element's single repetition" without building repetition-selection UI — that's S-03's explicit job (roadmap S-03: "track each repetition with its own independent row progress").
- `element_save_pattern` (app/routes/projects.py:216-242) deletes and recreates `RowState` rows on every pattern save, seeding all of them to `not_started` (line 239) for every `(repetition, row)` pair. So a `RowState` row is guaranteed to exist for every row before S-02's route ever runs — the row-mark route can safely assume `RowState` exists and do an `UPDATE`/fetch-then-update rather than an upsert-or-create.

### 4. Current row rendering — no state awareness yet

- `element_detail` (app/routes/projects.py:158-175) queries only `Row` (ordered by `position`), passes `rows` to the template — it does **not** join or query `RowState` at all today.
- `app/templates/projects/element_detail.html:76-81` renders each row as a static `<li><span class="row-dot">●</span>{{ row.content }}</li>` — the "grey-dot indicator" mentioned in the task is purely decorative CSS (`.row-dot { color: #9e9e9e; }`, element_detail.html:48-51); it carries no state today.
- `project_detail` (app/routes/projects.py:86-109) computes a row **count** per element only (via `func.count(Row.id)` grouped by `element_id`, lines 98-103) — no RowState aggregation exists at the project-list level either. If the plan wants a per-element progress summary on the project detail page (not required by FR-006/FR-007 but a natural complement), that's a new query to design.
- **Auto-jump target**: FR-007 requires "the view jumps to the first unmarked row" on element open. Today's `element_detail` route has no concept of "first unmarked row" — the plan must add a query (join `Row` + `RowState` filtered to the element's one `ElementRepetition`, ordered by `Row.position`, first row where state is not `done` — or not `not_started`, this is a real semantic choice, see Open Questions) and decide how the template scrolls/highlights that row (a `#row-{id}` anchor + `scrollIntoView`, or server-side reordering/highlighting — since there is no JS today, an anchor-based `<a href="#row-N">` auto-focus or a CSS `:target` highlight are the no-JS-cost options, versus a small inline script if HTMX is being introduced anyway).

### 5. Test conventions to mirror

- `tests/conftest.py` (full file, 99 lines): tables created via `SQLModel.metadata.create_all` (not Alembic) in a session-scoped `_create_test_tables` fixture (lines 27-45); `_dispose_engines` (lines 48-60, autouse) disposes both engines after every test to avoid cross-event-loop asyncpg errors; `db_session` fixture (lines 63-67) rolls back only its own uncommitted work — tests that commit via the app's routes must manually delete their own rows in teardown; `test_user` fixture (lines 79-99) signs up via `POST /auth/signup`, sets the session cookie on the shared `async_client`, and tears down its own `Project`/`User` rows.
- `tests/test_project_routes.py` (100 lines) is the only route test file for `app/routes/projects.py`. Naming convention: `test_<subject>_<expected_outcome>`. Pattern for a mutating POST + redirect test (`test_add_element_redirects_to_its_detail`, lines 62-84): arrange via direct `db_session.add`+`commit`, act via `async_client.post(..., follow_redirects=False)`, assert `303`, requery via a **fresh** `db_session.execute(select(...))`, assert `Location` header string, then a real follow-up GET asserting `200`, then manual FK-ordered teardown. Non-redirect validation-error POSTs assert `200` + substring match in `response.text` (`test_add_element_blank_name_shows_error`, lines 87-99).
- No existing test exercises `element_save_pattern` or any row-state mutation end-to-end — S-02 is the first slice to need this; the plan should specify new test(s) mirroring the above shape, including DB-state verification via fresh query (not the request's session) to actually prove the explicit-commit-before-response discipline works.

### 6. Review-document shape (for the upcoming `/10x-plan-review`)

- `context/changes/project-and-pattern-display/reviews/plan-review.md`: header (Plan path / Mode: Deep / Date / Verdict: `SOUND (after fixes)` / Findings count), `## Verdicts` table with 5 dimensions (End-State Alignment, Lean Execution, Architectural Fitness, Blind Spots, Plan Completeness), `## Grounding` one-liner (existing-paths/symbols/brief↔plan/Progress↔phase mechanical checks), `## Findings` as `### F<n> — <title>` blocks with Severity (❌/⚠️/💡)/Impact/Dimension/Location/Detail/Fix/Decision fields.
- `impl-review-phase-{1,2,3}.md` use a related but distinct 6-dimension Verdicts table (Plan Adherence, Scope Discipline, Safety & Quality, Architecture, Pattern Consistency, Success Criteria) — not needed for a plan-review, but useful context for later `/10x-impl-review` on this same change.

## Code References

- `app/db.py:16-23` — `get_session` dependency; commit-after-yield semantics
- `app/routes/projects.py:23-40` — `_get_project` / `_get_project_and_element` ownership-check helpers to reuse
- `app/routes/projects.py:86-109` — `project_detail`; only computes row counts, no RowState join
- `app/routes/projects.py:153,250` — explicit `await session.commit()` before redirect, with rationale comments
- `app/routes/projects.py:158-175` — `element_detail`; no RowState awareness today
- `app/routes/projects.py:178-252` — `element_save_pattern`; seeds RowState at `not_started` for every (repetition, row) pair (line 239); deletes RowState/Row/ElementRepetition on re-save (lines 217-220)
- `app/models/progress.py:8-27` — `RowStateEnum`, `RowState` (state, stitch_position, unique constraint, onupdate timestamp)
- `app/models/project.py:24-44` — `Element.repeat_count` (default 1, never changed at runtime), `ElementRepetition`
- `app/models/pattern.py:5-12` — `Row` (element_id, position, content)
- `app/templates/projects/element_detail.html:76-81` — current static row-dot rendering (no state)
- `app/templates/base.html:1-434` — shared layout; no `<script>`, viewport meta present (line 6), CSS vars (lines 11-22)
- `app/static/styles.css` — duplicate of base.html's inline critical CSS; design tokens to extend consistently
- `tests/conftest.py:16-99` — fixtures: `_create_test_tables`, `_dispose_engines`, `async_client`, `db_session`, `test_user`
- `tests/test_project_routes.py:62-99` — mutating-POST test pattern to mirror

## Architecture Insights

- The project has a firm, twice-applied convention: any POST handler that both mutates state and redirects must call `await session.commit()` explicitly before returning the `RedirectResponse`, because `get_session`'s own commit runs during dependency teardown, after the response is already in flight, and a 303 lets the browser race that teardown with a follow-up GET.
- The schema was deliberately over-built in F-01 for S-02/S-03: `RowState.stitch_position` and `ElementRepetition` exist now but aren't used by any route yet — F-01's own risk note (roadmap.md:76) warned "a schema change after S-02 lands requires a data migration with live data. Define it carefully" — and it appears that caution paid off: nothing in S-02 requires a schema change.
- HTMX was pre-selected at the tech-stack level specifically for the reason S-02 needs it (the 100ms NFR), and S-01 deliberately deferred introducing it rather than debating it — so `/10x-plan` for this change is executing a decision, with the main remaining questions being *how* (endpoint shape, swap target, fragment template, no-JS fallback), not *whether*.
- Because every element currently has exactly one `ElementRepetition`, S-02 can treat "the row's state" as a 1:1 relationship with `Row` for now (join through the single repetition) without needing to design multi-repetition UI — that complexity is explicitly S-03's.

## Historical Context (from prior changes)

- `context/changes/project-and-pattern-display/plan.md:47,50` — S-01 explicitly deferred HTMX and row-marking to S-02.
- `context/changes/project-and-pattern-display/reviews/impl-review-phase-3.md:29` (F1) — restates and enforces the commit-before-redirect convention for a new route; directly applicable precedent for row-marking-and-persistence's redirect (if any).
- `context/foundation/test-plan.md:46,65,83` — Risk #1 in the QA risk map is precisely this feature ("Row-mark write silently fails — HTMX POST returns an error, UI updates, DB doesn't"); Phase 2 of the rollout (`testing-write-path-ownership`) already anticipates testing this endpoint once it exists.
- `context/changes/testing-write-path-ownership/research.md:25,45,61-81,291,316` — confirms the row-mark endpoint doesn't exist yet, is explicitly deferred, and lays out what the sibling agent's test-plan phase expects once it ships (verify both HTTP response fragment and DB state on a POST, especially non-2xx).

## Related Research

- `context/changes/project-and-pattern-display/research.md` — prior slice's research; HTMX deferral discussion (§5 HTMX Status).
- `context/changes/testing-write-path-ownership/research.md` — sibling in-flight change (different worktree) anticipating this endpoint's test coverage; do not touch that worktree, but its expectations (fragment + DB state assertions on POST) are useful signal for this plan's own test additions.

## Open Questions

1. **Cycling order for the 3 states**: FR-006 says states are "toggleable" but does not specify an explicit cycle order. `/10x-plan` must pick one (e.g. not_started → in_progress → done → not_started) and state it explicitly — this is not specified anywhere in the PRD or roadmap.
2. **"First unmarked row" semantics for auto-jump (FR-007)**: does "unmarked" mean `state != done` (so an `in_progress` row is where you land) or `state == not_started` strictly (so an in-progress row is skipped over, landing on the next fully-untouched row)? PRD FR-007 text just says "first unmarked row" — the plan must resolve this ambiguity explicitly; it directly affects US-01's flow ("returns the next day, and finds it still marked, with the view auto-jumping to the first unmarked row").
3. **HTMX endpoint shape**: full resource route (e.g. `POST /projects/{project_id}/elements/{element_id}/rows/{row_id}/state`) returning an HTML fragment (200) vs a redirect back to `element_detail` (303, full-page). Given the 100ms NFR, an HTMX-swapped fragment avoids a full-page round-trip; the plan should pick this explicitly, and if it returns a fragment rather than a redirect, decide whether the commit-before-return discipline still applies (this research recommends yes, defensively, per §1 above).
4. **Live-sync error UX** (roadmap Open Question 1, PRD Open Question 1) — explicitly owned by the user, not blocking for S-02 planning, but the plan should at minimum decide what HTTP status / fragment content a failed row-mark returns, even if the visual treatment (toast/banner/modal) is deferred.
5. **No-JS fallback**: since this is the first JS/HTMX introduced in the codebase, does the row-mark control still work via a plain `<form method="post">` submit if JavaScript is disabled (progressive enhancement), or is HTMX assumed to be always present? Not specified by PRD/roadmap; a plan decision.
