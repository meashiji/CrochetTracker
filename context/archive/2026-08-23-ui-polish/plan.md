# UI Polish — Design Tokens + Component System + Accessibility + Responsive Cleanup

## Overview

Introduce a design token foundation, unify component styles with accessible interactive states, clean up CSS architecture (critical CSS duplication, breakpoint system), and migrate all pages to the new system — with explicit visual approval gates at each phase.

## Current State Analysis

- **CSS**: single `app/static/styles.css` (485 lines) + inline critical styles in `base.html` (~70-75% curated subset, not verbatim; `.brand-mark` diverges: inline = 64×64 transparent vs styles.css = 48×48 gradient + inset shadow)
- **Tokens**: only 10 color tokens in `:root`; no spacing, typography, radius, elevation scales
- **Components**: 7 button selectors in styles.css (.btn, .btn-outline, button[type="submit"], .auth-card-centered button[type="submit"], .nav-links button, .stitch-panel-close) + 4 button-like selectors in template <style> blocks (.icon-button, .repeat-stepper, .row-toggle, .editor-toggle — each template defines its own conflicting .icon-button); divergent inputs; coherent card/panel family (`.panel` base); no focus-ring system, no `:disabled` styles, no skip link
- **Accessibility**: custom widgets have ARIA; forms lack `for`/`id` pairing, live regions; no skip link; no focus indicators
- **Responsive**: 2 ad-hoc breakpoints (760px, 520px), desktop-first; touch targets mostly <44×44px
- **Performance**: critical CSS duplicates ~3.5KB on every response; no minification/build step
- **Templates**: 16 HTML template files (14 pages + `base.html` layout + `_row.html` partial) across `base.html`, `index.html`, `projects/*`, `auth/*`, `500.html`, `stitches/_panel.html`; 3 templates also contain embedded `<style>` blocks (505 lines: list.html 68, detail.html 118, element_detail.html 319) with conflicting `.icon-button` rules (3 definitions), hardcoded state colors (`#16a34a`, `#b45309`, `#dc2626`, etc.) bypassing `:root` palette, plus 11 inline `style=""` attributes

## Desired End State

- **Tokens**: complete system (spacing 4px base, typography scale, semantic color roles with on-colors ≥4.5:1, radius scale, elevation steps) in `tokens.css` imported by `styles.css`
- **Components**: unified button/input/card variants consuming tokens; `:focus-visible` focus-ring system; `:disabled` styles; skip link; all touch targets ≥44×44px; ARIA complete on forms
- **CSS Architecture**: critical CSS removed, `styles.css` preloaded; breakpoint tokens (`--bp-*`); mobile-first media queries; global `overflow-x` guard
- **Pages**: all 14 templates migrated to tokens/components; WCAG AA contrast via token on-colors; visual approval at each phase gate

### Key Discoveries

- Spacing/typography/radius/elevation: **zero systematization** (magic numbers everywhere) — tokens are prerequisite
- Focus states: **entirely missing** — accessibility regression (WCAG AA 2.4.7)
- Critical CSS: **80% verbatim duplicate** of styles.css — remove + preload
- Card/panel family: already coherent (`.panel` base) — extend, don't reinvent
- Color tokens: exist but incomplete — need destructive/success/warning/on-* pairs

## What We're NOT Doing

- No build step (Vite/esbuild) — raw CSS with `@import` + preload
- No page-by-page WCAG audit — trust token on-colors ≥4.5:1
- No utility-first / Tailwind-style classes — keep semantic BEM-ish classes
- No container queries — viewport media queries only
- No JavaScript framework — stays Jinja2 + HTMX + vanilla JS
- No new HTML structure — only CSS/class changes

## Implementation Approach

Four sequential phases. Each phase ends with a **visual approval gate**: you review the changes in browser (dev server) and give explicit "OK" before next phase starts.

## Critical Implementation Details

- **Gate enforcement**: Phase N+1 does not start until you confirm "OK" on Phase N visual result
- **Big bang migration** (Phase 4): single PR migrates all 14 templates; CI must pass
- **Token-driven everything**: no hardcoded values in `styles.css` after Phase 1
- **Focus-ring**: single token-driven `:focus-visible` rule; no per-component overrides
- **Touch targets**: global `min-height: 44px; min-width: 44px` on interactive elements
- **Skip link**: standard fixed top-left, visible on `:focus`, targets `<main id="main">`

---

## Phase 1: Design Tokens

### Overview

