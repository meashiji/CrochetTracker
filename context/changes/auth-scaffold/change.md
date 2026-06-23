---
change_id: auth-scaffold
title: Auth scaffold
status: impl_reviewed
created: 2026-06-13
updated: 2026-06-14
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

- Phase 4 addendum: when building `app/auth/mail.py`, also add `MAIL_FROM_NAME` (e.g. "CrochetTracker") to the `ConnectionConfig` and `app/config.py`, so outgoing magic-link emails show a friendly sender name instead of the raw Gmail address. `MAIL_FROM` itself stays the actual `@gmail.com` address.

- **Plan amendment (Phase 3 review, F3)**: `/auth/login` no longer shows a distinct "This account has no password set..." message for magic-link-only accounts — it now returns the generic "Invalid email or password." for that case too, to avoid account-enumeration via the login form. This intentionally deviates from the Phase 3 contract's original wording.

- **Phase 4 addendum**: consider a two-step login flow (ask for email first, then show password field or magic-link option depending on account type), Notion/Slack-style. Raised during Phase 3 review triage; deferred to Phase 4 planning — would also affect the `/auth/login` form shape from Phase 3.

- **Future possibility (F6, accepted as-is for now)**: add CSRF tokens to auth/state-changing forms if the threat model changes (e.g. multi-user data sharing, payments). Currently `SessionMiddleware(same_site="lax")` is considered sufficient — revisit before such a change ships.

- **Plan amendment (Phase 4 review, F2)**: `POST /auth/magic-link` no longer get-or-creates a user. It only sends a magic link if the email already exists in the DB; unknown emails silently return the same "check your email" page. Magic link is login-only, not a registration path. This eliminates phantom account creation and matches the "if there is an account connected to this email" UX pattern. The plan's stated intent was get-or-create; this intentionally deviates from it.
