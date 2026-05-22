---
project: "CrochetTracker"
context_type: greenfield
created: 2026-05-21
updated: 2026-05-21
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  gray_areas_resolved:
    - topic: "pain category"
      decision: "workflow friction — pattern and progress exist, tracking is clunky/manual"
    - topic: "status quo"
      decision: "mix of paper, memory, and generic notes apps — nothing consistent"
    - topic: "primary persona scope"
      decision: "user themselves first; crochet enthusiasts broadly if useful later"
    - topic: "auth model"
      decision: "account-based (email + password OR magic link); cloud sync across devices; offline use cached locally and synced on reconnect. ~4-week timeline accepted in exchange for solving the phone/laptop split."
    - topic: "pattern input"
      decision: "copy/paste plain text only for v1; PDF import deferred to v2"
    - topic: "mvp timeline"
      decision: "revised to ~4 weeks after-hours once cloud sync added; trimmed to ~3.5 weeks by deferring PWA install and mobile UX polish (responsive layout still in scope). Target 2026-07-05 with fallbacks 2026-08-10, 2026-09-14."
    - topic: "mobile scope"
      decision: "middle path — responsive layout so phone browsers work, but PWA install and dedicated mobile UX polish deferred to v2"
  frs_drafted: 10
  quality_check_status: accepted
product_type: web-app
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 4
  hard_deadline: "2026-07-05"
  hard_deadline_fallbacks: ["2026-08-10", "2026-09-14"]
  after_hours_only: true
---

## Functional Requirements

### Project & Element Management
- FR-001: User can create a new project with a name. Priority: must-have
  > Socrates: Counter considered — "naming adds setup friction before any value." Resolution: project naming is necessary for multi-project identification; stands as written.
- FR-002: User can add a named element to a project (e.g., "body"). Priority: must-have
  > Socrates: Counter accepted — "elements add friction for single-piece projects." Resolution: a default unnamed element is auto-created when a project is created; users name it or add more only when needed. Simple projects skip the step entirely.
- FR-003: User can set a repeat count on an element (e.g., ×3); each repetition is tracked independently with its own row progress. Priority: must-have
  > Socrates: Counter considered — "users could create duplicate elements manually." Resolution: repeat tracking matches how crochet patterns are actually written (×2 sleeves, ×4 squares); stands as written.

### Pattern Input & Display
- FR-004: User can paste a plain-text pattern into an element. Priority: must-have
  > Socrates: Counter accepted — "pattern text structure varies wildly; parsing may mangle the pattern." Resolution: app performs best-effort row splitting, but user can manually adjust row boundaries before starting. Parsing is a suggestion, not authoritative.
- FR-005: User can view the pattern displayed as a list of rows. Priority: must-have
  > Socrates: Counter raised — "full pattern display may be overwhelming for long patterns." Resolution: default view focuses on rows near current position; a slider allows navigating the full pattern. Full context remains accessible.

### Progress Tracking
- FR-006: User can set a row to one of three states (not started / in-progress / done); states are toggleable. Priority: must-have
  > Socrates: Both counters accepted — "mid-row stopping needs representation" and "mis-taps must be undoable." Resolution: three states (not started, in-progress, done) replace binary done/not-done; all states are toggleable. See FR-010 for stitch-level position within in-progress rows.
- FR-007: On opening a project, the view jumps to the first unmarked row; full pattern remains accessible by scrolling. Priority: must-have
  > Socrates: Counter accepted — "jumping to first unmarked row is more useful than showing all rows equally." Resolution: auto-scroll to first unmarked row on open; scrolling up reveals completed rows. Best of both.
- FR-010: User can record the specific stitch position they stopped at within an in-progress row (e.g., "stopped at stitch 14"). Priority: must-have

### Navigation
- FR-008: User can have multiple projects and switch between them. Priority: must-have
  > Socrates: Counter considered — "single-project v0 would prove the concept faster." Resolution: multiple projects are the core use case (the problem is juggling WIPs); a single-project app doesn't solve the stated pain. Stands as written.

### Reference
- FR-009: User can open a reference panel showing common stitch codes and their descriptions. Priority: nice-to-have
  > Socrates: Counter considered — "a static glossary duplicates external resources." Resolution: in-app reference reduces context-switching during active work; the convenience is genuine. Stands as written.

## Business Logic

CrochetTracker knows the user's next move for any active project — which row to work on and which stitch to start from — so they never have to count stitches or analyze the pattern and compare it to their work again.