Create `tokens.css` with complete token system (spacing, typography, color roles, radius, elevation, focus-ring). Import in `styles.css`. Refactor `styles.css` to consume tokens exclusively (no hardcoded values remain). **No visual changes yet** — tokens are not yet used by components.

### Changes Required:

#### 1. `app/static/tokens.css` (new file)

**File**: `app/static/tokens.css`

**Intent**: Define complete design token system as CSS custom properties.

**Contract**: Export tokens in these categories:
- **Spacing**: `--space-1`..`--space-10` (4px base: 4, 8, 12, 16, 20, 24, 28, 32, 36, 40px)
- **Typography**: `--font-family-base`, `--font-size-display`..`--font-size-caption`, `--line-height-tight`..`--line-height-relaxed`, `--font-weight-normal`..`--font-weight-bold`
- **Color roles**: existing 10 + `--color-destructive`, `--color-destructive-on`, `--color-success`, `--color-success-on`, `--color-warning`, `--color-warning-on`, `--color-on-primary`, `--color-on-surface`, `--color-on-background`, `--color-on-muted`
- **Radius**: `--radius-sm` (4px), `--radius-md` (8px), `--radius-lg` (12px), `--radius-xl` (16px), `--radius-2xl` (20px), `--radius-full` (999px)
- **Elevation**: `--shadow-1`..`--shadow-4` (step scale from current single shadow)
- **Focus ring**: `--focus-ring-color`, `--focus-ring-width` (2px), `--focus-ring-offset` (2px)
- **Breakpoints**: `--bp-sm` (480px), `--bp-md` (760px), `--bp-lg` (1024px), `--bp-xl` (1280px)
- **Touch target**: `--touch-target-min` (44px)

#### 2. `app/static/styles.css` (modify)

**File**: `app/static/styles.css`

**Intent**: Import tokens; replace all hardcoded values with token references.

- Line 1: `@import "tokens.css";`
- Every numeric value (padding, margin, gap, font-size, line-height, border-radius, box-shadow, color) replaced by `var(--token-name)`
- No raw numbers/colors remain except `0` and `100%`

#### 3. `app/templates/base.html` (modify)

**File**: `app/templates/base.html`

**Intent**: Remove inline critical styles; add preload for styles.css.

**Contract**:
- Remove `<style id="critical-styles">...</style>` block entirely
- Add before `</head>`:
  ```html
  <link rel="preload" as="style" href="/static/styles.css">
  <link rel="stylesheet" href="/static/styles.css" media="print" onload="this.media='all'">
  ```
- Keep existing `<link rel="stylesheet" href="/static/styles.css">` (now loads async via preload)

### Success Criteria:

#### Automated Verification:
- `grep -r "var(--" app/static/styles.css | wc -l` > 100 (tokens widely used)
- `grep -E ":\s*\d+(px|rem|em)\b" app/static/styles.css` returns only `0` or `100%` (no raw numeric values)
- `grep -c "@import.*tokens.css" app/static/styles.css` == 1
- `grep -c "critical-styles" app/templates/base.html` == 0
- `grep -c 'rel="preload".*styles.css' app/templates/base.html` == 1
- `uv run pytest -q` passes (76 tests)

#### Manual Verification (GATE 1 — Visual Approval):
- [ ] Open dev server (`uv run uvicorn app.main:app --reload`)
- [ ] Verify **no visual change** vs before (tokens not yet used by components)
- [ ] DevTools Network: `styles.css` loads, no inline `<style id="critical-styles">`
- [ ] DevTools Elements: `:root` shows all new tokens
- [ ] **Your approval: "OK — tokens ready, proceed to Phase 2"**

---

## Phase 2: Component System + Accessibility

### Overview

Unify component variants (buttons, inputs, cards) on token base. Add `:focus-visible` focus-ring system, `:disabled` styles, skip link, global touch-target minimum (44×44px), complete ARIA on forms. **First phase with visible changes.**

### Changes Required:

#### 1. `app/static/styles.css` (modify — component layer)

**File**: `app/static/styles.css`

**Intent**: Redefine component styles using tokens; add focus-ring, disabled, touch-target, skip link.

