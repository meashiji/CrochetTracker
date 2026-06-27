---
date: 2026-06-27T08:02:28+00:00
researcher: claude-sonnet-4-6
git_commit: 7a39602dafac835d64a6e68a612891fd40d43829
branch: main
repository: CrochetTracker
topic: "S-01: project-and-pattern-display — codebase integration points"
tags: [research, codebase, s-01, project, element, row, pattern, routes, templates]
status: complete
last_updated: 2026-06-27
last_updated_by: claude-sonnet-4-6
---

# Research: S-01 Project Creation + Pattern Display

**Date**: 2026-06-27T08:02:28+00:00
**Researcher**: claude-sonnet-4-6
**Git Commit**: 7a39602dafac835d64a6e68a612891fd40d43829
**Branch**: main
**Repository**: CrochetTracker

## Research Question

What does the existing codebase provide for S-01 (project creation + pattern display)? What models, routes, template conventions, and auth integration points are available? What key decisions were made in prior changes that constrain or guide the implementation?

## Summary

The schema is fully in place and ready for S-01 — no migrations needed. Pattern text is stored raw in `Element.pattern_text`; S-01's paste handler is responsible for parsing it into `Row` records, creating `ElementRepetition` records, and eagerly initialising `RowState` records. Routes follow a consistent FastAPI + Jinja2 pattern with `Depends(get_current_user)` + `Depends(get_session)`. No HTMX is in use yet. All S-01 routes are automatically protected by `AuthRedirectMiddleware` with no middleware changes required.

## Detailed Findings

### 1. Data Models (all in `app/models/`)

#### Project — `app/models/project.py:7-21`
```
project table:
  id          int, PK, auto-increment
  user_id     int, NOT NULL, INDEXED, FK → user.id
  name        str, NOT NULL
  created_at  datetime (UTC, tz-aware), NOT NULL, default=now
  updated_at  datetime (UTC, tz-aware), NOT NULL, default=now, auto-updated
```
Filter by user: `select(Project).where(Project.user_id == user.id)`

#### Element — `app/models/project.py:24-35`
```
element table:
  id            int, PK
  project_id    int, NOT NULL, INDEXED, FK → project.id
  name          str | None (nullable — None = default auto-element)
  pattern_text  str | None (nullable — raw pasted text, kept for re-parsing)
  repeat_count  int, NOT NULL, default=1, ge=1
  created_at    datetime (UTC, tz-aware), NOT NULL
```
`pattern_text` is the raw paste blob. No size limit defined in schema or planning docs.

#### ElementRepetition — `app/models/project.py:38-44`
```
element_repetition table:
  id                  int, PK
  element_id          int, NOT NULL, INDEXED, FK → element.id
  repetition_number   int, NOT NULL
  UNIQUE(element_id, repetition_number)
```
Created eagerly by S-01's paste handler: one row per `range(1, element.repeat_count + 1)`.

#### Row — `app/models/pattern.py:5-12`
```
row table:
  id          int, PK
  element_id  int, NOT NULL, INDEXED, FK → element.id
  position    int, NOT NULL  (1-based, order within element)
  content     str, NOT NULL  (text of this parsed line)
  UNIQUE(element_id, position)
```
One `Row` DB record = one line of the parsed pattern text.

#### RowState — `app/models/progress.py:14-27`
```
row_state table:
  id                      int, PK
  element_repetition_id   int, NOT NULL, INDEXED, FK → element_repetition.id
  row_id                  int, NOT NULL, INDEXED, FK → row.id
  state                   RowStateEnum, NOT NULL, default=not_started
  stitch_position         int | None (nullable, only meaningful when in_progress)
  updated_at              datetime (UTC, tz-aware), NOT NULL
  UNIQUE(element_repetition_id, row_id)
```

RowStateEnum values (`app/models/progress.py:8-11`): `not_started`, `in_progress`, `done`

S-01 must create one RowState per (ElementRepetition × Row) combination, all initialised to `not_started`. This is the "eager initialisation" contract established in `db-schema-and-models/plan.md:32`.

#### Relationship Chain for Display
```
User ──(user_id)──→ Project ──(project_id)──→ Element ──(element_id)──→ Row (ordered by position)
                                                         └──(element_id)──→ ElementRepetition
                                                                              └──(element_repetition_id + row_id)──→ RowState
```

### 2. Pattern Parsing Contract

**Established in:** `context/changes/db-schema-and-models/plan.md:32, 136-142`

- `pattern_text` stores the **raw pasted text** — kept verbatim for re-parsing.
- At paste time, S-01 splits by newline (`\n`), strips blank lines, assigns 1-based `position`.
- Each non-blank line → one `Row` record.
- For each repetition (1..repeat_count) → one `ElementRepetition` + one `RowState` per Row.
- The roadmap explicitly defers boundary-editor UX: "ship the simplest split first".

### 3. Auth Integration

**`get_current_user`** — `app/auth/dependencies.py:8-15`
```python
async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401)
    return user
```
- Import: `from app.auth.dependencies import get_current_user`
- Returns `User` with attributes: `.id` (int), `.email` (str), `.password_hash` (str | None), `.created_at`
- Raises 401 when not authenticated; `AuthRedirectMiddleware` catches it and redirects to `/auth/login`

**`get_session`** — `app/db.py:16-23`
- `AsyncSession` async generator
- Auto-commits on success, auto-rollbacks on exception
- Import: `from app.db import get_session`

**Middleware** — `app/auth/middleware.py:6`
- `_PUBLIC_PATHS` explicit set: `/health`, `/auth/login`, `/auth/signup`, `/auth/magic-link`, `/auth/magic-link/verify`
- Everything else (including `/projects/*`) auto-requires authentication — **no middleware changes needed for S-01**.

