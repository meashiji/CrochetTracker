---
project: CrochetTracker
version: 1
status: draft
created: 2026-06-05
updated: 2026-09-03
prd_version: 1
main_goal: market-feedback
top_blocker: time
---

# Roadmap: CrochetTracker

> Derived from `context/foundation/prd.md` (v1) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Vision recap

Crochet enthusiasts lose track of their row position when returning to a project after a break. The app solves one specific job: knowing instantly, on reopening a project, exactly which row to start from — without notes, counting, or memory. The product hypothesis is that covering this single narrow job eliminates the whole class of mid-project mistakes crocheters experience today.

## North star

**S-02: row-marking-and-persistence** — User marks a row done, closes the app, returns the next day, and finds it still marked.

> Gwiazda przewodnia (north star) oznacza tu: najmniejszy kompletny przepływ od końca do końca, który udowadnia, że produkt działa — S-02 umieszczone jest tak wcześnie jak Prerequisites pozwalają, bo wszystko inne ma sens tylko wtedy, gdy zaznaczanie i trwałość stanu działają.

This is the moment the product hypothesis is proven: the app reliably answers "where was I?" without any effort from the user.

## At a glance

| ID   | Change ID                    | Outcome (user can …)                                              | Prerequisites | PRD refs                              | Status   |
|------|------------------------------|-------------------------------------------------------------------|---------------|---------------------------------------|----------|
| F-01 | db-schema-and-models         | (foundation) ORM models, migrations, DB connection in place       | —             | FR-001–010                            | done     |
| F-02 | auth-scaffold                | (foundation) sign up, sign in; routes protected per-user          | F-01          | Access Control                        | done     |
| S-01 | project-and-pattern-display  | create a project, paste a pattern, and see it as a list of rows   | F-01, F-02    | FR-001, FR-002, FR-004, FR-005, FR-008 | done     |
| S-02 | row-marking-and-persistence  | mark a row (3 states) and return next day to find it still marked | S-01          | FR-006, FR-007, US-01                 | done     |
| S-03 | repeats-and-stitch-position  | track repeat elements independently; record stitch position        | S-02          | FR-003, FR-010                        | done     |
| S-04 | stitch-reference-panel       | open a reference panel showing stitch codes and descriptions       | F-02          | FR-009                                | done     |
| P-01 | ui-polish                    | visual design pass — typography, colors, spacing, responsive       | S-02          | —                                     | done |

## Streams

Navigation aid — groups items that share a Prerequisites chain. Canonical ordering lives in the dependency graph below; this table is the proposed reading order across parallel tracks.

| Stream | Theme                  | Chain                                    | Note                                                                      |
|--------|------------------------|------------------------------------------|---------------------------------------------------------------------------|
| A      | Critical tracking path | `F-01` → `F-02` → `S-01` → `S-02`       | The only path to the north star; strictly sequential by dependency.       |
| B      | Tracking extensions    | `S-02` → `S-03`                          | Extends the core mechanic after north star is validated.                  |
| C      | Reference panel        | `F-02` → `S-04`                          | Nice-to-have; parallel with S-01/S-02/S-03 once F-02 is done.            |

## Baseline

What's already in place as of 2026-06-05 (auto-researched + user-confirmed).
Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent — no templates, no Tailwind CSS, no static/ directory
- **Backend / API:** partial — FastAPI app at `app/main.py:3`, `/health` and `/` only; `app/routes/` and `app/models/` empty
- **Data:** absent — no SQLModel/SQLAlchemy, no migrations; no DB deps in `pyproject.toml`
- **Auth:** absent — no auth provider, sessions, or middleware
- **Deploy / infra:** present — Dockerfile, fly.toml, GitHub Actions, Fly Postgres provisioned on Fly.io (region: fra)
- **Observability:** absent — no logging library, no Sentry, no metrics

## Foundations

### F-01: Database schema + SQLModel setup

- **Outcome:** (foundation) SQLModel models (User, Project, Element, ElementRepetition, Row, RowState) defined; Alembic configured; DB connection wired to Fly Postgres via `DATABASE_URL`; migrations apply cleanly on deploy.
- **Change ID:** db-schema-and-models
- **PRD refs:** FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-010 (every data-backed FR depends on this schema)
- **Unlocks:** F-02 (needs User model), S-01 (needs Project / Element / Row tables)
- **Prerequisites:** — (Fly Postgres already provisioned per baseline)
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** The RowState schema (not-started / in-progress / done + optional stitch position) must be correct before S-02 is built — a schema change after S-02 lands requires a data migration with live data. Define it carefully in /10x-plan db-schema-and-models before writing any migration.
- **Status:** done

### F-02: Auth scaffold

