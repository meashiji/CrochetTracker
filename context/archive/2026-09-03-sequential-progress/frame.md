# Frame Brief: Sequential row & repeat progress

> Framing step before /10x-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed.

## Reported Observation

In rep 1 the user can mark both row 1 and row 5 as `done` independently. In crochet,
rows are worked in order — you cannot do row 5 before row 1 — and the same applies
across repetitions: you cannot mark work done in rep 2 while rep 1 still has work
left. The app currently has no ordering constraint on row/repeat state.

## Initial Framing (preserved)

- **User's stated cause or approach**: The row/repeat model is too permissive — it
  allows non-sequential completion that contradicts how crochet actually works.
- **User's proposed direction**: Add a rule so a row can only be completed once all
  prior rows (in that repetition) are done, and a repetition's work can only be
  completed once the prior repetition is done.
- **Pre-dispatch narrowing**: User picked "Blokada wszelkiego postępu" for rows
  (row N can't be advanced to *any* state until row N-1 is done), "Bez kaskady"
  for reverts (reverting a middle row leaves later rows untouched), "Blokada zapisu
  tylko" for reps (rep navigation stays free; only writes are blocked until the
  prior rep is done), and "Cofanie zawsze wolne" (a row can always be reverted
  done→not_started even if its predecessor isn't done).

## Dimension Map

The observation could originate at any of these dimensions:

1. **[Toggle/advance rule]** — the state-transition allows any forward move with no
   predecessor check.  ← user's framing
2. **[Rep boundary gate]** — no rule links rep N completion to rep N+1 access.
3. **[Revert / orphan handling]** — what happens when a middle row is un-marked and
   later rows become orphaned `done`.
4. **[UI affordance]** — how "blocked" is communicated so the user isn't confused
   when a row/repeat won't change.

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| Forward advance is unconstrained | `app/routes/projects.py:920` does `row_state.state = ROW_STATE_CYCLE[...]` with no predecessor check; `ROW_STATE_CYCLE:23` blindly cycles not_started→in_progress→done→not_started. Tests `test_row_state_routes.py` mark any row any way (e.g. `test_per_rep_toggle_isolation` toggles row 1 of rep 2 freely). | STRONG |
| No rep-boundary gate in write path | `row_state_toggle` (`projects.py:896`) only loads the target repetition; it never checks whether the previous repetition is fully `done`. Reps are seeded independently (`_resolve_requested_rep`, repeat-count stepper). | STRONG |
| Revert semantics undefined for orphans | No cascade logic anywhere; toggle is a pure per-row cycle. | WEAK (absent = no behavior today) |
| UI has no "blocked" state | Rows render as `row-item--{state}`; no disabled/locked variant exists. | STRONG (absent feature) |

## Narrowing Signals

- Row ordering is by `Row.position` asc (`projects.py:513-516`); `_first_unmarked_row_id`
  (`projects.py:197`) already walks rows in order — a natural hook.
- `RowState` rows exist per (rep, row); the predecessor/`done` check and rep-completion
  check are both cheap queries from the existing `repetition` handle.
- User explicitly confirmed: advance gated, revert always allowed, no cascade, reps
  write-block only.

## Cross-System Convention

Crochet progress is strictly sequential by construction — the state model's "advance"
direction must follow `Row.position` order within a repetition, and repetitions must
unlock in `repetition_number` order. The product already presents rows in order and
auto-jumps to the first non-`done` row, which is consistent with a locked-forward model.

## Reframed (or Confirmed) Problem Statement

> **The actual problem to plan around is**: the row/repeat state model allows forward
> progress out of crochet order — a row may advance (not_started→in_progress→done)
> even when an earlier row in the same repetition isn't done, and a repetition may
> be advanced even when the previous repetition isn't fully done.

The fix is a forward-advance gate, not a data-model change: only *advances* are
constrained (by `Row.position` within a rep, and by prior-rep completion across reps);
reverts (done→not_started) stay always allowed; there is no cascade (later rows keep
their state, even if orphaned). The UI needs a visible "locked" affordance so a
blocked advance is explained rather than a silent no-op.

## Confidence

- **HIGH** — the write path is unconstrained (confirmed in code), and the user has
  settled the two edge cases (revert-always-allowed, no cascade, rep write-block
  only) directly.

## What Changes for /10x-plan

The plan should implement a forward-advance gate in the row-state toggle (and any
other advance path): block the not_started→in_progress and in_progress→done
transitions when the predecessor row in the same rep isn't `done` (for rows), or
when the previous repetition isn't fully `done` (for rep N>1 advances). Revert
(done→not_started) stays unblocked. Add a visible locked/unavailable UI state; no
cascade. Existing tests that assume free any-row toggling will need adjusting.

## References

- Source files: `app/routes/projects.py:23` (cycle), `:896` (toggle), `:513` (order),
  `:197` (`_first_unmarked_row_id`); `app/models/progress.py:14` (`RowState`);
  `app/models/pattern.py:5` (`Row`); `tests/test_row_state_routes.py`
  (e.g. `test_per_rep_toggle_isolation:463`)
- Related research: none yet