The app holds, for each element repetition within a project, a row-completion state (not started / in-progress / done) and, when in-progress, a stitch position within that row. These states are the inputs the user provides by tapping. The output is the app's answer to "where am I?" — the first unmarked row and the last known stitch position — surfaced immediately on opening the project, without any calculation on the user's part.

## Non-Functional Requirements

- A row state change (mark / unmark / set in-progress) is reflected in the UI within 100 ms of the user's tap — no spinner, no loading state.
- The app's layout adapts responsively to phone-sized screens — a user can open it in a mobile browser, read the pattern, and tap rows. Full one-handed mobile UX polish (oversized touch targets, gesture optimization) is acceptable to defer to v2.
- All features work without an active internet connection — no action requires a network request to complete.
- Changes made while offline are reconciled with the server once connectivity returns; the user does not observe lost, duplicated, or silently reverted row marks after a reconnect.

## User Stories

### US-01: Returning to a project after a break

- **Given** a user has a project with at least one element, a pattern loaded, and some rows already marked done
- **When** they open the app and navigate to that project
- **Then** they see the exact rows already marked, can immediately identify where to continue, and can mark the next row done without any additional setup

#### Acceptance Criteria
- Marked rows are visually distinct from unmarked rows (green highlight or equivalent)
- The state shown matches what was last saved — no data loss on re-open
- After initial sign-in, no save button or manual persistence step is required during normal use
- Cross-device: the same project state appears on every signed-in device the user owns

## Non-Goals

- **No PDF import in v1.** Pattern input is plain-text paste only. PDF parsing is unpredictable across pattern formats and belongs in v2 once the core tracking is validated.
- **No pattern sharing or community features.** No public pattern library, no sharing between users, no social feed. This is a personal tracking tool.
- **No team or multi-user workspaces.** One account, one user's projects. No collaboration, no shared project access.
- **No automatic pattern parsing intelligence.** The app splits pasted text by line (best-effort) and lets the user adjust boundaries manually. No AI/ML row detection in v1.
- **No PWA install or dedicated mobile UX polish in v1.** The app is responsive (works in a mobile browser) but skips the "Add to home screen" PWA setup and the touch-target / one-handed-use refinements. Both deferred to v2.

## Vision & Problem Statement

Crochet enthusiasts lose track of their position in a pattern when they return from a break or switch between multiple active projects. The cost is real: wrong row counts, redone sections, and mistakes that only surface mid-project. Today there is no dedicated tool for this — crocheters fall back on a mix of paper notes, sticky markers, memory, and generic notes apps, with nothing consistent.

The insight: progress tracking for crochet is not a calendar or a to-do list. It is a row counter tied to a specific pattern — and the moment the app covers that specific, narrow job, the whole class of mid-project mistakes goes away.

## User & Persona

**Primary persona:** A crochet enthusiast (the developer, initially). Works on one or more projects simultaneously. Picks up and puts down a project across days or weeks. Needs to know, instantly and reliably, exactly which row of which pattern they were on — without having to decode a note or trust their memory.

The critical moment: opening a project bag after a gap and needing to know "where was I?" before a single stitch is made.

## Success Criteria

### Primary
- User can create a project, add a named element, paste a plain-text pattern, and the app displays it as a list of rows.
- User can tap a row to mark it done; a visual indicator (green mark / highlight) appears immediately.
- Progress persists automatically — re-opening the app restores the exact marked state with no manual save.

### Secondary
- A project can hold multiple independently-tracked named elements (e.g., "body", "sleeves", "hat"), each with its own pattern and row progress.

### Guardrails
- Progress must never be lost on app close, crash, or page refresh — row marks are written immediately on tap, not on a deferred save.

## Access Control

Single user with an account. The user signs up and logs in with email + password (or a magic link). Each user's projects and progress are stored server-side and synced across their devices — opening the app on phone and laptop shows the same data.

The app caches data locally so it remains fully usable offline; changes are queued and synced automatically when a connection is restored.

No role separation — flat single-user model per account. No admin, no shared projects, no team workspaces.

## Timeline acknowledgment

Acknowledged on 2026-05-21: ~3.5-week MVP requires sustained after-hours dedication across roughly a month, balancing scope (account-based cloud sync, local caching, responsive layout for laptop + phone) against the July 5th target. User accepted the trade-off in exchange for solving the phone/laptop data split. PWA install and dedicated mobile UX polish were deferred from v1 to trim ~0.5 weeks from the original 4-week estimate. Fallback dates (2026-08-10, 2026-09-14) remain if the work runs long.
