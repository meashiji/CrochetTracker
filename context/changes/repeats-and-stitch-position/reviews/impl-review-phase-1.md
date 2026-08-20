<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Repeats + stitch position (S-03)

- **Plan**: context/changes/repeats-and-stitch-position/plan.md
- **Scope**: Phase 1 of 2
- **Date**: 2026-08-18
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 1 warning, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Stepper increase race / double-click can 500 and break the reps invariant

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (Reliability)
- **Location**: app/routes/projects.py:770-786, app/models/project.py:40, app/templates/projects/element_detail.html:325-329
- **Detail**: The `+` stepper button is an unguarded `type="submit"` (no confirm, no disable-on-submit). A double-click fires two concurrent POSTs; both read the stale `element.repeat_count` before either commits, and both insert the same `repetition_number`, violating `UniqueConstraint(element_id, repetition_number)` → unhandled `IntegrityError` → 500. An increase-vs-decrease race can leave reps present while the field is lower, and a later increase re-inserts the orphaned number → another 500. No data loss, but a realistic 500 and a recoverable invariant break. The `−` form at least has a confirm; the `+` form has nothing.
- **Fix A ⭐ Recommended**: Guard the `+` button (disable on submit, e.g. `hx-disable-elt` or JS) AND derive the new-rep range from the freshly fetched `existing_reps` max (not the field) AND handle `IntegrityError` with rollback + redirect so a duplicate seed degrades gracefully.
  - Strength: Removes the 500 class and protects the reps-match-`repeat_count` invariant at the source; covers non-UI callers too.
  - Tradeoff: More code in the stepper route; slightly less "plain field update" simplicity.
  - Confidence: HIGH — the failure mode is concrete (unique constraint + double-submit).
  - Blind spot: Race not reproduced in a test; reasoned from constraint + timing.
- **Fix B**: Frontend-only button guard, no route change.
  - Strength: Minimal; fixes the realistic double-click trigger.
  - Tradeoff: Race remains possible from any non-UI caller; invariant stays unprotected server-side.
  - Confidence: MED — stops the common trigger, not the class.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A (derive seed range from existing reps max + IntegrityError rollback + redirect; disable-on-submit on both stepper buttons; regression test `test_stepper_increase_skips_existing_rep_numbers`)

### F2 — last_rep_* cookie set without samesite/secure flags

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (Security)
- **Location**: app/routes/projects.py:542-544
- **Detail**: `response.set_cookie(f"last_rep_{element.id}", ..., max_age=31_536_000)` sets only `max_age`; the session cookie uses `same_site="lax", https_only=True` (app/main.py). The value is a non-sensitive 1..99 int, so impact is minimal, but the flag posture should match the rest of the app.
- **Fix**: Add `samesite="lax"` to the `set_cookie` call to match the session-cookie posture.
- **Decision**: FIXED (added `samesite="lax"` to the `last_rep_*` set_cookie)

### F3 — Stepper increase can be unbounded on pathological patterns

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (Performance)
- **Location**: app/routes/projects.py:770-786
- **Detail**: A 1→99 increase on a ~25k-row pattern inserts ~2.5M `RowState` rows in one transaction/commit. Bounded by the 99 cap and `MAX_PATTERN_LENGTH`, and self-inflicted (owner's own data), so not worth engineering for now.
- **Fix**: No action now — accept as a documented bound; revisit only if pathological patterns appear in real use.
- **Decision**: FIXED differently — chunked flush (`ROW_STATE_SEED_CHUNK = 10_000`) so a 1→99 increase on a huge pattern never materializes the whole reps×rows product in one unit of work; `await session.flush()` per chunk