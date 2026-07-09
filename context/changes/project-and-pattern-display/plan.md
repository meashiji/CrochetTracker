# S-01: Project Creation + Pattern Display — Implementation Plan

## Overview

Implement the first user-facing slice: a user can create a project, see it in a project list, add named elements, paste a plain-text crochet pattern, and view the pattern as a scrollable numbered list of rows. Each row gets a neutral grey-dot state indicator (RowState records are eagerly initialised to `not_started` at paste time, ready for S-02's marking UI).

## Current State Analysis

- Schema is fully ready — Project, Element, ElementRepetition, Row, RowState models and all migrations are in place. No new migrations needed.
- Auth is fully in place — `get_current_user`, `get_session`, `AuthRedirectMiddleware` all established. All `/projects/*` routes are automatically protected; no middleware changes needed.
- No project routes, templates, or services exist yet.
- `app/main.py` has a minimal `GET /` index page; it needs a link to `/projects/`.
- Established conventions from auth-scaffold: `APIRouter(prefix="...")`, `Jinja2Templates(directory="app/templates")`, `TemplateResponse(request, "path.html", {"user": user})`, `RedirectResponse(url="...", status_code=303)`, `{"error": "..."}` for inline errors.

### Key Discoveries

- `app/models/project.py:7-21` — Project: `id`, `user_id` (FK→user, indexed), `name`, `created_at`, `updated_at`
- `app/models/project.py:24-35` — Element: `id`, `project_id`, `name` (nullable), `pattern_text` (nullable), `repeat_count` (int, ge=1, default=1)
- `app/models/project.py:38-44` — ElementRepetition: `id`, `element_id`, `repetition_number`; UNIQUE(element_id, repetition_number)
- `app/models/pattern.py:5-12` — Row: `id`, `element_id`, `position` (1-based), `content`; UNIQUE(element_id, position)
- `app/models/progress.py:8-27` — RowStateEnum (`not_started`, `in_progress`, `done`), RowState: `element_repetition_id` + `row_id` + `state` + `stitch_position` + `updated_at`; UNIQUE(element_repetition_id, row_id)
- `app/auth/dependencies.py:8-15` — `get_current_user` returns User with `.id`, `.email`
- `app/db.py:16-23` — `get_session` is an AsyncSession async generator; auto-commits on success

## Desired End State

A logged-in user can:
1. Navigate to `/projects/` and see their projects list.
2. Create a new project (name only) — auto-creates an unnamed default element.
3. Open the project detail (`/projects/{id}`) and see a list of its elements.
4. Open an element detail (`/projects/{id}/elements/{eid}`) and paste a plain-text crochet pattern.
5. After saving, see the pattern displayed as a numbered row list with a grey dot next to each row.
6. Re-paste / edit the pattern — a warning is shown ("saving will reset row progress"); saving replaces all rows.
7. Add additional named elements to a project.
8. Switch between projects via the project list.

### Key Discoveries (verification targets)

- `GET /projects/` returns the user's project list (scoped by `user_id`).
- `POST /projects/new` creates a Project + one unnamed Element in one transaction.
- `POST /projects/{id}/elements/{eid}` (save pattern) creates N Rows + M ElementRepetitions + N×M RowStates in one transaction.
- Ownership is enforced: accessing another user's project or element returns 404.

## What We're NOT Doing

- No new Alembic migrations (schema already exists).
- No HTMX — all interactions are full-page form submits.
- No FR-005 slider (no "current position" until S-02).
- No FR-007 auto-scroll to first unmarked row (S-02).
- No row marking or state toggling (S-02).
- No repeat-count UI (S-03).
- No stitch position (S-03).
- No pattern boundary editor (roadmap open question, deferred).
- No changing `_PUBLIC_PATHS` in middleware — project routes are auto-protected.

## Implementation Approach

Three phases in dependency order:

1. **Project CRUD + auto-element** — router file, main.py wiring, project list + create form. No pattern logic yet.
2. **Element detail + pattern parsing** — pattern paste form, parser service, eager RowState initialisation, re-paste warning.
3. **Project detail + add element** — project detail page showing elements, add-element form.

Each phase ends with a working, deployable state. Phases 1 and 3 can be done quickly; Phase 2 contains the bulk of the DB work.

## Critical Implementation Details

**Ownership check pattern**: When loading a project or element, always verify `project.user_id == user.id`. Return 404 (not 403) to avoid leaking existence — `raise HTTPException(status_code=404)`. Load the project first, check ownership, then load child resources.

**Re-parse deletion order**: SQLAlchemy will reject deleting Rows or ElementRepetitions if their RowState children exist (FK constraint, no cascade defined). Always delete in this order: RowStates → Rows + ElementRepetitions (can run in parallel, both reference element only). Use `delete(Model).where(...)` bulk-delete statements inside the same transaction as the re-insert.

**`updated_at` must be set explicitly in the save-pattern handler**: `Project.updated_at` has `onupdate` wired — it fires automatically when SQLAlchemy emits an UPDATE for the project row. But in the save-pattern handler, no Project field is mutated, so SQLAlchemy never emits that UPDATE and `onupdate` never fires. Fix: explicitly set `project.updated_at = datetime.now(timezone.utc)` and call `session.add(project)` — this makes SQLAlchemy detect a change and emit the UPDATE, carrying `updated_at` along with it.

**Eager RowState init volume**: For a 200-row pattern with `repeat_count=1`, this inserts 200 RowState rows in one transaction. This is fine at target scale (small data volume per PRD), but the bulk-delete + re-insert loop should use SQLAlchemy Core `insert()` rather than per-object ORM adds if the pattern is long. For S-01, ORM adds are acceptable; note the boundary for future optimisation if patterns grow.

---

## Phase 1: Project Routes + Auto-Element Creation

### Overview

Create the projects router, wire it into `app/main.py`, and implement project list and project creation. Creating a project auto-creates one unnamed default element in the same transaction (FR-002). Add a "My projects" link to the index page.

### Changes Required

#### 1. Pattern parser service

**File**: `app/services/__init__.py` (new, empty)
**File**: `app/services/pattern.py` (new)

**Intent**: Centralise the pattern-text-to-rows logic so it can be tested and reused (re-parse on edit).

**Contract**: One public function `parse_pattern(text: str) -> list[tuple[int, str]]` — splits input using `str.splitlines()` (handles `\n`, `\r\n`, and `\r`), strips each line, drops blank lines, returns `[(position, content)]` with 1-based `position`. Returns an empty list if the input is blank or all whitespace.

#### 2. Projects router

**File**: `app/routes/projects.py` (new)

**Intent**: Define all project and element routes. Start with project list and project create.

**Contract**:
- `router = APIRouter(prefix="/projects")` with a module-level `templates = Jinja2Templates(directory="app/templates")`.
- `GET /` — query Projects where `user_id == user.id`, ordered by `updated_at DESC`, render `projects/list.html` with `{"user": user, "projects": projects}`.
- `GET /new` — render `projects/new.html` with `{"user": user}`.
- `POST /new` — create `Project(user_id=user.id, name=name.strip(), ...)` + `Element(project_id=project.id, name=None, repeat_count=1, ...)` in one `session.add` block before the auto-commit; redirect 303 to `/projects/{project.id}`. Validate: name must not be blank (re-render form with `{"error": "Project name is required."}`).

#### 3. Register router in main.py

**File**: `app/main.py`

**Intent**: Make project routes reachable.

**Contract**: Import `projects_router` from `app.routes.projects` and call `app.include_router(projects_router)` after the existing `app.include_router(auth_router)` line.

#### 4. Index page link

**File**: `app/templates/index.html`

**Intent**: Give authenticated users a path to their projects from the home page.

**Contract**: Add a link `<a href="/projects/">My projects</a>` inside the `{% block content %}` block.

#### 5. Project list template

**File**: `app/templates/projects/list.html` (new)

**Intent**: Show all the user's projects; empty state if none.

**Contract**: Extends `base.html`. If `projects` is empty, show "No projects yet — create one." with a link to `/projects/new`. Otherwise render a list of project names linking to `/projects/{project.id}`, each showing `updated_at` if useful. Include a "New project" link.

#### 6. Project create form template

**File**: `app/templates/projects/new.html` (new)

**Intent**: Single-field form for project name.

**Contract**: Extends `base.html`. `{% if error %}` banner. `<form method="post" action="/projects/new">` with `<input name="name" required>` and a submit button.

### Success Criteria

#### Automated Verification

- App starts without import errors: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8080`
- `parse_pattern` unit test: given `"Row 1\n\nRow 2\n  Row 3  "` returns `[(1, "Row 1"), (2, "Row 2"), (3, "Row 3")]`; given `""` returns `[]`

#### Manual Verification

- Logged-in user sees `GET /projects/` with an empty-state message and "New project" link.
- Submitting a project name creates the project and redirects to `/projects/{id}` (detail, even if minimal — 404 OK at this phase).
- Submitting a blank name re-renders the form with an error message.
- `/projects/` shows the new project by name.
- `GET /` (index) shows a "My projects" link.

**Implementation Note**: Pause after Phase 1 manual testing before proceeding.

---

## Phase 2: Element Detail + Pattern Parsing

### Overview

Implement the element detail page (`GET/POST /projects/{id}/elements/{eid}`) with pattern paste form and row display. On POST, parse the text into Row records, create one ElementRepetition (repeat_count=1 for now), and eagerly initialise RowState records. If the element already has rows, show an inline warning on the form before the user saves.

### Changes Required

#### 1. Element detail routes

**File**: `app/routes/projects.py`

**Intent**: Add `GET` and `POST` routes for `/projects/{id}/elements/{eid}`.

**Contract**:

`GET /projects/{project_id}/elements/{element_id}`:
- Fetch Project by `project_id`; 404 if not found or `user_id != user.id`.
- Fetch Element by `element_id`; 404 if not found or `project_id` doesn't match.
- Query Row records for this element (`WHERE element_id = element.id ORDER BY position ASC`).
- Pass `{"user": user, "project": project, "element": element, "rows": rows, "has_rows": len(rows) > 0}` to `projects/element_detail.html`.

`POST /projects/{project_id}/elements/{element_id}`:
- Same ownership checks.
- Read `pattern_text` from Form.
- Run `parse_pattern(pattern_text)` — returns `[(position, content)]`.
- If result is empty: re-render form with `{"error": "Pattern text produced no rows — please check the input."}`.
- If element already has rows: delete in order:
  1. Bulk-delete RowStates where `element_repetition_id IN (SELECT id FROM element_repetition WHERE element_id = element.id)`.
  2. Bulk-delete Rows where `element_id = element.id`.
  3. Bulk-delete ElementRepetitions where `element_id = element.id`.
- Update `element.pattern_text = pattern_text.strip()`.
- Insert Rows: one per `(position, content)` from parser output.
- Insert ElementRepetitions: one per `range(1, element.repeat_count + 1)` — for S-01 this is always one repetition.
- Call `await session.flush()` — this sends the Row and ElementRepetition INSERTs to the DB so their auto-increment PKs are populated on the in-memory objects before RowStates reference them.
- Insert RowStates: one per `(element_repetition, row)` combination, `state=RowStateEnum.not_started`.
- Update `project.updated_at = datetime.now(timezone.utc)`.
- All inserts happen in a single transaction (auto-committed by `get_session`).
- Redirect 303 to `GET /projects/{project_id}/elements/{element_id}`.

#### 2. Element detail template

**File**: `app/templates/projects/element_detail.html` (new)

**Intent**: Pattern paste form + row list with grey-dot state indicators. Warning banner when rows already exist.

**Contract**: Extends `base.html`. Sections in order:
1. Breadcrumb: project name → element name (or "Unnamed element").
2. `{% if error %}` error banner.
3. `{% if has_rows %}<p style="color: orange">⚠ Saving a new pattern will reset all row progress for this element.</p>{% endif %}`.
4. `<form method="post">` with `<textarea name="pattern_text" rows="10">{{ element.pattern_text or "" }}</textarea>` and submit button labelled "Save pattern".
5. `{% if rows %}` → `<ol>` list; each `<li>` has a grey dot (`●` or `○` in grey, inline style) followed by `{{ row.content }}`. `{% else %}` → "No pattern pasted yet." `{% endif %}`.

### Success Criteria

#### Automated Verification

- App starts without import errors after adding new routes.
- `parse_pattern` edge cases tested: single-line input, trailing whitespace, Windows-style `\r\n` line endings (strip handles both).

#### Manual Verification

- Navigate to `/projects/{id}/elements/{auto_eid}` (after creating a project in Phase 1) — see empty pattern form with "No pattern pasted yet."
- Paste a multi-line pattern (5+ lines), save — redirected back; rows appear as a numbered list with grey dots.
- Verify in the DB (or via Fly logs) that Row + ElementRepetition + RowState records exist.
- Re-paste a different pattern — orange warning banner is visible on the page above the form (because `has_rows=True`). Save confirms the replacement; new rows appear, old rows are gone.
- Paste blank text — form re-renders with an error message.

**Implementation Note**: Pause after Phase 2 manual testing before proceeding.

---

## Phase 3: Project Detail + Add Element

### Overview

Implement `GET /projects/{id}` (project detail showing elements with row counts and links) and `GET/POST /projects/{id}/elements/new` (add a named element). After adding an element, redirect to its element detail page so the user can immediately paste a pattern.

### Changes Required

#### 1. Project detail route

**File**: `app/routes/projects.py`

**Intent**: Show a project's elements with their row counts and links to their detail pages.

**Contract**:

`GET /projects/{project_id}`:
- Fetch Project; 404 if not found or ownership fails.
- For each Element: count its Rows (sub-query or load + len).
- Render `projects/detail.html` with `{"user": user, "project": project, "elements_with_counts": [(element, row_count), ...]}`.

#### 2. Add element routes

**File**: `app/routes/projects.py`

**Intent**: Allow adding a named element to an existing project.

**Contract**:

`GET /projects/{project_id}/elements/new`:
- Ownership check.
- Render `projects/element_new.html` with `{"user": user, "project": project}`.

`POST /projects/{project_id}/elements/new`:
- Ownership check.
- Read `name` from Form; validate not blank (re-render with error if blank).
- Create `Element(project_id=project.id, name=name.strip(), repeat_count=1, ...)`.
- Update `project.updated_at = datetime.now(timezone.utc)`.
- Redirect 303 to `/projects/{project_id}/elements/{new_element.id}` (element detail — user can immediately paste a pattern).

#### 3. Project detail template

**File**: `app/templates/projects/detail.html` (new)

**Intent**: Overview of a project — its elements, each showing row count and a link to element detail.

**Contract**: Extends `base.html`. Shows project name as heading. Lists elements: element name (or "Unnamed element"), row count ("N rows" or "No pattern yet"), link to `/projects/{id}/elements/{eid}`. "Add element" link to `/projects/{id}/elements/new`. Back link to `/projects/`.

#### 4. Add element template

**File**: `app/templates/projects/element_new.html` (new)

**Intent**: Single-field form for element name.

**Contract**: Extends `base.html`. `{% if error %}` banner. `<form method="post" action="/projects/{project.id}/elements/new">` with `<input name="name" required placeholder="e.g. Body, Sleeves">`. Submit button "Add element". Back link to project detail.

### Success Criteria

#### Automated Verification

- App starts without import errors after all routes are added.
- `GET /projects/{id}` returns 200 for the project's owner and 404 for a different user (ownership enforced).

#### Manual Verification

- After creating a project, `GET /projects/{id}` shows the auto-element (unnamed, 0 rows or N rows if pattern was pasted in Phase 2).
- "Add element" link navigates to the form; submitting a blank name shows an error; submitting a valid name redirects to the new element's detail page.
- New element appears on project detail page with "No pattern yet."
- Can navigate back to project list from project detail; can switch between multiple projects.
- Accessing another user's project URL returns 404.

**Implementation Note**: Pause after Phase 3 manual testing before proceeding.

---

## Testing Strategy

### Unit Tests

- `app/services/pattern.py::parse_pattern` — test with: normal multi-line input, blank lines between rows, leading/trailing whitespace, empty string, string of only whitespace, Windows `\r\n` endings.

### Integration Tests

- None added in S-01 (no test infrastructure exists yet). Manual verification covers the critical paths.

### Manual Testing Steps

1. Create a project → redirected to project detail → auto-element visible.
2. Open auto-element → paste a 10-line pattern → save → rows visible with grey dots.
3. Re-paste different pattern → warning banner visible → save → new rows appear.
4. Add a second named element → redirected to its detail → paste pattern → rows appear.
5. Return to project list → both projects visible (if multiple created) → switch between them.
6. Open URL for another user's project (or a non-existent ID) → 404.

## Performance Considerations

Pattern parsing and eager RowState initialisation insert up to `N × M` RowState rows in one transaction, where N = row count and M = `repeat_count`. For S-01 with `repeat_count=1` and typical pattern lengths (20–200 rows), this is negligible. No caching or batching needed at this scale.

## Migration Notes

No migrations required. All tables are in place from F-01 and F-02.

## References

- Research: `context/changes/project-and-pattern-display/research.md`
- PRD refs: FR-001, FR-002, FR-004, FR-005, FR-008
- DB models: `app/models/project.py`, `app/models/pattern.py`, `app/models/progress.py`
- Auth pattern: `app/routes/auth.py`, `app/auth/dependencies.py`

---

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Project Routes + Auto-Element Creation

#### Automated

- [x] 1.1 App starts without import errors after adding router and templates — b25e656
- [x] 1.2 `parse_pattern` unit test passes: multi-line input, blank lines, whitespace, empty string — b25e656

#### Manual

- [x] 1.3 `GET /projects/` shows empty-state message and "New project" link — b25e656
- [x] 1.4 Submitting project name creates project and redirects to `/projects/{id}` — b25e656
- [x] 1.5 Blank name submission re-renders form with error message — b25e656
- [x] 1.6 `/projects/` lists the new project by name — b25e656
- [x] 1.7 `GET /` index shows "My projects" link — b25e656

### Phase 2: Element Detail + Pattern Parsing

#### Automated

- [x] 2.1 App starts without import errors after new routes added — 487a73b
- [x] 2.2 `parse_pattern` edge cases tested: single-line, trailing whitespace, `\r\n` endings — 487a73b

#### Manual

- [x] 2.3 Element detail shows empty pattern form with "No pattern pasted yet" — 487a73b
- [x] 2.4 Pasting a multi-line pattern saves and displays numbered rows with grey dots — 487a73b
- [x] 2.5 Row + ElementRepetition + RowState records exist in DB after paste — 487a73b
- [x] 2.6 Re-pasting shows orange warning banner; saving replaces rows correctly — 487a73b
- [x] 2.7 Pasting blank text re-renders form with error message — 487a73b

### Phase 3: Project Detail + Add Element

#### Automated

- [x] 3.1 App starts without import errors after all routes added
- [x] 3.2 `GET /projects/{id}` returns 404 for a different user's project

#### Manual

- [x] 3.3 Project detail shows auto-element with correct row count
- [x] 3.4 "Add element" form validates blank name and shows error
- [x] 3.5 Adding a named element redirects to its element detail page
- [x] 3.6 New element appears on project detail with "No pattern yet"
- [x] 3.7 Project list allows switching between multiple projects
- [x] 3.8 Accessing another user's project URL returns 404
