# Stitch reference panel — Plan Brief

> Full plan: `context/changes/stitch-reference-panel/plan.md`
> Frame brief: none
> Research: none

## What & Why

We're adding a stitch reference panel to the CrochetTracker app showing 8 basic crochet stitches in US notation with descriptions. This supports the product hypothesis that covering this single narrow job (instantly knowing which row to start from) eliminates mid-project mistakes. The panel gives users a quick way to identify stitches they encounter in their patterns.

## Starting Point

The app currently has no stitch reference material. Users lose track of row position when returning to a project — a reference panel with basic stitches is the minimal addition to address this. The app already has auth scaffold, project display, and row-marking (S-02/S-03) built; this panel fits in the existing auth shell as a read-only reference component.

## Desired End State

A user can open a reference panel from the app header showing 8 basic crochet stitches with US notation, symbols, and descriptions. The panel is responsive (full on desktop, condensed on mobile), accessible (ARIA labels, keyboard navigation), and reads as part of the app — no external links or accounts needed. When opened, the user can quickly identify a stitch by name and symbol.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| -------- | ------ | ---------------- | ------ |
| Notation US | US only | Matches v1 scope; US is most widely documented internationally | Plan decision (this session) |
| 8 stitches | chain, sc, dc, hdc, tr, magic ring, inc, dec | Foundational set; covers >90% of typical projects | Plan decision (this session) |
| Panel placement | Header right action | Consistent with existing app patterns; minimal UI change | Existing app design |
| Read-only, no auth barrier | Panel accessible without login | Reference material should be available to all logged-in users; auth already required for app entry | Auth scaffold dependency |

## Scope

**In scope**: 8 US-notation stitches with descriptions; panel in app header; responsive design; ARIA accessibility.

**Out of scope**: UK notation (future v1 enhancement); interactive row counting (S-02/S-03); dynamic/user-contributed content; pattern library.

## Architecture / Approach

A simple JS constant array embedded in the app, rendered as a panel component in the header. No new database model, no API routes, no migrations. The panel is pure presentation — data is hardcoded. This keeps the change lightweight and fast to implement while still delivering value.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| ----- | ---------------- | -------- |
| 1. Stitch Data & Model | `STITCHES` constant + Panel component skeleton | Data structure design |
| 2. Panel Integration & Polish | Header button + styling + accessibility | CSS/responsive details |

**Prerequisites**: Auth scaffold (S-02/S-03 already done), header component exists.

**Estimated effort**: ~2 sessions across 3 phases (data model, integration, polish).

## Open Risks & Assumptions

- **US-only notation**: Decision made; UK will be tracked for v2. If v1 users request UK, it can be added as a separate panel.
- **8 stitches sufficient**: Covers >90% of typical projects; if users need more, future expansion is straightforward.
- **No auth barrier**: Panel must be accessible to any logged-in user; must not block app usage.

## Success Criteria (Summary)

- Panel opens from header button
- All 8 US-notation stitches display with correct symbol and description
- Panel is responsive (desktop + mobile)
- Keyboard accessible (Tab/Escape)
- No JavaScript errors on mount or panel interaction

## Architecture / Approach

> Corrected 2026-08-23: the app is FastAPI + Jinja2 + HTMX (no React/JSX).

**Data**: `app/stitches.py` exports `STITCHES` constant — 8 TypedDict entries with `name`, `symbol`, `description`, `category`.

**UI**: `GET /stitches/panel` renders `app/templates/stitches/_panel.html` fragment; `app/templates/base.html` header gets a toggle button + container; `app/static/js/stitch-panel.js` handles open/close.

**No database**: Static content — no migrations, no schema changes.

## Architecture / Approach (diagram text)

```
base.html topbar (.nav-links)
  ↑
  [Stitch reference button]  -- htmx.ajax (first open) -->
  ↓
#stitch-panel container <-- GET /stitches/panel fragment
  ↑
STITCHES constant (app/stitches.py)
```

## Key Decisions (table continued)

| Decision | Choice | Why (1 sentence) | Source |
| -------- | ------ | ---------------- | ------ |
| No database | Static content | Keeps change lightweight; no migration needed | Plan decision |
| US notation only | v1 scope | Faster delivery; UK tracked for v2 | Plan decision |
| Header placement | Consistent with app | Minimal UI change, follows existing patterns | Existing app design |