- **Outcome:** (foundation) user can sign up and sign in via email + password or magic link; an unauthenticated visitor is redirected to the sign-in screen; session middleware protects all project routes; every user sees only their own data.
- **Change ID:** auth-scaffold
- **PRD refs:** Access Control section, US-01 acceptance criteria ("after initial sign-in, no manual save required"; "same project state on every signed-in device")
- **Unlocks:** S-01 (project views require an authenticated user), S-04 (reference panel lives inside the auth shell)
- **Prerequisites:** F-01 (needs User model)
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Which library handles email + password + magic link sessions in FastAPI + Jinja2? (fastapi-users, authlib, custom flow?) Owner: user. Block: no — /10x-plan auth-scaffold resolves this.
- **Risk:** No standard FastAPI library covers magic links out of the box; this is the highest-research foundation. Sequenced immediately after F-01 because every S-NN slice needs it — a bad auth choice is expensive to swap once project routes depend on it.
- **Status:** done

## Slices

### S-01: Project creation + pattern display

- **Outcome:** user can create a project, add a named element, paste a plain-text pattern, and see it displayed as a scrollable list of rows; user can switch between multiple projects.
- **Change ID:** project-and-pattern-display
- **PRD refs:** FR-001, FR-002, FR-004, FR-005, FR-008
- **Prerequisites:** F-01, F-02
- **Parallel with:** S-04 (once F-02 is done; neither depends on the other)
- **Blockers:** —
- **Unknowns:**
  - Pattern row-boundary editor UX (FR-004 / FR-005): how does the user adjust boundaries after best-effort parse — drag-to-split, click-to-merge, or raw text edit? Owner: user. Block: no (design decision for /10x-plan, best-effort parse ships first).
- **Risk:** The best-effort row parser (split by line, user-adjustable) must not block delivery — ship the simplest split first, make boundaries editable in a follow-up if needed. Don't let parser complexity delay S-02.
- **Status:** done

### S-02: Row marking + persistence (north star)

- **Outcome:** user can set a row to one of three states (not started / in-progress / done), toggle between them; on reopening the project, the view jumps to the first unmarked row and shows the exact previously-marked state — no manual save required.
- **Change ID:** row-marking-and-persistence
- **PRD refs:** FR-006, FR-007, US-01
- **Prerequisites:** S-01
- **Parallel with:** S-04 (once F-02 is done)
- **Blockers:** —
- **Unknowns:**
  - Live-sync error UX: when a row-mark request fails (network blip, server error), what does the user see — inline toast, banner, modal? Owner: user. Block: no (PRD Open Question 1 — downstream design decision).
- **Risk:** The 100ms NFR (row state change reflected in UI within 100ms) requires HTMX to update the DOM optimistically or the server to respond fast enough. Sequenced first among slices because it proves the core hypothesis — don't defer it for UX polish.
- **Status:** done

### S-03: Repeat element tracking + stitch position

- **Outcome:** user can set a repeat count on an element (e.g., ×3) and track each repetition with its own independent row progress; user can record the specific stitch position they stopped at within an in-progress row (e.g., "stopped at stitch 14").
- **Change ID:** repeats-and-stitch-position
- **PRD refs:** FR-003, FR-010
- **Prerequisites:** S-02
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Repeat tracking multiplies the row-state records in the DB (N repetitions × M rows per element). Ensure F-01's ElementRepetition model handles this cleanly so S-03 is an additive UI change, not a schema rework.
- **Status:** done

### S-04: Stitch reference panel

- **Outcome:** user can open a reference panel showing common stitch codes and their descriptions (US, UK notation, or both).
- **Change ID:** stitch-reference-panel
- **PRD refs:** FR-009
- **Prerequisites:** F-02
- **Parallel with:** S-01, S-02, S-03
- **Blockers:** —
- **Unknowns:**
  - Which stitch codes to include — US notation, UK notation, both? What is the source of the glossary content? Owner: user. Block: yes — content must be decided before this slice can be planned.
- **Risk:** Low — this is a static reference panel with no data model dependencies. Blocked only by the content decision (Open Question 3).
- **Status:** done

### P-01: UI polish

- **Outcome:** the app looks intentional — consistent typography, color palette, spacing, and readable layout on mobile and desktop; no raw browser-default styling.
- **Change ID:** ui-polish
- **PRD refs:** —
- **Prerequisites:** S-02 (north star validated; component shapes are stable)
- **Parallel with:** S-03, S-04
- **Blockers:** —
- **Unknowns:**
  - Which CSS framework — Tailwind CSS, Pico.css, or plain custom CSS? Owner: user. Block: no (decide in /10x-plan ui-polish).
- **Risk:** Low — purely additive; no data model or route changes. Doing this before features stabilise risks rework if component structure changes.
- **Status:** done

## Backlog Handoff

