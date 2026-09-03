# UI Polish — Plan Brief

> Full plan: `context/changes/ui-polish/plan.md`
> Frame brief: `context/changes/ui-polish/frame.md`

## What & Why

Aplikacja ma własny CSS ale bez systemu tokenów, z duplikowanym critical CSS, bez focus-ringów, z drobnymi touch-targetami. Użytkownik chce "visual design pass" ale **decyduje o każdej zmianie wizualnej** — plan ma 4 fazy z bramkami zatwierdzania.

## Starting Point

- `styles.css` 485 linii + inline critical styles (80% duplikat) w `base.html`
- 10 tokenów kolorów w `:root`; brak spacing/typo/radius/elevation
- 9+ wariantów przycisków, brak focus-ring, brak `:disabled`, brak skip link
- 2 ad-hoc breakpoints (760/520px), desktop-first; touch targets <44px
- 16 plików HTML template'ów (14 stron + base.html layout + _row.html partial); 3 z nich zawierają `<style>` bloki (505 linii)

## Desired End State

Pełny system tokenów (spacing 4px base, typo scale, color roles z on-colors ≥4.5:1, radius, elevation), ujednolicone komponenty z focus-ring/disabled/touch-target/skip-link, mobile-first responsive, critical CSS usunięty + preload, wszystkie 14 stron zmigrowanych — **każda faza zatwierdzona wizualnie przez Ciebie**.

## Key Decisions Made

| Decision | Choice | Why | Source |
|----------|--------|-----|--------|
| Token file | `tokens.css` + `@import` | Separation of concerns, czystsze PR | Plan |
| Button variants | Pozostaw warianty, ujednolic stany | Minimalna zmiana HTML, token-driven stany | Plan |
| Focus ring | Token-driven (`--focus-ring-*`) | Jedno miejsce zmiany, WCAG AA | Plan |
| Critical CSS | Usuń + preload | Zero duplikacji, proste, cache'owalne | Plan |
| Build step | Raw CSS (bez Vite) | Zero zależności, prostszy stack | Plan |
| Migracja | Big bang (jeden PR) | Szybsze zakończenie, spójny stan | Plan |
| WCAG audit | Tylko tokeny z on-colors 4.5:1 | Szybsze, system chroni przyszłość | Plan |
| Touch targets | `min-height: 44px` globalnie | Gwarancja WCAG AA 2.5.5 | Plan |
| Skip link | Standardowy (fixed, `:focus`, `#main`) | WCAG AA 2.4.1, standard | Plan |

## Scope

**In scope:**
- `tokens.css` + refactor `styles.css` na tokeny
- Focus-ring, disabled, touch-target (44px), skip link, ARIA forms
- Mobile-first breakpoints (`--bp-*`), usuwanie critical CSS, overflow-x guard
- Ekstrakcja `<style>` bloków z 3 template'ów do `styles.css` (tokenizacja)
- Migracja 16 plików template'ów (big bang), usunięcie 11 inline `style=""`, audit kontrastu przez tokeny

**Out of scope:**
- Build step (Vite/esbuild), minifikacja
- Utility-first / Tailwind classes
- Container queries
- Page-by-page WCAG audit (axe/lighthouse)
- Nowa struktura HTML / JavaScript framework

## Architecture / Approach

```
Phase 1: Tokens (fundament)          → GATE 1: no visual change
Phase 2: Components + A11y           → GATE 2: focus-ring, Tab, skip, touch
Phase 3: Responsive + CSS cleanup    → GATE 3: 320-1440px, no h-scroll
Phase 4: Migration (big bang)        → GATE 4: final sign-off
```

Tokeny w `tokens.css` → `@import` w `styles.css` → komponenty konsumują tokeny → templates używają komponentów.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|-------|------------------|----------|
| 1. Design Tokens | Complete token system (spacing, typo, color roles, radius, elevation, focus-ring, breakpoints, touch-target) in `tokens.css`; `styles.css` refactored; critical CSS removed | Tokens not yet used — visual gate confirms no regression |
| 2. Components + A11y | Unified button/input/card variants; `:focus-visible` ring; `:disabled`; skip link; global 44px touch target; ARIA forms | First visible changes — must match your vision |
| 3. Responsive + CSS | Mobile-first `@media (min-width: var(--bp-*))`; overflow-x guard; touch targets verified | Layout shifts on mobile/tablet — must feel right |
| 4. Page Migration | All 14 templates migrated to tokens/components; WCAG AA via on-colors; final cleanup | Big bang — single PR, rollback if needed |

**Prerequisites:** dev server (`uv run uvicorn app.main:app --reload`), browsers (Chrome/Firefox + DevTools device toolbar)

**Estimated effort:** ~4-6 sessions across 4 phases (each phase ends with your visual approval)

## Open Risks & Assumptions

- **Big bang migration** — if regression slips through, rollback is full revert; CI must be solid
- **Token values** — you approve exact numbers/colors in Gate 1; wrong values propagate everywhere
- **Focus-ring design** — token-driven single rule; if you want per-component variation later, refactor needed
- **No build step** — raw CSS @import blocks parsing slightly; acceptable for this scale
- **WCAG via tokens only** — assumes token on-colors cover all real usage; spot-check in Gate 4

## Success Criteria (Summary)

- [ ] Gate 1: Tokens ready, zero visual change
- [ ] Gate 2: Focus-ring, skip link, Tab nav, 44px targets, disabled states, form ARIA — approved
- [ ] Gate 3: 320→1440px responsive, no horizontal scroll, mobile layouts — approved
- [ ] Gate 4: All 14 pages consistent, contrast OK, stitch panel works, performance clean — **final sign-off**
- [ ] All automated tests pass (76/76) at every gate