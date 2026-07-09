# Row marking + persistence (S-02, north star) — Plan Brief

> Full plan: `context/changes/row-marking-and-persistence/plan.md`
> Research: `context/changes/row-marking-and-persistence/research.md`

## What & Why

Implements the smallest end-to-end flow that proves CrochetTracker's product hypothesis: a user marks a row through three states (not started / in-progress / done), the mark persists with no manual save, and reopening the pattern jumps straight to the first unmarked row. This is roadmap slice S-02, deliberately sequenced first among slices because it *is* the product hypothesis (FR-006, FR-007, US-01).

## Starting Point

`RowState` and `ElementRepetition` already exist from F-01 with every field this needs (`state`, `stitch_position` — unused here). S-01 shipped project/element creation and pattern-paste, and already pre-seeds every row's `RowState` at `not_started`. Today rows render as a static, non-interactive list — no row is clickable, no state is shown, and the codebase has zero client-side JS anywhere.

## Desired End State

Tapping a row cycles its state and the change sticks — close the tab, come back tomorrow, and the exact same marks are there, with the page having scrolled straight to the first row you haven't finished.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| HTMX or plain forms? | **Introduce HTMX**, but only in Phase 3, layered on top of a working plain-form version from Phase 1 | `tech-stack.md` already commits this project to HTMX for exactly this NFR; S-01 explicitly deferred it here rather than debating it — this plan executes a decision already on record | Research |
| Where does HTMX come from? | Vendor a pinned `htmx.min.js` (2.0.4) into `app/static/js/`, no CDN | A CDN round-trip sits directly on the 100ms-critical path and adds a runtime dependency this self-contained Docker/Fly.io deploy doesn't otherwise have | Plan |
| Cycling order (FR-006 doesn't specify one) | `not_started → in_progress → done → not_started` | Matches the natural progression already implied by the UI ("grey dot" → partial → complete) | Plan |
| "First unmarked row" semantics (FR-007 ambiguous) | First row whose state is **not `done`** (so an in-progress row is where you land, not skipped) | Matches PRD's Business Logic section: "the first unmarked row and the last known stitch position" describes *where to continue*, not strictly untouched rows | Plan |
| No-JS fallback for the toggle control | **None** — Phase 3 fully replaces Phase 1's plain-form mechanism | PRD's Access Control section already assumes a live, connected, JS-capable client ("every interaction reaches the server live"); building a parallel fallback path is pure scope creep | Plan |
| Live-sync error UX (toast/banner/modal) | Deferred — this plan only guarantees a visible, non-silent failure indicator (a CSS error class on the row) | PRD Open Question 1 is explicitly user-owned and non-blocking; a minimal signal satisfies the "never silently lose a mark" guardrail without pre-empting the user's design call | Plan / Roadmap |
| Repeat handling | Treat state as 1:1 with `Row` (via the element's single, always-exactly-one `ElementRepetition`) | Every element is created with `repeat_count=1` today with no way to change it — multi-repetition UI is explicitly S-03's job | Research |

## Scope

**In scope:**
- POST route to cycle a row's `RowState.state` through the 3-state cycle, ownership-checked.
- `element_detail` GET updated to show each row's current state and compute the auto-jump target.
- Auto-scroll/highlight to the first non-done row on page load.
- HTMX fragment swap for the toggle, replacing the interim full-reload mechanism.
- Minimal visible failure indicator on a failed toggle request.
- Integration tests mirroring existing `tests/test_project_routes.py` conventions.

**Out of scope:**
- `stitch_position` recording (FR-010, S-03), repeat-count editing (FR-003, S-03).
- Final error-UX design (toast/banner/modal — Open Question 1).
- Project-list-level progress summaries, Tailwind adoption (P-01), CSRF protection.
- Live re-jump within an already-open session (auto-jump is a page-load-time computation only).

## Architecture / Approach

Three phases, each independently shippable: Phase 1 proves persistence works at all (plain form, full reload — satisfies FR-006's data layer). Phase 2 adds the auto-jump computation and scroll behavior on top (FR-007), independent of transport. Phase 3 swaps the transport to an HTMX fragment response to hit the 100ms NFR, and updates Phase 1's now-stale redirect-based tests accordingly. A single reusable Jinja partial (`_row.html`) renders a row identically whether it's part of the full page or an HTMX-swapped fragment, so the two render paths can't drift.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Row-state toggle + persistence | Working 3-state marking, full-page reload | Slower than the NFR target — acceptable as an interim step |
| 2. Auto-jump on open | View lands on the first unmarked row on reopen | Ambiguity in "first unmarked" semantics — resolved explicitly above |
| 3. HTMX fragment swap | Near-instant tap-to-update, meets 100ms NFR; visible failure signal | First JS ever shipped in this codebase; Phase 1's tests need updating for the new response shape |

**Prerequisites:** S-01 (project-and-pattern-display) done — confirmed, no schema change needed.
**Estimated effort:** ~3 sessions, one per phase.

## Open Risks & Assumptions

- Assumes `repeat_count` stays at 1 through S-02's lifetime (true today, verified by grep — no route changes it). If S-03 ships repeat-count editing before this assumption is revisited, the single-repetition query in this plan will need updating.
- The final error-UX treatment (toast/banner/modal) is explicitly deferred to the user (Open Question 1) — Phase 3 ships only a minimal CSS-class error signal, not the final design.
- HTMX 2.0.4 is specified as the vendored version; if unavailable at implementation time, the nearest current 2.x stable release should be substituted with the same vendoring approach.

## Success Criteria (Summary)

- A user can tap a row through all three states and see it persist across a page reload.
- Reopening an element with mixed row states scrolls to the first non-done row.
- A tap-to-update feels near-instant (no full-page flash) and a failed write never looks like it silently succeeded.
