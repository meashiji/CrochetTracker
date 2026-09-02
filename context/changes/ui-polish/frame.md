# Frame Brief: P-01 UI Polish — Design Tokens + Component System + Accessibility + Responsive Cleanup

> Framing step before /10x-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed.

## Reported Observation

Aplikacja ma własny CSS (`app/static/styles.css` + inline critical styles w `base.html`), CSS custom properties dla kolorów, podstawowy layout. Użytkownik chce "visual design pass — typografia, kolory, odstępy, responsive layout; no raw browser-default styling" oraz system design tokens do przyszłych featureów.

## Initial Framing (preserved)

- **User's stated cause or approach**: "P-01 z roadmapy — przejść po UI i dopracować wygląd (typografia, paleta, spacing, breakpointy)"
- **User's proposed direction**: Zrobić plan na P-01 ui-polish.
- **Pre-dispatch narrowing**: Mix znanych problemów + audyt od zera; design tokens + istniejące strony; priorytet: wszystkie sekwencyjnie (Tokens → Komponenty/a11y → Responsive/CSS cleanup → Audit/migracja).

## Dimension Map

The observation could originate at any of these dimensions:

1. **DESIGN TOKENS / SYSTEM** — brak scentralizowanych tokenów (spacing scale, typo scale, color roles, elevation, radius); wartości "magic numbers" rozrzucone po CSS; trudno zmieniać spójnie.  ← framing użytkownika
2. **KOMPONENTY / WZORCE** — brak biblioteki komponentów (button, card, input, badge, panel); style powielone; stany (hover/focus/active/disabled) nie ujednolicone.
3. **TYPOGRAFIA / HIERARCHIA** — font-family zdefiniowany globalnie, ale skala rozmiarów (h1-h6, body, small, caption) nieusystematyzowana; line-height, font-weight, letter-spacing losowe.
4. **KOLORY / KONTRAST / ROLE** — paleta w :root istnieje, ale role semantyczne (primary, secondary, destructive, success, warning, surface variants, on-colors) nie wyodrębnione; kontrast WCAG AA niezaudytowany.
5. **SPACING / LAYOUT SYSTEM** — padding/margin/gap jako magic numbers; brak spójnej skali (np. 4px base unit); breakpointy: 760px, 520px — czy to system czy przypadkowe?
6. **RESPONSYWNOŚĆ / BREAKPOINTY** — dwa media queries (760px, 520px); topbar/hero/auth-layout na 760px, stitch-grid na 520px; czy to kompletny system breakpointów?
7. **STANY INTERAKTYWNE** — :hover/:focus/:active/:disabled/:focus-visible nie ujednolicone; outline/focus-ring brakuje w wielu miejscach (dostępność klawiaturowa).
8. **AKCESYJNOŚĆ / SEMANTYKA** — aria w panelu stitch, ale inne komponenty (przyciski, linki, formularze) mogą brakujeć focus-ring, labeli, live regions.
9. **PERFORMANCE / CSS ARCHITEKTURA** — inline critical styles w base.html (duplikacja z styles.css); brak minifikacji/bundlinga; @import nie używane.
10. **PRZYSZŁE FEATURES / ROZSZERZALNOŚĆ** — design tokens mają służyć przyszłym featureom; czy plan uwzględnia migration path?

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| **1. Design Tokens: spacing/typo/color roles/radius/elevation** | Spacing: NONE (wszystkie magic numbers: 2,4,6,8,10,12,14,16,18,20,24,28,30,48px); Typo: WEAK (tylko font-family, brak skali h1-h6/caption); Color Roles: STRONG (partial) — 10 tokenów, brak destructive/success/warning/on-colors; Radius: NONE (8 wartości: 999px, 24px, 22px, 20px, 18px, 16px, 14px, 12px); Elevation: NONE (1 cień `--shadow` dla wszystkiego) | 🔴 STRONG |
| **2. Components/States/Accessibility** | Button variants: WEAK (9+ stylów, brak bazy, duplikat .btn vs button[type=submit]); Input: WEAK (base OK, .row-stitch diverguje); Card/panel: STRONG (spójna rodzina .panel); Focus states: NONE (brak :focus/:focus-visible/focus-ring); Disabled: NONE; ARIA: WEAK (custom widgety OK, formularze bez for/id, brak live regions); Skip links: NONE | 🔴 STRONG |
| **3. Responsive/Breakpoints/Performance** | Breakpoints: WEAK (2 ad-hoc: 760px, 520px; desktop-first; duplikat 760px w 2 plikach); Critical CSS: STRONG (80% werbatim duplikat styles.css w base.html); Minification: NONE; Touch targets (44×44): WEAK (nav, btn, icon-btn, close-btn <44px); Container queries: NONE; Fluid typography: STRONG (h1 clamp) | 🔴 STRONG (CSS cleanup) / 🟡 MEDIUM (responsive) |

