---
change_id: row-marking-and-persistence
title: Row marking (3 states) + auto-jump + persistence — north star slice
status: implementing
created: 2026-07-09
updated: 2026-07-12
archived_at: null
---

## Notes

North star slice (S-02) per context/foundation/roadmap.md. Prerequisite S-01
(project-and-pattern-display) is done. User marks a row done, closes the app,
returns the next day, and finds it still marked; the view auto-jumps to the
first unmarked row. PRD refs: FR-006, FR-007, US-01. Key open architectural
question flagged in the roadmap: the 100ms NFR on row-state updates may
require HTMX optimistic UI, or a fast enough plain server round-trip — this
is a real decision to make explicit in /10x-plan, not gloss over.
