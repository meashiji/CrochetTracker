# Sequential Row & Repeat Progress — Plan Brief

> Full plan: `context/changes/sequential-progress/plan.md`
> Frame brief: `context/changes/sequential-progress/frame.md`

## What & Why

In crochet, rows are worked in order — you can't do row 5 before row 1, and you
can't complete rep 2 while rep 1 still has work. Today the app lets any row in any
rep be marked `done` independently. This change enforces ordering: a row can advance
toward `done` only when the previous row (in the same rep) and the previous
repetition are done. Reverts always stay free.

## Starting Point

The row toggle (`row_state_toggle`) blindly cycles `not_started → in_progress →
done → not_started` with no predecessor or prior-rep check. Rows are ordered by
`position`; reps are numbered and seeded independently. There is no disabled/locked
row state in the UI, and no rep-completeness concept.

## Desired End State

A user can only push progress forward in crochet order: within a rep you unlock rows
sequentially, and across reps you unlock rep N only after rep N-1 is fully done.
Locked rows/pills are visually distinct; you can always revert anything (even an
orphaned `done` row); opening an element auto-lands on the first incomplete rep.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Advance gate (rows) | Row N advances only when row N-1 is `done` | Mirrors physical crochet ordering | Frame |
| Advance gate (reps) | Rep N writes unlock when rep N-1 fully `done` | You can't start a repeat before finishing the previous | Frame |
| Revert policy | `done → not_started` always allowed | User can fix mistakes; no deadlock | Frame |
| Cascade | None — reverting leaves later rows' state alone | Keep it simple; user cleans up manually | Frame |
| Locked row UI | Dimmed inactive button (only for blocked advances) | Clear, and `done` rows stay revertable | Plan |
| Rep lock UI | Lock glyph + dimmed pill, still clickable to view | Write-block only; viewing stays free | Plan |
| Auto-entry | Bare-open lands on first not-fully-done rep | Drops you where the work is | Plan |

## Scope

**In scope:** server-side advance gating (rows + reps), locked row rendering, rep-pill
lock, auto-navigate to first incomplete rep, updated tests.

**Out of scope:** schema/migration changes, cascade on revert, blocking rep/row
viewing, changes to stitch position or the repeat-count stepper.

## Architecture / Approach

Pure server-side logic plus template/CSS changes — no data-model change. A small
helper computes "is a rep fully done"; the toggle endpoint intercepts only advance
transitions (reverts pass). Render passes per-row locked flags and per-rep
completeness to the templates, which show disabled rows and locked pills. Auto-jump
re-pins the cookie to the first incomplete rep on a bare open.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Gate logic (server) | Blocked advances rejected; revert free; tests | Getting the gating contract exactly right |
| 2. UI row lock | Locked rows dimmed/inactive + CSS | Keeping `done` rows revertable (not locked) |
| 3. Rep lock + auto-jump | Pill locks + auto-land on first incomplete rep | Not overriding explicit `?rep=` |

**Prerequisites:** Element/rep/row model already in place; no migration.
**Estimated effort:** ~3 short phases; mostly tests + two templates + one route.

## Open Risks & Assumptions

- Existing orphaned `done` rows (created before this rule) are accepted as-is; no
  cascade/backfill.
- "Fully done" for a rep means every row's `RowState` is `done`; an element with no
  rows is trivially complete (never blocks).

## Success Criteria (Summary)

- You can't advance a row past an incomplete predecessor, or a rep past an
  incomplete previous rep.
- You can always revert any row, even an orphaned `done`.
- Locked rows and reps are visually clear, but reps still open for viewing.
- Bare-open lands on the first rep you need to work on; explicit `?rep=` still works.
