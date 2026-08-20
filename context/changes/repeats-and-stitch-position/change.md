---
change_id: repeats-and-stitch-position
title: Repeat element tracking + stitch position recording
status: implemented
created: 2026-08-01
updated: 2026-08-20
archived_at: null
---

## Notes

Roadmap slice S-03 (context/foundation/roadmap.md). PRD refs: FR-003, FR-010.
Prerequisite S-02 (row-marking-and-persistence) is done and archived.

User can set a repeat count on an element (e.g., ×3) and track each repetition
with its own independent row progress; user can record the specific stitch
position they stopped at within an in-progress row (e.g., "stopped at stitch 14").

Known constraint from S-02 planning: `repeat_count` is hard-coded to 1 at element
creation (app/routes/projects.py), and S-02's toggle route resolves "the" single
ElementRepetition via `.scalar_one()` — both will need revisiting here. The
RowState.stitch_position column exists but is unused so far.

- **Scope addition (user, mid-Phase-1)**: show the repeat count as a `×N` badge
  per element in the project detail element list (`projects/detail.html`). The
  element detail page already displays `×N` via the Phase 1 stepper in the title row.