**Contract**:
- **Button base**: `.btn` uses tokens for padding, radius, colors, font; variants `.btn--primary`, `.btn--outline`, `.btn--ghost`, `.btn--icon`, `.btn--sm`, `.btn--lg` as modifiers
- **Input base**: `.form-input`, `.form-textarea`, `.form-select` share padding, radius, border, colors, focus-ring
- **Card/Panel**: `.panel`, `.panel--elevated`, `.panel--interactive` extend `.panel` base with token variants
- **Global focus-ring**: single `:focus-visible` rule using `--focus-ring-*` tokens
- **Global disabled**: `:disabled` + `[aria-disabled="true"]` styles using tokens
- **Global touch target**: `button, a[role="button"], input, select, textarea, [tabindex="0"] { min-height: var(--touch-target-min); min-width: var(--touch-target-min); }`
- **Skip link**: `.skip-link` fixed top-left, visible on `:focus`, targets `#main`
- **Remove duplicate button styles**: consolidate `button[type="submit"]`, `.nav-links button`, `.stitch-panel-close`, `.icon-button`, `.repeat-stepper button`, `.row-toggle` to use base + modifiers

#### 2. `app/templates/base.html` (modify)

**File**: `app/templates/base.html`

**Intent**: Add skip link and `id="main"` on main content.

**Contract**:
- After `<body>`: `<a href="#main" class="skip-link">Przejdź do treści</a>`
- On `<main class="content">`: add `id="main"`

#### 3. Form templates (modify — ARIA completion)

**Files**: `app/templates/auth/*.html`, `app/templates/projects/*.html`

**Intent**: Add explicit `for`/`id` label pairing, `aria-describedby` for errors, `aria-live` regions for htmx swaps.

**Contract**:
- Every `<label>` wrapping `<input>` gets explicit `for="input-id"` + `id="input-id"` on input
- Error messages get `id="error-*"` + `aria-describedby="error-*"` on input
- htmx swap targets get `aria-live="polite"` where appropriate

### Success Criteria:

#### Automated Verification:
- `grep -c ":focus-visible" app/static/styles.css` >= 1
- `grep -c ":disabled" app/static/styles.css` >= 1
- `grep -c "min-height: var(--touch-target-min)" app/static/styles.css` >= 1
- `grep -c "skip-link" app/static/styles.css` >= 1
- `grep -c 'id="main"' app/templates/base.html` == 1
- `grep -c 'for=' app/templates/auth/*.html app/templates/projects/*.html` >= 20 (label pairing)
- `uv run pytest -q` passes (76 tests)

#### Manual Verification (GATE 2 — Visual Approval):
- [ ] Open dev server
- [ ] **Tab through entire app** — every interactive element shows focus-ring
- [ ] **Click Tab → Enter** on buttons/links — works
- [ ] **Shift+Tab** reverse order — works
- [ ] **Mobile viewport** (Chrome DevTools device toolbar): all buttons/links ≥44×44px
- [ ] **Skip link**: press Tab first time → "Przejdź do treści" appears top-left, Enter jumps to main
- [ ] **Disabled states**: submit during form submit → button shows disabled style
- [ ] **Forms**: labels click → focus input; errors announced (aria-live)
- [ ] **Visual diff vs before**: buttons, inputs, cards look consistent; colors from token palette
- [ ] **Your approval: "OK — components look right, proceed to Phase 3"**

---

## Phase 3: Responsive + CSS Architecture

### Overview

Build on Phase 1's critical CSS removal — no inline styles remain; introduce breakpoint tokens, switch to mobile-first media queries, fix touch targets, add global overflow guard. **Layout changes visible on mobile/tablet.**

### Changes Required:

#### 1. `app/static/tokens.css` (modify — breakpoint tokens)

**File**: `app/static/tokens.css`

**Intent**: Add breakpoint tokens (already defined in Phase 1, now used).

**Contract**: `--bp-sm: 480px`, `--bp-md: 760px`, `--bp-lg: 1024px`, `--bp-xl: 1280px`

#### 2. `app/static/styles.css` (modify — responsive layer)

**File**: `app/static/styles.css`

**Intent**: Replace all `@media` with mobile-first using breakpoint tokens; fix touch targets; add overflow guard.

**Contract**:
- **Mobile-first**: base styles = mobile; `@media (min-width: var(--bp-sm))`, `@media (min-width: var(--bp-md))`, etc.
- **Remove** old desktop-first `@media (max-width: 760px)` and `@media (max-width: 520px)`
- **Component adaptations**: topbar, hero, auth-layout, pattern-layout, stitch-grid — all use mobile-first tokens
- **Global overflow guard**: `html, body { overflow-x: hidden; }` (or `.app-shell { overflow-x: hidden; }`)
- **Touch targets**: already global from Phase 2; verify on mobile viewport
- **Fluid typography**: keep `h1 clamp()`; consider extending to other headings

#### 3. `app/static/styles.css` (modify — cleanup)

**File**: `app/static/styles.css`

