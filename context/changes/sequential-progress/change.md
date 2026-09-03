---
change_id: sequential-progress
title: Enforce sequential row & repeat progress (crochet ordering)
status: implemented
created: 2026-09-03
updated: 2026-09-03
archived_at: null
---

## Notes

User-reported logic change: crochet rows are sequential — you can't do row 5 before
row 1, and you can't complete rep 2 while rep 1 still has work. Currently any row in
any rep can be marked done independently. Enforce ordering constraints.

Framing in progress (`frame.md`). See session notes for confirmed semantics.
