# GitHub Issues — MVP Roadmap Migration

**Migrated:** 2026-06-05  
**Repository:** [patrycja-gurdak/CrochetTracker](https://github.com/patrycja-gurdak/CrochetTracker)  
**Source:** `context/foundation/roadmap.md` (v1)  
**Milestone:** [MVP v1](https://github.com/patrycja-gurdak/CrochetTracker/milestone/1) — hard deadline 2026-07-05

---

## Labels created

| Label | Color | Purpose |
|---|---|---|
| `foundation` | blue `#0075ca` | F-NN items — infrastructure prerequisites with no direct user-visible outcome |
| `slice` | green `#0e8a16` | S-NN items — user-facing capabilities |
| `blocked` | red `#d93f0b` | Item has a blocking unknown; cannot be planned until resolved |
| `nice-to-have` | gray `#cfd3d7` | Non-essential feature (nice-to-have priority in PRD) |

---

## Issues

### #1 — [F-01] DB schema: SQLModel models + Alembic migrations
**URL:** https://github.com/patrycja-gurdak/CrochetTracker/issues/1  
**Labels:** `foundation`  
**Roadmap status:** ready — `/10x-plan db-schema-and-models` can run now  
**Change ID:** `db-schema-and-models`

**What it delivers:** SQLModel models for every entity the app needs — User, Project, Element, ElementRepetition, Row, RowState — plus Alembic migration tooling and a wired DB connection to Fly Postgres via `DATABASE_URL`. This is the data contract the rest of the app is built on.

**Why first:** Every other issue (F-02 through S-04) either needs the User model (auth) or the Project/Row/State tables (slices). Fly Postgres is already provisioned — the only work is writing the code.

**Key risk:** The RowState schema (not-started / in-progress / done + optional stitch position) must be correct before S-02 is built. A schema change after S-02 ships requires a live data migration. Get it right in planning.

**Prerequisites:** none (Fly Postgres already provisioned)  
**Unlocks:** #2 (F-02), #3 (S-01)

---

### #2 — [F-02] Auth: sign-up, sign-in, magic link, session middleware
**URL:** https://github.com/patrycja-gurdak/CrochetTracker/issues/2  
**Labels:** `foundation`  
**Roadmap status:** proposed  
**Change ID:** `auth-scaffold`

**What it delivers:** User can sign up and sign in via email + password or magic link. An unauthenticated visitor is redirected to the sign-in screen. Session middleware protects all project routes. Each user sees only their own data — which is what makes cross-device sync meaningful.

**Why second:** Every slice (S-01 through S-04) lives behind the auth wall. A bad library choice here is expensive to swap once routes depend on it. Research the right solution in `/10x-plan auth-scaffold` before writing any code.

**Key risk:** No standard FastAPI library covers magic links out of the box. The planning step must evaluate fastapi-users, authlib, and a custom flow before committing.

**Prerequisites:** #1 (F-01 — needs User model)  
**Unlocks:** #3 (S-01), #6 (S-04)

---

### #3 — [S-01] Project creation + pattern paste + row list display
**URL:** https://github.com/patrycja-gurdak/CrochetTracker/issues/3  
**Labels:** `slice`  
**Roadmap status:** proposed  
**Change ID:** `project-and-pattern-display`

**What it delivers:** User can create a project, add a named element, paste a plain-text pattern, and see it displayed as a scrollable list of rows. User can switch between multiple projects. The app performs best-effort line-based row splitting; the user can adjust boundaries manually.

**Why third:** First user-visible slice. Sets up the project/element/pattern data and the UI shell that S-02 (the north star) builds on. Parser complexity must not delay delivery — ship simple line-split first.

**Key risk:** Don't let the row-boundary editor UX become a blocker. Best-effort split ships first; the editor UX is a follow-up design decision.

**Prerequisites:** #1 (F-01), #2 (F-02)  
**Parallel with:** #6 (S-04) — once #2 is done, neither depends on the other

---

### #4 — [S-02] Row marking (3 states) + auto-jump + persistence — north star
**URL:** https://github.com/patrycja-gurdak/CrochetTracker/issues/4  
**Labels:** `slice`  
**Roadmap status:** proposed  
**Change ID:** `row-marking-and-persistence`

**What it delivers:** User can set a row to one of three states (not started / in-progress / done) and toggle between them. On reopening the project, the view jumps to the first unmarked row and shows the previously-marked state — no manual save required. This is the moment the product hypothesis is proven.

**Why this is the north star:** The entire PRD vision is: "the moment the app covers that specific, narrow job, the whole class of mid-project mistakes goes away." That moment is when the user marks a row, closes the app, returns the next day, and finds it still marked. This slice delivers exactly that.

**Key risk:** The 100ms NFR (row state change reflected within 100ms) requires either optimistic DOM updates via HTMX or a fast server response. Plan for this explicitly — don't discover it during implementation.

**Prerequisites:** #3 (S-01)  
**Parallel with:** #6 (S-04)

---

### #5 — [S-03] Repeat element tracking + stitch position recording
**URL:** https://github.com/patrycja-gurdak/CrochetTracker/issues/5  
**Labels:** `slice`  
**Roadmap status:** proposed  
**Change ID:** `repeats-and-stitch-position`

**What it delivers:** User can set a repeat count on an element (e.g., ×3) and track each repetition with its own independent row progress. User can record the specific stitch position they stopped at within an in-progress row (e.g., "stopped at stitch 14").

**Why after north star:** Extends the validated core tracking mechanic. Both FRs (FR-003, FR-010) build on the RowState machine that S-02 establishes — they're additive UI and data changes, not architectural ones.

**Key risk:** ElementRepetition model in F-01 must be designed to handle N repetitions × M rows cleanly. If the schema was cut short in F-01, S-03 requires a migration.

**Prerequisites:** #4 (S-02)  
**Parallel with:** #6 (S-04)

---

### #6 — [S-04] Stitch reference panel
**URL:** https://github.com/patrycja-gurdak/CrochetTracker/issues/6  
**Labels:** `slice`, `blocked`, `nice-to-have`  
**Roadmap status:** blocked  
**Change ID:** `stitch-reference-panel`

**What it delivers:** User can open a reference panel inside the app showing common stitch codes and their descriptions (US notation, UK notation, or both). Reduces context-switching during active crochet work.

**Why blocked:** The content decision (which codes to include, which notation, what source) must be made before planning can start. This is Open Roadmap Question 3. Once resolved, this is low-complexity work — a static panel with no data model dependencies.

**To unblock:** Decide: US notation only / UK notation only / both? And what is the source of the glossary content? Update the issue, remove the `blocked` label, and run `/10x-plan stitch-reference-panel`.

**Prerequisites:** #2 (F-02 — lives inside the auth shell)  
**Parallel with:** #3, #4, #5 — can be worked any time after F-02 once content is decided

---

## Dependency graph

```
#1 F-01 (ready)
  └─► #2 F-02
        ├─► #3 S-01
        │     └─► #4 S-02 ◄── north star
        │           └─► #5 S-03
        └─► #6 S-04 (blocked — content decision needed)
```

## Critical path to north star

`#1` → `#2` → `#3` → `#4`

Start with `#1` now. Every day the critical path is clear: finish current issue, pick next in the chain.

## Working agreement

- **Start an issue:** assign yourself, move to "In Progress" on the milestone board.
- **Plan an issue:** run `/10x-plan <change-id>` — the skill creates `context/changes/<change-id>/` with a detailed implementation plan.
- **Close an issue:** run `/10x-archive <change-id>` after merging — the skill archives the change folder, flips the roadmap item to `done`, and appends a `## Done` entry in `roadmap.md`.
- **Unblock #6:** answer Open Roadmap Question 3 in `roadmap.md`, remove the `blocked` label from the issue, then plan it.