**Intent**: Remove any remaining duplicate/legacy rules; organize with clear section comments.

### Success Criteria:

#### Automated Verification:
- `grep -c "min-width: var(--bp-" app/static/styles.css` >= 3 (mobile-first breakpoints)
- `grep -c "max-width: 760px" app/static/styles.css` == 0 (no old desktop-first)
- `grep -c "max-width: 520px" app/static/styles.css` == 0
- `grep -c "overflow-x: hidden" app/static/styles.css` >= 1
- `uv run pytest -q` passes (76 tests)

#### Manual Verification (GATE 3 — Visual Approval):
- [ ] Open dev server
- [ ] **Resize viewport** through 320px → 480px → 760px → 1024px → 1440px
- [ ] **Mobile (375px)**: topbar stacks, hero stacks, auth stacks, stitch-grid 1-col, no horizontal scroll
- [ ] **Tablet (768px)**: topbar horizontal, hero 2-col, auth 2-col, stitch-grid 2-col
- [ ] **Desktop (1024px+)**: full layout, stitch-grid 2-col (or 4-col if designed), comfortable spacing
- [ ] **Touch targets** on mobile: all buttons/links ≥44×44px (DevTools device toolbar)
- [ ] **No horizontal scroll** at any viewport width
- [ ] **Your approval: "OK — responsive works, proceed to Phase 4"**

---

## Phase 4: Page Audit & Migration

### Overview

Extract all template `<style>` blocks into `styles.css` (tokenized), remove inline `style=""` attributes, migrate all 16 template files to token/component system in single big-bang PR. Verify token usage, WCAG AA contrast via on-colors, visual consistency. **Final visual approval.**

### Changes Required:

#### 1. Extract template `<style>` blocks into `styles.css`

**Files**:
- `app/templates/projects/list.html` — remove `<style>` block (68 lines: `.icon-button`, `.project-actions`, hover-reveal media queries)
- `app/templates/projects/detail.html` — remove `<style>` block (118 lines: `.icon-button`, `.element-actions`, state colors)
- `app/templates/projects/element_detail.html` — remove `<style>` block (319 lines: `.row-toggle`, `.editor-toggle`, `.repeat-stepper`, `.icon-button`, state colors)

**Intent**: Extract all rules from template `<style>` blocks into `styles.css`, replacing hardcoded values with tokens. Unify conflicting rules (3 `.icon-button` definitions → 1).

**Contract**:
- All extracted rules moved to `styles.css` with token references
- Conflicting selectors unified (e.g., `.icon-button` → single definition with modifiers if needed)
- `<style>` blocks removed from all 3 templates
- 11 inline `style=""` attributes replaced with utility classes or token-driven classes
- No `<style>` blocks remain in any template

#### 2. All templates (modify — token/component migration)

**Files**:
- `app/templates/base.html`
- `app/templates/index.html`
- `app/templates/projects/list.html`
- `app/templates/projects/detail.html`
- `app/templates/projects/element_detail.html`
- `app/templates/projects/element_new.html`
- `app/templates/projects/new.html`
- `app/templates/projects/_row.html`
- `app/templates/auth/signup.html`
- `app/templates/auth/login.html`
- `app/templates/auth/change_password.html`
- `app/templates/auth/magic_link_request.html`
- `app/templates/auth/magic_link_sent.html`
- `app/templates/auth/magic_link_error.html`
- `app/templates/500.html`
- `app/templates/stitches/_panel.html`

**Intent**: Replace all hardcoded classes/styles with token-driven component classes.

**Contract**:
- Every element uses `.btn` + modifier, `.form-input`, `.panel` + modifier, etc.
- No inline `style=""` attributes remain
- No hardcoded colors/padding/radius in templates
- ARIA complete: labels paired, live regions on htmx swaps, landmarks (`<main id="main">`, `<nav>`, `<header>`, `<aside>`)

#### 2. `app/static/styles.css` (modify — final cleanup)

**File**: `app/static/styles.css`

**Intent**: Remove any now-unused legacy rules; ensure only token-driven rules remain.

### Success Criteria:

#### Automated Verification:
- `grep -r "style=" app/templates/` == 0 (no inline styles)
- `grep -r "#[0-9a-fA-F]\{3,6\}" app/templates/` == 0 (no hex colors in templates)
- `grep -r "padding:[^v]" app/templates/` == 0 (no raw padding in templates)
- `grep -c "<style>" app/templates/projects/list.html app/templates/projects/detail.html app/templates/projects/element_detail.html` == 0 (no template <style> blocks)
- `uv run pytest -q` passes (76 tests)
- `grep -c "var(--color-.*-on-" app/static/styles.css` >= 6 (on-colors used)

