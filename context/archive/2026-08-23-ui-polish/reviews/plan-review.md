<!-- PLAN-REVIEW-REPORT -->
# Plan Review: UI Polish — Design Tokens + Component System + Accessibility + Responsive Cleanup

- **Plan**: `context/changes/ui-polish/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-28
- **Verdict**: REVISE
- **Findings**: 1 critical, 3 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS ✅ |
| Lean Execution | PASS ✅ |
| Architectural Fitness | WARNING ⚠️ |
| Blind Spots | FAIL ❌ |
| Plan Completeness | WARNING ⚠️ |

## Grounding

16/16 template paths ✓, styles.css ✓, 0/1 tokens.css (not yet created — correct) · 76/76 tests ✓ · brief↔plan ✓

## Findings

### F1 — Template `<style>` blocks: missing from plan entirely, contain conflicting rules and hardcoded hex colors

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; affects Phase 1-4 scope and all automated gates
- **Dimension**: Blind Spots
- **Location**: Current State Analysis (omitted); Phase 4 (scope insufficient)

- **Detail**: Three templates contain embedded `<style>` blocks that the plan does not mention:
  - `projects/list.html` — 68 lines (`.icon-button`, `.project-actions`, hover-reveal media queries)
  - `projects/detail.html` — 118 lines (`.icon-button`, `.element-actions`, state colors `#16a34a`, `#b45309`, `#9e9e9e`)
  - `projects/element_detail.html` — 319 lines (`.row-toggle`, `.editor-toggle`, `.repeat-stepper`, `.icon-button`, state colors `#fff8e1`, `#e9f8ee`, `#dc2626`, `#f0c14b`, `#86d9a6`, `#fff`)

  Combined: **505 lines of CSS in templates**. Issues:
  1. **Conflicting `.icon-button` rules**: each template defines its own variant with different properties (specificity battles documented in template comments)
  2. **Hardcoded hex colors** bypassing `:root` palette — Phase 4's `grep -r "#[0-9a-fA-F]\{3,6\}" app/templates/ == 0` will fail
  3. **11 inline `style=""` attributes** across templates (e.g. `style="color: #a44f62"`) — Phase 4's `grep -r "style=" app/templates/ == 0` will fail
  4. **Button-like selectors** (`.icon-button`, `.repeat-stepper button`, `.row-toggle`, `.editor-toggle`) not mentioned in Current State Analysis

  The plan's claim "No new HTML structure — only CSS/class changes" is contradicted: removing `<style>` blocks requires editing template HTML.

- **Fix A ⭐ Recommended**: Add Phase 4.5 (or merge into Phase 4): Extract all template `<style>` blocks into `styles.css` (tokenized), remove 11 inline `style=""` attributes by adding utility classes, then run Phase 4 migration. Add explicit sub-task to Phase 4 for: "Remove `<style>` blocks from list.html, detail.html, element_detail.html; extract rules into styles.css; replace inline styles with classes."
  - Strength: Completes the CSS architecture cleanup; gates pass; no dangling inline styles.
  - Tradeoff: ~1 extra session for extraction and conflict resolution (3 conflicting `.icon-button` rules need unification).
  - Confidence: HIGH — extraction path is mechanical; the real work is consolidating conflicting rules.
  - Blind spot: None significant — the rules are self-contained in the `<style>` blocks.

- **Decision**: Fixed

### F2 — "9+ button variants" count inflated; key selectors omitted from analysis

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis, Phase 2

- **Detail**: `styles.css` has 7 button-related selectors (`.btn`, `.btn-outline`, `button[type="submit"]`, `.auth-card-centered button[type="submit"]`, `.nav-links button` ×2, `.stitch-panel-close`), not 9+. The remaining variants (`.icon-button`, `.repeat-stepper`, `.row-toggle`, `.editor-toggle`) exist only in template `<style>` blocks (see F1). The plan should note that ~5 button variants live outside `styles.css` in template `<style>` blocks.

- **Fix**: Change Current State Analysis to: "7 button selectors in `styles.css` + 4 button-like selectors in template `<style>` blocks (`.icon-button`, `.repeat-stepper`, `.row-toggle`, `.editor-toggle`) — each template defines its own conflicting `.icon-button`."

- **Decision**: Fixed

### F3 — Critical CSS "80% verbatim duplicate" is not strictly verbatim

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis, Phase 1

- **Detail**: The inline `<style id="critical-styles">` block in `base.html` is a **curated subset** (~70-75%), not a verbatim copy. Notable differences: `.brand-mark` has `width: 64px; height: 64px; background: transparent` inline vs `width: 48px; height: 48px` with gradient + `box-shadow: inset` in `styles.css`. The cleanup still works (Phase 1 removes the inline block), but the "80% verbatim" claim overstates the overlap and understates the brand-mark discrepancy.

- **Fix**: Change "80% verbatim duplicate" to "~70-75% curated subset with divergent `.brand-mark` values (64×64 transparent vs 48×48 gradient + inset shadow). Cleanup: remove inline block entirely, styles.css is authoritative."

- **Decision**: Fixed

### F4 — Phase 3 overview references critical CSS removal as if it's a Phase 3 task

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 — Overview

- **Detail**: Phase 3 Overview says "Remove critical CSS duplication (already done in Phase 1)" which is parenthetically correct but visually suggests it's a Phase 3 action. The detailed "Changes Required" for Phase 3 correctly doesn't include critical CSS removal. This is cosmetic but could confuse the implementer during Phase 3 execution.

- **Fix**: Remove "Remove critical CSS duplication (already done in Phase 1)," from Phase 3 Overview. Replace with: "Build on Phase 1's critical CSS removal — no inline styles remain."

- **Decision**: Fixed

### F5 — Success Criteria grep patterns have edge-case false-positive risk

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 & Phase 4 — Automated Verification

- **Detail**: The grep `"(padding|margin|gap|font-size|radius|shadow|color):[^v]"` has two edge cases: (1) `box-shadow: var(--shadow)` would match because the space after `:` is `[^v]`, producing a false positive; (2) `color: --surface` (no `var()`) would NOT match because `--` starts with `-`, not `[^v]` — a false negative. In practice, after tokenization these are unlikely to misfire, but the pattern is imprecise.

- **Fix**: Use `grep -E "(padding|margin|gap|font-size|radius|shadow|color):\s*[^v(]"` (requires space after colon then a non-`v` non-`(` char) or better, `grep -P "(padding|margin|gap|font-size|radius|shadow|color):\s*(?!(var\())[^v\s]"`. For simplicity: just change the intent to "no hardcoded px/rem/% values remain" and use `grep -E ":\s*\d+px\b"` instead.

- **Decision**: Fixed

### F6 — "14 templates" count in Current State Analysis vs 16 HTML files

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — fix is obvious
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis, Phase 4

- **Detail**: The plan says "14 templates" in Current State Analysis but Phase 4 lists 16 files. The discrepancy: `base.html` (layout, not a page) and `_row.html` (partial, not a standalone page) bring the count to 16 HTML files. Phase 4's file list is correct (16 files); the "14" in Current State Analysis is off.

- **Fix**: Change "14 templates" to "16 HTML template files (14 pages + base.html layout + _row.html partial)" in Current State Analysis and Phase 4 Overview.

- **Decision**: Fixed
