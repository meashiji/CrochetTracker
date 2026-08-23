# Stitch Reference Panel Implementation Plan

> **2026-08-23 re-plan**: the original plan assumed a React/JSX frontend that
> does not exist in this repo — the app is FastAPI + Jinja2 + HTMX (see
> `context/foundation/tech-stack.md`). Untracked JSX artifacts
> (`app/components/*.jsx`, `app/stitches.js`) from the earlier attempt are
> dead code and get deleted. The plan below targets the real stack.

## Overview

Add a stitch reference panel to the app showing 8 basic crochet stitches in US notation with descriptions. This panel will help users identify stitches by name and symbol, supporting the app's core goal of knowing instantly which row to start from without notes, counting, or memory.

## Current State Analysis

- The frontend is server-rendered: Jinja2 templates (`app/templates/`) + HTMX (`app/static/js/htmx.min.js`) + one stylesheet (`app/static/styles.css`). No JS build step, no React.
- The app shell/header lives in `app/templates/base.html` (topbar with `.nav-links`), rendered on every page, logged in or not.
- Routes follow the pattern: `APIRouter` per domain in `app/routes/`, each with its own `Jinja2Templates(directory="app/templates")`, registered in `app/main.py`.
- Auth: `AuthRedirectMiddleware` redirects every non-public path to `/auth/login` when no session (`app/auth/middleware.py:_PUBLIC_PATHS`).
- No existing stitch glossary or reference material. 8 stitches to include: chain, single crochet, double crochet, half double crochet, treble crochet, magic ring, increase, decrease.

## Desired End State

A user can open a reference panel from a "Stitch reference" button in the app header showing 8 basic crochet stitches with US abbreviation, name, and description. **UX revision 2026-08-23 (user)**: the panel is a non-modal popover bubble anchored under the trigger button — not a centered modal — so the pattern stays visible and interactive next to it (no scroll-away, no backdrop covering the page). It floats fixed while the pattern scrolls, closes via close button, Escape, or the toggle, and is responsive (4-column grid on desktop, 2 on mobile). The fragment route is public (read-only reference, no auth barrier), consistent with the plan-brief decision.

## What We're NOT Doing

- UK notation (out of scope for v1 — tracked as future enhancement)
- Interactive stitch counter or row-tracking functionality (covered by S-02/S-03)
- Dynamic glossary content loading or user-contributed entries
- Full pattern library or project-specific stitch customization
- Any database model, migration, or Alembic change — content is a static Python constant

## Implementation Approach

1. **Stitch data** — `app/stitches.py`: typed constant `STITCHES` (tuple of `Stitch` TypedDicts) with `name`, `symbol`, `description`, `category`.
2. **Fragment route** — `app/routes/stitches.py`: `GET /stitches/panel` renders `templates/stitches/_panel.html` with `STITCHES`. Registered in `app/main.py`. Path added to `_PUBLIC_PATHS` (read-only, no user data).
3. **Header toggle** — button in `base.html` `.nav-links`; hidden container `#stitch-panel`; `app/static/js/stitch-panel.js` handles open/close: first click loads the fragment via `htmx.ajax`, later clicks toggle; Escape and outside click close; focus moves to the close button on open and back to the trigger on close; `aria-expanded` kept in sync.
4. **Styling** — appended to `app/static/styles.css` (single-stylesheet convention): overlay, dialog card, responsive stitch grid (2 cols mobile, 4 cols desktop), uses existing CSS custom properties.

## Critical Implementation Details

- **Panel placement**: non-modal popover bubble anchored under the "Stitch reference" header button; **no backdrop, no modal focus trap** — the pattern stays fully visible and interactive underneath.
- **Data structure**: Python constant — no database model needed for static content.
- **Auth**: `/stitches/panel` in `_PUBLIC_PATHS` so the button works on logged-out pages (`/`, `/auth/login`) without an HTMX redirect-into-panel glitch.
- **Accessibility**: `role="dialog"` (non-modal, no `aria-modal`); Escape closes; focus to close button on open, back to trigger on close; `aria-expanded` synced.
- **Behavior**: first click loads fragment via `htmx.ajax`, later clicks toggle; Escape and close button close; **click outside does NOT close** (user can interact with the pattern while the reference stays open).
- **Scrolling**: panel uses `position: fixed` with computed top/left from the trigger button; stays pinned while the page scrolls.
- **Responsive**: grid is 2 columns by default, 1 column ≤520px; panel width capped at 480px.
- **No migrations needed** — static content, no database changes.

## Phase 1: Stitch Data & Fragment Route

### Overview

Define the 8 stitches as a typed Python constant, add the fragment route and template, and cover the contract with pytest.

### Changes Required:

#### 1. `app/stitches.py` (new file)

**Intent**: Define the 8 stitches as a typed constant shared by route and tests.

**Contract**: Export `Stitch` (TypedDict with `name`, `symbol`, `description`, `category`) and `STITCHES: tuple[Stitch, ...]` with exactly 8 entries covering the US names: chain, single crochet, double crochet, half double crochet, treble crochet, magic ring, increase, decrease.

**Success Criteria**:

- `STITCHES` contains exactly 8 entries, all fields non-empty strings
- Names match the US notation list above
- Importable without side effects

#### 2. `app/routes/stitches.py` + template `app/templates/stitches/_panel.html` (new files)