#### Manual Verification (GATE 4 — Final Visual Approval):
- [ ] Open dev server
- [ ] **Walk every page**: `/`, `/projects/`, `/projects/new`, `/projects/<id>`, `/projects/<id>/elements/new`, `/projects/<id>/elements/<id>`, `/auth/signup`, `/auth/login`, `/auth/change-password`, `/auth/magic-link*`, 500 page (trigger error), stitch panel
- [ ] **Consistency check**: buttons same height/radius/colors; inputs same; cards same; focus-ring same everywhere
- [ ] **Color palette**: only token colors used (no stray hex)
- [ ] **Contrast**: spot-check text/background pairs — all readable
- [ ] **Stitch panel**: opens, focuses close button, Esc closes, click outside closes, mobile 1-col
- [ ] **Performance**: Network tab — no inline critical styles, `styles.css` loads once
- [ ] **Your final approval: "OK — UI polish complete"**

---

## Testing Strategy

### Unit/Integration Tests (automated):
- Existing pytest suite (76 tests) must pass at every gate
- No new unit tests required — visual gates are primary verification

### Manual Testing (per gate):
- Defined in each phase's "Manual Verification (GATE N)"

---

## Performance Considerations

- Phase 1: critical CSS removal → ~3.5KB less per response
- Phase 3: mobile-first CSS → no desktop styles downloaded on mobile
- No build step → no minification (~14KB vs ~8KB gzipped acceptable for this scale)

---

## Migration Notes

- Big bang migration (Phase 4): single PR, all templates at once
- If regression: `git revert <migration-commit>` restores previous CSS/templates
- Tokens remain backward-compatible during migration (old classes still work until replaced)

---

## References

- Frame brief: `context/changes/ui-polish/frame.md`
- Source files: `app/static/styles.css`, `app/templates/base.html`, `app/templates/projects/*.html`, `app/templates/auth/*.html`, `app/templates/stitches/_panel.html`

---

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Design Tokens

#### Automated
- [x] 1.1 Create `app/static/tokens.css` with complete token system — e40c3be
- [x] 1.2 Refactor `app/static/styles.css` to `@import tokens.css` and consume tokens exclusively — e40c3be
- [x] 1.3 Remove inline critical styles from `base.html`; add preload for `styles.css` — abe29a6
- [x] 1.4 Full test suite passes: `uv run pytest -q` (76 passed) — e40c3be

#### Manual
- [x] 1.5 **GATE 1**: No visual change; tokens visible in DevTools; preload works — **Your approval required**

### Phase 2: Component System + Accessibility

#### Automated
- [x] 2.1 Unify button/input/card variants on tokens; add focus-ring, disabled, touch-target, skip link — 3f37aaa
- [x] 2.2 Add skip link + `id="main"` to `base.html`; complete ARIA on forms — 3f37aaa
- [x] 2.3 Full test suite passes: `uv run pytest -q` (76 passed) — 3f37aaa

#### Manual
- [x] 2.4 **GATE 2**: Focus-ring works, Tab navigation, skip link, touch targets ≥44px, disabled states, form ARIA — approved by user 2026-09-02

### Phase 3: Responsive + CSS Architecture

#### Automated
- [x] 3.1 Mobile-first breakpoints using `--bp-*` tokens; remove old desktop-first queries — ca4e618 (literal bp values in `@media`; custom properties don't substitute there)
- [x] 3.2 Global overflow-x guard; verify touch targets on mobile — ca4e618
- [x] 3.3 Full test suite passes: `uv run pytest -q` (76 passed) — ca4e618 (77 passed)

#### Manual
- [x] 3.4 **GATE 3**: Viewports 320→1440px work; no horizontal scroll; mobile layouts correct — approved by user 2026-09-02

### Phase 4: Page Audit & Migration

#### Automated
- [x] 4.1 Extract template `<style>` blocks into `styles.css` (tokenized); unify conflicting selectors; remove 11 inline `style=""` attributes — 08583d9
- [x] 4.2 Migrate all 16 templates to token/component classes; complete ARIA — 08583d9
- [x] 4.3 Remove unused legacy CSS; verify token-only usage; no `<style>` blocks remain — 08583d9
- [x] 4.4 Full test suite passes: `uv run pytest -q` (75 passed) — 08583d9

#### Manual
- [x] 4.5 **GATE 4**: All pages consistent, contrast OK, stitch panel works, performance clean — approved by user 2026-09-03