| Roadmap ID | Change ID                   | Suggested issue title                                        | Ready for `/10x-plan` | Notes                                               |
|------------|-----------------------------|--------------------------------------------------------------|-----------------------|-----------------------------------------------------|
| F-01       | db-schema-and-models        | DB schema: SQLModel models + Alembic migrations              | done                  | Implemented                                          |
| F-02       | auth-scaffold               | Auth: sign-up, sign-in, magic link, session middleware        | done                  | Implemented                                          |
| S-01       | project-and-pattern-display | Project creation + pattern paste + row list display          | done                  | Implemented, all 3 phases impl-reviewed              |
| S-02       | row-marking-and-persistence | Row marking (3 states) + auto-jump + persistence (north star) | yes                  | Prerequisite S-01 done; run `/10x-new row-marking-and-persistence` — this is the validation milestone |
| S-03       | repeats-and-stitch-position | Repeat element tracking + stitch position recording          | no                    | Needs S-02 done                                     |
| S-04       | stitch-reference-panel      | Stitch reference panel (nice-to-have)                        | no                    | Blocked on stitch content decision (Open Question 3)|
| P-01       | ui-polish                   | Visual design pass (typography, colors, spacing, responsive) | no                    | Plan after S-02; CSS framework TBD                  |

## Open Roadmap Questions

1. **Live-sync error UX** — When a row-mark request fails, what does the user see — inline toast, banner, modal? Owner: user. Block: no (affects S-02 polish, not S-02 planning).
2. **Account recovery flow** — If the user loses access to their password or magic-link email, what is the recovery path? Owner: user. Block: no.
3. **Stitch reference content (FR-009)** — Which stitch codes to include — US notation, UK notation, both? What is the glossary source? Owner: user. Block: S-04 (blocks planning of stitch-reference-panel).
4. **Pattern row-boundary editor UX (FR-004 / FR-005)** — How does the user adjust row boundaries after best-effort parse? Owner: user. Block: no (ships as simple split first; editor UX is a follow-up).

## Parked

- **PDF import** — Why parked: PRD §Non-Goals: "Pattern input is plain-text paste only. PDF parsing is unpredictable across pattern formats and belongs in v2."
- **Pattern sharing / community features** — Why parked: PRD §Non-Goals: "No public pattern library, no sharing between users, no social feed."
- **Team / multi-user workspaces** — Why parked: PRD §Non-Goals: "One account, one user's projects."
- **Automatic pattern parsing intelligence** — Why parked: PRD §Non-Goals: "No AI/ML row detection in v1."
- **PWA install + dedicated mobile UX polish** — Why parked: PRD §Non-Goals: responsive layout ships; "Add to home screen" and touch-target refinements deferred to v2.
- **Offline capability** — Why parked: PRD §Non-Goals: "Offline-first behaviour explicitly deferred to v2. Trade-off made to enable Python-only stack matching developer skills."
- **Observability** — Why parked: no PRD requirement for logging/error-tracking at MVP; add if Fly.io logs prove insufficient post-launch.

## Done

(Empty on first generation. `/10x-archive` appends here when a change matching a roadmap item is archived.)

- **F-01: (foundation) SQLModel models (User, Project, Element, ElementRepetition, Row, RowState) defined; Alembic configured; DB connection wired to Fly Postgres via `DATABASE_URL`; migrations apply cleanly on deploy.** — Archived 2026-08-21 → `context/archive/2026-06-05-db-schema-and-models/`. Lesson: —.
- **F-02: (foundation) user can sign up and sign in via email + password or magic link; an unauthenticated visitor is redirected to the sign-in screen; session middleware protects all project routes; every user sees only their own data.** — Archived 2026-08-21 → `context/archive/2026-06-13-auth-scaffold/`. Lesson: —.
- **S-01: user can create a project, add a named element, paste a plain-text pattern, and see it displayed as a scrollable list of rows; user can switch between multiple projects.** — Archived 2026-08-21 → `context/archive/2026-06-27-project-and-pattern-display/`. Lesson: —.

- **S-02: user can set a row to one of three states (not started / in-progress / done), toggle between them; on reopening the project, the view jumps to the first unmarked row and shows the exact previously-marked state — no manual save required.** — Archived 2026-08-01 → `context/archive/2026-07-09-row-marking-and-persistence/`. Lesson: —.
- **S-03: user can set a repeat count on an element (e.g., ×3) and track each repetition with its own independent row progress; user can record the specific stitch position they stopped at within an in-progress row (e.g., "stopped at stitch 14").** — Archived 2026-08-20 → `context/archive/2026-08-01-repeats-and-stitch-position/`. Lesson: —.
- **S-04: user can open a reference panel showing 8 basic crochet stitches in US notation with descriptions; the popover is anchored under the header button, stays fixed while scrolling the pattern, and is fully accessible without auth barriers.** — Archived 2026-08-23 → `context/archive/2026-08-23-stitch-reference-panel/`. Lesson: —.

- **P-01: (foundation) the app looks intentional — consistent typography, color palette, spacing, and readable layout on mobile and desktop; no raw browser-default styling.** — Archived 2026-09-03 → `context/archive/2026-08-23-ui-polish/`. Lesson: —.
