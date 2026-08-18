# Repeats + stitch position (S-03) — Plan Brief

> Full plan: `context/changes/repeats-and-stitch-position/plan.md`

## What & Why

Ships FR-003 (repeat count on an element, each repetition tracked with its own row progress) and FR-010 (record stitch position within an in-progress row) — the last two must-have tracking requirements. Crochet patterns are written as repeats (×2 sleeves, ×4 squares), and mid-row stops need a stitch number, not just a row state.

## Starting Point

S-02 shipped working row-state toggling (3 states, HTMX fragment swap, auto-jump, persistence) with a hard-coded `repeat_count=1` and single-repetition assumptions baked into helpers, routes, and templates. The F-01 schema already has everything S-03 needs — `Element.repeat_count`, `ElementRepetition`, `RowState.stitch_position` — so no migration is required.

## Desired End State

User sets ×3 via an inline stepper on the element page, gets "Rep 1 | Rep 2 | Rep 3" pills, and tracks each repetition's rows independently. Reopening the element lands on the last-viewed rep (per-device cookie), jumped to its first non-done row. On any in-progress row, an inline stitch input saves "stopped at stitch 14" instantly and keeps it across reloads and state cycles.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Repeat-count UI | Inline −/+ stepper on element detail | Co-located with the element; matches the inline-rename interaction | Plan (user) |
| Rep display | Pills, one rep at a time, `?rep=N` in URL | Page stays compact; bookmarkable; matches "working on sleeve 2" mental model | Plan (user) |
| Decreasing count | Allowed, JS confirm, deletes top reps' progress | Matches the existing pattern-re-save destructive precedent | Plan (user) |
| Auto-jump target | Last-viewed rep (cookie), jump within it | Respects parallel working styles; user overrode the first-unfinished-rep recommendation | Plan (user) |
| Cookie vs DB for last rep | Per-element cookie, clamped on read | View state, not project data — avoids a migration; per-device is acceptable | Plan |
| Stitch input UX | Inline number input on in_progress rows only, HTMX save on change | Co-located with the row; visible exactly when relevant | Plan (user) |
| Stitch lifecycle | Kept in DB across state cycles; displayed only in_progress | Survives accidental toggles; user chose over clear-on-leave | Plan (user) |
| Schema changes | None | F-01 over-built the schema for exactly this slice | Research |

## Scope

**In scope:** repeat-count stepper (route + UI) with seed/delete of reps and row-states; rep-scoped toggle route and helpers (`/reps/{n}/` in path); rep pills + last-viewed cookie; per-rep auto-jump; stitch route + inline input; test updates to rep-scoped URLs.

**Out of scope:** any migration; cross-device last-rep sync; per-rep breakdown on project detail; repeat_count on the create form; stitch display on non-in-progress rows; HTMX for pills/stepper; route-level stitch state guards.

## Architecture / Approach

Phase 1 re-scopes every row-state code path from "the element's one rep" to "rep number N": a by-number rep lookup, a request-scoped rep resolver (query param → cookie → 1), the stepper route maintaining the reps-match-`repeat_count` invariant, and pill navigation. Phase 2 widens `_build_row_states` to carry full `RowState` objects (state + stitch_position) and adds the stitch route + inline input — purely additive on Phase 1.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Repeat count + per-rep tracking | FR-003: stepper, rep pills, rep-scoped routes, cookie, auto-jump | Breaking S-02's single-rep assumptions — mitigated by updating S-02 tests to `/reps/1/` URLs |
| 2. Stitch position | FR-010: stitch route + inline input on in_progress rows | Nested-interactive markup in the row `<li>` — input stays a sibling of the button |

**Prerequisites:** S-02 done and archived (✓); test DB conventions in place.
**Estimated effort:** ~2 sessions across 2 phases.

## Open Risks & Assumptions

- The reps-match-`repeat_count`-when-rows-exist invariant holds because all rep creation/deletion flows through pattern save or the stepper — any future third writer must maintain it.
- Per-device (cookie) last-viewed rep means phone and laptop can open on different reps; accepted as view state, not project data.

## Success Criteria (Summary)

- ×N elements show N independently tracked repetitions; marks in one rep never affect another.
- Reopening an element lands on the last-viewed rep, scrolled to its first non-done row.
- A stitch number entered on an in-progress row persists across reloads and state cycles.
