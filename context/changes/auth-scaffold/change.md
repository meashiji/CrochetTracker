---
change_id: auth-scaffold
title: Auth scaffold
status: impl_reviewed
created: 2026-06-13
updated: 2026-06-13
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

- Phase 4 addendum: when building `app/auth/mail.py`, also add `MAIL_FROM_NAME` (e.g. "CrochetTracker") to the `ConnectionConfig` and `app/config.py`, so outgoing magic-link emails show a friendly sender name instead of the raw Gmail address. `MAIL_FROM` itself stays the actual `@gmail.com` address.
