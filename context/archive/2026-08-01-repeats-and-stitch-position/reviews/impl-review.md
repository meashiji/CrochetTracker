<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Repeats + stitch position (S-03)

- **Plan**: context/changes/repeats-and-stitch-position/plan.md
- **Scope**: Phase 1 and 2 of 2 (full plan)
- **Date**: 2026-08-20
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical | 2 warnings | 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — Stitch route crashes with 500 on Unicode superscript digits

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:953
- **Detail**: `value.isdigit()` accepts superscript/subscript Unicode digits (`"¹".isdigit()` is `True`) but `int("¹")` raises `ValueError` — unhandled → 500. A user pasting `²` into the stitch box (HTMX posts regardless of the `pattern="[0-9]*"` browser hint) triggers it. The parametrized test covers `"abc"`/`"0"`/`"10000"` but not this class.
- **Fix**: Parse once with `try: value_int = int(value) except ValueError:` (which also drops the double `int()`), then range-check. Blank handled before parsing.
- **Decision**: FIXED — isascii() guard + regression case (¹) in test_row_state_routes.py

### F2 — Chunked RowState seeding does not bound session memory

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:796-815
- **Detail**: The chunked flush bounds each SQL batch but not the session identity map — every seeded `RowState` object is retained until `commit()`, so the full reps×rows product still materializes in memory. At `MAX_PATTERN_LENGTH` (~25k rows) × a 1→99 increase that's ~2.4M ORM instances held simultaneously — a real OOM risk for the pathological case the chunk constant claims to defend. The comment's claim ("never materializes … as one unbounded unit of work") is only true for the INSERT, not the object graph. Mitigated in practice by the 99-rep cap and the project's stated small scale, but the guarantee is overstated.
- **Fix**: Bulk insert the seeds (`await session.execute(insert(RowState), [...])`) to bypass the identity map, or reject a step whose reps×rows product exceeds a bound.
- **Decision**: FIXED via Fix A — bulk Core insert; ROW_STATE_SEED_CHUNK removed; updated_at default verified in test

### F3 — Plan drift: stitch input is type="text", plan still says type="number"

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: app/templates/projects/_row.html:16; plan.md:181
- **Detail**: The Phase 2 contract specified `type="number" min="1" max="9999"`; the implementation uses `type="text" inputmode="numeric" pattern="[0-9]*"`. Deliberate and user-validated: `type="number"` blocks non-numeric typing, making the invalid-input error path unreachable. Intent is preserved — the route still enforces digits 1–9999. The plan was never updated. Also, the required `name="stitch_position"` attribute (a correctness fix — HTMX only serializes named fields) is absent from the plan's snippet.
- **Fix**: Update the plan's Phase 2 item 3 contract to reflect the actual input attributes and the `name` requirement.
- **Decision**: FIXED — plan Phase 2 item 3 contract updated to reflect type=text + name attribute

### F4 — `scalar_one()` raises 500 instead of 404 when a state row is missing

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:882, 932
- **Detail**: The toggle and stitch routes use `result.scalar_one()`, which raises `NoResultFound` → 500 if the `(rep, row)` state row is missing (possible under a concurrent pattern-save or stepper-decrease that deletes the rep mid-flight). The sibling helper `_get_element_repetition_by_number` (projects.py:135) uses `scalar_one_or_none()` → 404, matching the app's "bad pairing = 404, never 500" convention.
- **Fix**: Switch both to `scalar_one_or_none()` + `HTTPException(404)`.
- **Decision**: FIXED — both routes now scalar_one_or_none() + 404

### F5 — last-viewed-rep cookie has weaker posture than the session cookie

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/routes/projects.py:550-555
- **Detail**: `last_rep_{element.id}` is set with only `samesite="lax"` — no `secure`, no `httponly` — while the session cookie uses `https_only=True` (app/main.py:23-25). Also the cookie key is not user-namespaced, so two accounts sharing one browser inherit each other's last-viewed rep. Impact is view-state only.
- **Fix**: Add `secure=True` and `httponly=True` to `set_cookie`; consider user-scoping the key.
- **Decision**: FIXED — secure=True, httponly=True added to last_rep_* cookie

### F6 — `project_create` redirects without an explicit commit (pre-existing)

- **Severity**: 👁 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Pattern Consistency
- **Location**: app/routes/projects.py:368-374
- **Detail**: `project_create` flushes (for the element PK) then redirects with no commit, while `get_session` commits only after the handler returns (app/db.py:20). The browser's follow-up GET to `/projects/{id}` can race that teardown commit and 404 a freshly created project. Every other mutation route in the file commits before redirect for exactly this reason (see `element_create:494` and the comment at projects.py:736-737). Pre-existing, outside the change's direct scope, but found in the reviewed file.
- **Fix**: Add `await session.commit()` before the redirect, matching `element_create`.
- **Decision**: FIXED — await session.commit() before project_create redirect

### F7 — Fragment route names are nouns; no docstrings

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: app/routes/projects.py:745, 907
- **Detail**: `element_repeat_count` and `row_stitch_position` are noun-phrases while every sibling mutation route uses `element_<verb>` (`element_rename`, `element_delete`, `element_save_pattern`, `row_state_toggle`). The two fragment-returning routes also lack docstrings, unlike the rest of the module.
- **Fix**: Rename to `element_update_repeat_count` / `row_update_stitch_position`; add one-line docstrings.
- **Decision**: FIXED — renamed to element_update_repeat_count / row_update_stitch_position + docstrings