---
change_id: stitch-reference-panel
title: Stitch reference panel US notation
status: in_progress
created: 2026-08-21
updated: 2026-08-23
archived_at: null
---

## Notes

stitch-reference-panel US notation + 8 US crochet stitches: chain, single crochet, double crochet, half double crochet, treble crochet, magic ring, increase, decrease

2026-08-23: re-planned for the real stack (FastAPI + Jinja2 + HTMX); dead JSX
artifacts removed. Phase 1+2 implemented and verified (pytest 76 passed +
headless-browser smoke).

2026-08-23 (UX revision): converted centered modal → non-modal popover
anchored under the header button. No backdrop, no focus trap, fixed position
stays visible while scrolling the pattern. Panel width ≤480px, 2-col grid
(1-col ≤520px). Uncommitted.