### 4. Existing Route & Template Conventions

**Router pattern** (`app/routes/auth.py:19-20`):
```python
router = APIRouter(prefix="/auth")
templates = Jinja2Templates(directory="app/templates")
```
S-01 follows this: `APIRouter(prefix="/projects")` in new file `app/routes/projects.py`.

**TemplateResponse signature**:
```python
templates.TemplateResponse(request, "projects/template.html", {"user": user})
templates.TemplateResponse(request, "projects/template.html", {"user": user, "error": "msg"})
```
Context always includes `request` (positional arg 1) and `user` for authenticated pages.

**Error display** (all auth templates):
```html
{% if error %}<p style="color: red">{{ error }}</p>{% endif %}
{% if success %}<p style="color: green">{{ success }}</p>{% endif %}
```

**POST success → redirect**:
```python
return RedirectResponse(url="/projects/{id}", status_code=303)
```
Always 303, never 302.

**Template naming**: snake_case, organised by feature: `projects/list.html`, `projects/detail.html`, `projects/new.html`, `projects/element_new.html`.

**Router registration** (`app/main.py:26`):
```python
app.include_router(auth_router)  # existing pattern
app.include_router(projects_router)  # S-01 adds this
```

### 5. HTMX Status

No `hx-*` attributes found anywhere in current templates. The project does not use HTMX yet. S-01 can introduce it (the roadmap mentions HTMX for the 100ms row-mark NFR in S-02), or ship plain form-submit first. Decision for `/10x-plan`.

### 6. Current `app/main.py` Structure

- FastAPI app at `app/main.py:12`
- Middleware: `AuthRedirectMiddleware` + `SessionMiddleware` (lines 14-20)
- Static files mounted at `/static/` from `app/static/` (line 22)
- Templates: `Jinja2Templates(directory="app/templates")` (line 24)
- Routes: `app.include_router(auth_router)` (line 26)
- Custom 500 handler (lines 29-31)
- Built-in routes: `GET /health`, `GET /` (lines 34-41)

## Code References

- `app/models/project.py:7-21` — Project model
- `app/models/project.py:24-35` — Element model (includes `pattern_text`)
- `app/models/project.py:38-44` — ElementRepetition model
- `app/models/pattern.py:5-12` — Row model
- `app/models/progress.py:8-11` — RowStateEnum
- `app/models/progress.py:14-27` — RowState model
- `app/auth/dependencies.py:8-15` — `get_current_user`
- `app/auth/middleware.py:6` — `_PUBLIC_PATHS`
- `app/db.py:16-23` — `get_session` async generator
- `app/routes/auth.py:19-20` — APIRouter + Jinja2Templates instantiation pattern
- `app/main.py:12-41` — full main.py structure

## Architecture Insights

**Eager row initialisation**: S-01 must create the full `Row` + `ElementRepetition` + `RowState` graph at paste time. This means S-01's pattern-paste POST handler does significant DB work: parse text → insert N rows, M repetitions, N×M row_states. For typical patterns (20-200 rows, repeat_count=1) this is fine in a single transaction.

**Re-parsing**: `pattern_text` is kept so the boundary editor (future) can re-parse without losing the original. If S-01 ever offers an "edit pattern" flow, it should clear and re-create Row/RowState records.

**User isolation**: enforced at query level (`WHERE user_id = user.id` on Project), not at model level. The `get_current_user` dependency + explicit WHERE clause is the established pattern.

**Session auto-commit**: `get_session` commits after the route handler returns. Routes that need to commit mid-handler (e.g., to ensure insert before redirect) can call `await session.commit()` manually — the second commit from `get_session` is a no-op. (Pattern established in auth-scaffold magic-link routes.)

**Lessons from `context/foundation/lessons.md`**: Destructive migration downgrades must be commented. S-01 adds no new migrations, so this doesn't apply here.

## Historical Context (from prior changes)

- `context/changes/db-schema-and-models/plan.md:32` — RowState eager initialisation assigned to S-01's paste handler ("RowState rows are inserted eagerly by the pattern-paste handler in S-01")
- `context/changes/db-schema-and-models/plan.md:136-142` — Row = one record per parsed line, 1-based `position`
- `context/changes/auth-scaffold/plan.md:39` — S-01 project views deferred from F-02; `/` stays minimal until S-01
- `context/changes/auth-scaffold/change.md` — middleware switched from prefix to explicit set; S-01 routes auto-protected

## Open Questions

1. **Single-form vs two-step project creation**: Does "create a project" + "add an element with pattern" happen in one form submission or two separate routes? (Simpler: two steps — create project first, then add element.)
2. **Eager RowState at element creation or only at first view?** The plan says "eager at paste time" — confirming this means a project with a 200-row pattern creates 200 RowState records immediately.
3. **URL structure**: Not decided in prior plans. Conventional proposal: `GET /projects/` (list), `GET /projects/new` (create form), `POST /projects/new` (submit), `GET /projects/{id}` (detail), `GET /projects/{id}/elements/new` (add element form), `POST /projects/{id}/elements/new` (submit element + pattern). Needs confirmation in `/10x-plan`.
4. **HTMX for S-01?** S-01 is form-driven (create/paste). HTMX is more relevant in S-02 (row-mark toggling). Safe to skip in S-01 and add in S-02.
5. **Project switching UX**: The roadmap says "user can switch between multiple projects" — a project list at `/projects/` satisfies this. No sidebar or modal needed at MVP.