## Narrowing Signals

Decisive observations from investigation that narrowed the hypothesis space:

- **Spacing/typography/radius/elevation have ZERO systematization** — not "inconsistent", but *absent*. This forces Phase 1 (Tokens) to be foundational; you cannot refactor components without a token layer first.
- **Focus states are entirely missing** — no `:focus`, `:focus-visible`, focus-ring anywhere. This is an accessibility regression (WCAG AA 2.4.7) and must be addressed in Phase 2 alongside component unification.
- **Critical CSS duplicates ~80% of styles.css** — the inline `<style id="critical-styles">` in base.html is a verbatim subset, not a curated above-the-fold extract. This adds ~3.5KB to every response with zero benefit. Phase 3 must remove or properly extract it.
- **Touch targets mostly <44×44px** — nav links, primary buttons, icon buttons, close buttons all fail mobile baseline. Phase 3 (responsive) must fix this.
- **Color tokens exist but are incomplete** — missing destructive/success/warning/on-* pairs. Phase 1 must complete the semantic color system before components can use it.
- **Card/panel family is already coherent** — `.panel` acts as a base with semantic variants. Phase 2 can extend this pattern rather than invent from scratch.

## Cross-System Convention

- **CSS custom properties in `:root`** — standard pattern in this stack (Jinja/HTMX); aligns with how colors are already done.
- **Single `styles.css` + inline critical fallback** — existing convention; but critical CSS must be *curated*, not *duplicated*.
- **HTMX + server-rendered HTML** — focus-ring and keyboard navigation are non-negotiable (no SPA router to manage focus).
- **No build step currently** — any minification/bundling would require introducing a tool (Vite/esbuild + lightningcss) or accepting raw CSS.

## Reframed (or Confirmed) Problem Statement

> **The actual problem to plan around is**: The UI layer lacks a design token foundation, a unified component system with accessible interactive states, and has a duplicated/uncurated CSS architecture. "Visual design pass" requires four sequential phases: (1) establish design tokens (spacing, typography, color roles, radius, elevation); (2) unify components & implement accessibility (focus-ring, touch targets, ARIA, skip link); (3) clean up CSS architecture (remove critical CSS duplication, introduce breakpoint tokens, fix touch targets, mobile-first media queries); (4) audit & migrate all existing pages to the new system.

The initial framing ("dopracować wygląd") was **incomplete** — it described the surface goal but missed the structural prerequisites (tokens, a11y, CSS cleanup) that evidence shows are necessary first.

## Confidence

- **HIGH** — strong evidence across all three dimensions + matches convention + decisive narrowing signals.

## What Changes for /10x-plan

The plan must be **four sequential phases** (not a single "polish" phase):
1. **Phase 1 — Design Tokens**: expand `:root` with spacing scale (4px base), typography scale, semantic color roles (destructive/success/warning/on-*), radius scale, elevation steps; create `tokens.css` or expand `:root`; refactor `styles.css` to consume tokens exclusively.
2. **Phase 2 — Component System + Accessibility**: unify button/input/card variants on token base; add `:focus-visible` focus-ring system; `:disabled` styles; skip link (`#main`); complete ARIA (label `for`/`id`, live regions for htmx swaps); ensure all touch targets ≥44×44px.
3. **Phase 3 — Responsive + CSS Architecture**: remove inline critical CSS duplication (curated subset or preload); introduce breakpoint tokens (`--bp-*`); mobile-first media queries; fix touch targets; add global `overflow-x` guard; consider build step (Vite + lightningcss) for minification.
4. **Phase 4 — Page Audit & Migration**: walk all templates (index, projects/*, auth/*, 500.html, stitch panel) and migrate to new tokens/components; verify contrast WCAG AA; document token usage for future features.

## References

- Source files: `app/static/styles.css`, `app/templates/base.html`, `app/templates/projects/*.html`, `app/templates/auth/*.html`
- Investigation tasks: TaskCreate IDs `ses_fd1d5f49fffeLTta5hb4Bc0d6v` (tokens), `ses_fd1d5cd7effecLfDv34DpLkb77` (components/a11y), `ses_fd1d5c0e4ffeRKhxBXA3P5IKi4` (responsive/perf)
- Related research: `context/changes/ui-polish/research.md` (to be created by /10x-research if needed)