**Intent**: Serve the panel fragment and render all 8 stitches.

**Contract**: `GET /stitches/panel` returns the fragment with `role="dialog"`, `aria-modal="true"`, a close button, and one entry per stitch showing symbol, name, description. Router registered in `app/main.py`; path added to `_PUBLIC_PATHS` in `app/auth/middleware.py`.

**Success Criteria**:

- `GET /stitches/panel` returns 200 authenticated **and** unauthenticated
- Response contains all 8 stitch names and symbols
- No DB access in the route

#### 3. `tests/test_stitch_reference.py` (new file)

**Intent**: Lock the data contract and fragment route behavior.

**Contract**: Tests for: 8 entries with expected names; fragment returns 200 with all stitches for an anonymous client; header toggle button present on `/`.

## Phase 2: Header Integration & Polish

### Overview

Wire the toggle into `base.html`, add the open/close JS behavior and styling.

### Changes Required:

#### 4. `app/templates/base.html` (modify)

**Intent**: Add the "Stitch reference" button, the panel container, and the script tag.

**Contract**: Button in `.nav-links` with `id="stitch-reference-toggle"`, `aria-expanded="false"`, `aria-controls="stitch-panel"`; empty hidden `div#stitch-panel`; `stitch-panel.js` loaded after htmx.

**Success Criteria**:

- Button renders on every page (base template)
- Page HTML unchanged otherwise; no console/JS load errors

#### 5. `app/static/js/stitch-panel.js` (new file)

**Intent**: Open/close behavior without a framework.

**Contract**: First click loads the fragment via `htmx.ajax` into `#stitch-panel` and opens; subsequent clicks toggle; Escape closes; click outside the panel card closes; focus to close button on open, back to trigger on close; `aria-expanded` synced.

**Success Criteria**:

- Open → close → open works without page reload and without re-fetching after first load
- Escape and outside click close the panel
- Focus lands on the close button when opened

#### 6. `app/static/styles.css` (modify)

**Intent**: Style overlay + dialog + responsive grid consistent with the design system.

**Contract**: Overlay dims background; card uses `--surface`/`--border`/`--shadow`; grid is 2 columns ≤640px, 4 columns on desktop; contrast ≥ 4.5:1 (existing palette text tokens).

**Success Criteria**:

- Panel displays with correct spacing and typography
- Responsive grid adjusts at the breakpoint
- Existing pages visually unchanged

## Testing Strategy

### Automated

- `tests/test_stitch_reference.py`: data contract, public fragment route, header button presence. Run with `uv run pytest tests/test_stitch_reference.py -v`, then full `uv run pytest`.
- E2E (Playwright) not required for this change — behavior is covered by route tests + manual checks below; revisit only if the panel gains dynamic behavior (per `context/foundation/test-plan.md` §"not covered").

### Manual Verification

- Open the panel from header — all 8 stitches display correctly
- Navigate with keyboard (Tab/Escape)
- Mobile view shows 2-column layout
- Panel closes on Escape and click outside
- Button works on a logged-out page (`/`)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Stitch Data & Fragment Route

#### Automated

- [x] 1.1 Define `Stitch` TypedDict + `STITCHES` constant (8 entries) in `app/stitches.py` — 05d4e7c
- [x] 1.2 Create `app/routes/stitches.py` + `app/templates/stitches/_panel.html`; register router in `app/main.py`; add `/stitches/panel` to `_PUBLIC_PATHS` — 05d4e7c
- [x] 1.3 New tests pass: `uv run pytest tests/test_stitch_reference.py -v` (5 passed) — 05d4e7c
- [x] 1.4 Full suite still passes: `uv run pytest` (76 passed) — 05d4e7c

#### Manual

- [x] 1.5 `curl /stitches/panel` returns the fragment with all 8 stitches (no session) — 05d4e7c

### Phase 2: Header Integration & Polish

#### Automated

- [x] 2.1 Toggle button + container + script wired in `app/templates/base.html` — 05d4e7c
- [x] 2.2 `app/static/js/stitch-panel.js`: load-once popover toggle + Escape/close + focus management + **positioning under trigger + fixed-on-scroll + resize reposition** — 05d4e7c
- [x] 2.3 Responsive 2-col grid + fixed popover styles + caret in `app/static/styles.css` (no backdrop, no modal) — 05d4e7c
- [x] 2.4 Full suite still passes: `uv run pytest` (76 passed) — 05d4e7c

#### Manual

> Verified via headless Chromium (Playwright) smoke run on a live `uvicorn` instance, not a human pass.

- [x] 2.5 Open popover from header — all 8 stitches display correctly in 2-col grid — 05d4e7c
- [x] 2.6 Navigate with keyboard (Escape); focus to close button on open — 05d4e7c
- [x] 2.7 Mobile ≤520px → 1 column; desktop 2 columns; panel ≤480px wide — 05d4e7c
- [x] 2.8 Panel closes on Escape/close button/toggle; reopens without reload (fragment fetched once); **stays fixed while page scrolls**; **outside click does NOT close** — pattern remains interactive — 05d4e7c
- [x] 2.9 Button works on logged-out `/` page — 05d4e7c

## References

- Related research: none (fresh implementation)
- Similar implementation: row-state fragment rendering in `app/routes/projects.py` (HTMX fragment pattern)
- Design notes: US notation per earlier decisions; 8 stitches chosen as foundational set
