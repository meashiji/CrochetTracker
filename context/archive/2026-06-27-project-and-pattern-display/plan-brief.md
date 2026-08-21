# S-01: Project Creation + Pattern Display — Plan Brief

> Full plan: `context/changes/project-and-pattern-display/plan.md`
> Research: `context/changes/project-and-pattern-display/research.md`

## What & Why

S-01 is the first user-visible slice — it turns the auth shell into a working app. Users need to create projects, paste crochet patterns, and see them as a row list so they know what they're tracking. Without this slice, the app is just a login screen.

## Starting Point

All DB tables are in place (Project, Element, Row, RowState) with no migrations needed. Auth is fully wired — `get_current_user`, `get_session`, and `AuthRedirectMiddleware` all exist and protect routes automatically. The app currently has no project routes, no project templates, and no pattern logic.

## Desired End State

A logged-in user can create a project, paste a plain-text crochet pattern into its auto-created element, and see the pattern displayed as a numbered row list with a grey dot beside each row. They can add more named elements to a project and switch between projects via a project list. Row + ElementRepetition + RowState records are eagerly initialised at paste time, so S-02 (marking) can build on top without any schema work.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Default element on project create | Auto-create one unnamed Element | FR-002 specifies it; avoids setup friction for simple projects | Plan |
| Multi-element support | Yes, add-element form on detail page | Matches FR-002 + PRD secondary success criterion | Plan |
| Pattern re-paste | Warn inline then replace | Silent replace risks losing S-02 progress; warn banner is honest without a modal | Plan |
| Row display style | Grey dot (neutral) next to each row | Proves RowState wiring end-to-end; S-02 makes it interactive | Plan |
| Slider (FR-005) | No — scrollable list only | No "current position" exists until S-02; slider without an anchor is useless | Plan |
| URL structure | REST sub-resource (`/projects/{id}/elements/{eid}`) | Deep-linkable, bookmarkable, follows established auth route convention | Plan |
| HTMX | No HTMX in S-01 | Full-page form submits are sufficient; HTMX adds value in S-02 for row marking | Plan |
| RowState initialisation | Eager at paste time | Assigned to S-01 in db-schema-and-models plan; S-02 reads, never writes schema | Research |

## Scope

**In scope:**
- `GET/POST /projects/` — project list + create
- `GET /projects/{id}` — project detail (elements + row counts)
- `GET/POST /projects/{id}/elements/new` — add element
- `GET/POST /projects/{id}/elements/{eid}` — element detail + pattern paste
- Pattern parser service (`app/services/pattern.py`)
- Eager Row + ElementRepetition + RowState creation on paste
- Inline warning on re-paste (if rows exist)
- Ownership 404 enforcement on all project/element routes
- Index page link to `/projects/`

**Out of scope:**
- New migrations (none needed)
- HTMX
- Pattern boundary editor
- Row marking / state toggling (S-02)
- Repeat-count UI (S-03)
- Stitch position (S-03)
- FR-005 slider
- FR-007 auto-scroll to first unmarked row (S-02)

## Architecture / Approach

New file `app/routes/projects.py` with `APIRouter(prefix="/projects")`. Registered in `app/main.py` alongside the existing auth router. New `app/services/pattern.py` holds the `parse_pattern(text)` function. Five new templates under `app/templates/projects/`. All routes use `Depends(get_current_user)` + `Depends(get_session)` exactly as auth routes do. Re-paste deletes RowStates → Rows → ElementRepetitions in that order (FK constraint) then re-inserts within one transaction.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Project CRUD + auto-element | Project list, create form, index link; router wired | None — straightforward CRUD |
| 2. Pattern paste + parsing | Pattern form, parser service, Row+RowState eager init, re-paste warning | Deletion order (RowStates must go before Rows) |
| 3. Project detail + add element | Project detail page, add-element form | Ownership check must be consistent across all routes |

**Prerequisites:** F-01 (schema) ✓ done, F-02 (auth) ✓ done
**Estimated effort:** ~2 sessions across 3 phases

## Open Risks & Assumptions

- `updated_at` on Project/Element is not auto-managed by SQLAlchemy's `onupdate` — must be set explicitly on every mutation.
- Bulk RowState insert for long patterns (200+ rows) uses ORM adds, which is fine for MVP scale but worth noting as a future optimisation boundary.
- No test infrastructure exists yet — Phase 1/2/3 rely on manual verification + one `parse_pattern` unit test.

## Success Criteria (Summary)

- User can create a project, paste a pattern, and see numbered rows with grey dots — all in one session with no manual save.
- Re-pasting a pattern shows a warning and correctly replaces all rows.
- Accessing another user's project returns 404, not data.
