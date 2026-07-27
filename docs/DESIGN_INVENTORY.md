# Basirah AI — Design Inventory (Phase 9)

Source of truth: Design System v1.0 (frozen, chapters 0-14), Design System
v2.0 Enterprise (Part I = v1.0 verbatim, Part II = enterprise expansion,
chapters 15-23), UI Specification v1.0 (25 screens, S1-S25 + global
invariants), the master logo, the approved brand-board and high-fidelity
mockups, and the user's explicit Phase 9 decisions below. Where the DS
text and a visual asset conflicted, the resolution the user confirmed is
recorded inline and is now binding for all implementation.

This document is descriptive, not inventive: every value below traces to
one of the source assets or an explicit user decision. Nothing here was
guessed. Any value needed during implementation that is *not* covered
here must be escalated, not invented (DS §23.2 interpretation ladder:
search doc -> derive from nearest sibling -> compose from tokens -> STOP
AND ASK).

## 1. Confirmed Phase 9 decisions (override any conflicting visual asset)

1. **Typography**: IBM Plex Sans Arabic is the official Arabic typeface.
   The "Safir" specimen shown on the brand board is a retired/legacy
   label and must not be used or sourced.
2. **App icon**: the Navy L5 icon-grade mark (gold + teal on navy-950) is
   the one production icon used everywhere in the app. The light-background
   ("خلفية فاتحة") tile is an optional export reserved for App Store /
   marketplace listing requirements only -- it must never appear inside
   the product UI and never replaces the production icon.
3. **Recommendation badges** (BUY/SELL/WATCH/HOLD) use a dedicated
   semantic palette, distinct from both market up/down colors and AI
   teal:
   - BUY -> green
   - SELL -> red
   - WATCH -> yellow
   - HOLD -> neutral/blue
   AI teal is reserved exclusively for AI-attribution elements (AI badge,
   AI confidence, AI score, AI attribution, AI-generated content chrome)
   and must never color a Buy/Sell/Watch/Hold action badge.
4. **UI Kit**: no separate Figma export is coming. The Design System, UI
   Specification, Enterprise Component Library (DS Part II ch.19) and the
   approved mockups together are the complete component source of truth.

## 2. Color tokens

### 2.1 Brand core (frozen, DS §2)

| Token | Hex | Usage |
|---|---|---|
| `bsr-gold-500` | `#D4AF37` | Brand gold -- value, premium financial chrome, logo gold |
| `bsr-teal-500` | `#00B894` | AI teal -- **AI-attribution content only** (Teal Reservation Rule) |
| `bsr-teal-700` | `#0E7C86` | AI teal, deeper variant (gradients, pressed AI states) |
| `bsr-navy-950` | `#0A0E14` | Base app background |
| `bsr-navy-800` | `#232A36` | Elevated surface background |
| `bsr-white` | `#FFFFFF` | Primary text on dark, inverse surfaces |

Full 100-900 scales exist for gold/teal/navy per DS §2.2-2.4; only the
core 5 values above are hard-frozen and must never be recolored. Every
other shade is derived (tint/shade ladder), never hand-picked.

**Governing rule (DS §15, "Teal Reservation Rule"): if it is teal, the AI
said it. If it is gold, it is valuable.** Teal is forbidden on links,
decorative elements, positive P&L, and any non-AI interactive control.

### 2.2 Market semantic colors (DS §15.3 -- deliberately distinct from brand teal)

| Token | Hex | Usage |
|---|---|---|
| `bsr-market-up` | `#3FB950` | Positive price/percentage change |
| `bsr-market-down` | `#E5484D` | Negative price/percentage change |

### 2.3 Recommendation badge colors (Phase 9 decision, §1.3 above)

| Token | Semantic | Notes |
|---|---|---|
| `bsr-action-buy` | green | same family as `bsr-market-up`, distinct token so the two can diverge later |
| `bsr-action-sell` | red | same family as `bsr-market-down` |
| `bsr-action-watch` | yellow | new token, not previously in the DS core palette -- compose from a neutral warm-yellow consistent with the existing tint/shade ladder methodology (DS §2.2), documented here as the escalation point if a literal hex is later supplied |
| `bsr-action-hold` | neutral/blue | desaturated slate-blue, distinct from both market colors and AI teal |

### 2.4 Surfaces & structure (DS §3)

- `bsr-surface-base` = navy-950, `bsr-surface-raised` = navy-800
- `bsr-border-subtle`, `bsr-border-strong` -- low-contrast hairlines on navy, never pure white at full opacity (DS §3.7 contrast rules)
- Text: primary = white @ full opacity, secondary = white @ reduced opacity per DS accessibility scale (§21), never a hand-picked gray

## 3. Typography

- **Arabic (UI/body/primary)**: IBM Plex Sans Arabic -- production-grade, open-licensed, correct numeral rendering (DS §4.1; confirmed over "Safir" per Phase 9 decision #1).
- **English/numerals (secondary)**: Inter, tabular lining figures.
- **Digits**: Western digits (0-9) mandatory for all financial data in both Arabic and English contexts -- never Eastern Arabic-Indic numerals.
- Type scale, weights, and line-heights follow DS §4.2-4.4's fixed ramp (display/h1-h4/body/caption/mono-numeric); no custom sizes outside that ramp.

## 4. Logo & iconography

- Master mark: eye + candlesticks + rising line + 4-point star, gold/teal on navy-950. Frozen; never reconstructed from memory -- only the supplied official asset files are ever used as the source image.
- 5 approved lockups: L1 Ceremonial, L2 Horizontal, L3 Wordmark, L4 Symbol, L5 Icon-grade.
- **App icon**: L5 only, gold + teal on navy-950 (Phase 9 decision #2). The light-background export is out-of-product-UI, marketplace-listing-only.
- Absolute prohibitions (DS §2.5, still binding): never place the mark on a solid gold or solid teal field, never recolor the mark, never use a light-background variant inside the product.
- **The Basirah Star**: 4-point star AI-attribution mark extracted from the logo glint. Teal-500. Sizes 12/16/20px. One-per-card density cap. Never appears on non-AI content.

## 5. Motion

Exactly 5 AI motions exist system-wide (DS §20); no others may be invented:

| Motion | Duration | Usage |
|---|---|---|
| Sweep | 700ms | signature AI motion, teal radial arc, max once per module per event, never ambient/looping |
| Pulse | 1s loop | AI-processing/live state indicator |
| Glint | 200ms | Star/logo micro-highlight |
| Explanation-expand | 320ms | opening the mandatory explanation panel |
| Confidence-fill | 400ms | confidence bar/gauge fill-in |

All other UI transitions (hover, focus, route change) use the DS's
general motion tokens (subtle, professional, 60fps target) -- never a
sixth AI-branded motion.

## 6. The Explainability Contract (DS §18.1 -- mandatory, build-blocking)

No Basirah recommendation may render without a reachable explanation.
Canonical explanation anatomy is mandatory on every recommendation
surface and includes:
- A **conflicting-evidence row** -- never hidden, even when empty of conflict it must render an explicit "no conflicting evidence" state, not be omitted.
- A **stop-loss value** -- "any buy/sell signal without a stop value cannot ship." Missing stop-loss is a build failure, not a style choice.

## 7. Spacing, radius, shadow, layout

- Spacing scale: DS §5's fixed 4px-based scale (`bsr-space-1` ... `bsr-space-n`). No raw px margins/padding outside the scale.
- Radius: DS §6's fixed radius scale (`bsr-radius-sm/md/lg/full`). Cards/buttons/inputs each map to one documented radius token, never an arbitrary value.
- Shadow/elevation: DS §7's elevation scale, dark-theme-appropriate (soft, low-opacity, never a light-mode drop shadow ported as-is).
- Layout: RTL-first, Arabic-primary. LTR is a mirror built from logical properties (`inline-start`/`inline-end`, `margin-inline-*`), never literal `left`/`right`. Global invariants (top bar, side nav, empty-state pattern, instrument row) are shared modules built once and reused by every screen -- a screen implementing its own version of any of these is defective by definition (UI Spec §0).

## 8. Responsive rules

Confirmed breakpoints/targets from the approved mockups: desktop dashboard
(wide multi-column grid), tablet (condensed grid, per the tablet mockup),
mobile (single-column, bottom tab bar), and a companion-device summary
view (per the watch mockup) -- watch-tier is read-only/summary, not a full
navigable app. Components resize via the DS token scale, not bespoke
per-breakpoint values.

## 9. Components (DS Part II ch.19 Enterprise Component Library + approved mockups)

Canonical, build-once components referenced across screens: top app bar,
global search, side navigation, instrument row, watchlist row, sector
pill/heatmap cell, AI signal card (with Star + confidence bar +
explanation-expand), recommendation badge (BUY/SELL/WATCH/HOLD per §2.3),
market gauge (sentiment dial), news item row, alert item row, report
card, chart panel (candlestick + range selector), portfolio holding row,
allocation donut, chat/AI conversation panel, empty state, loading
skeleton. Each is implemented exactly once and imported everywhere it
appears -- never re-implemented per screen.

## 10. Open escalation points

- `bsr-action-watch` (yellow) and `bsr-action-hold` (neutral/blue) do not
  have DS-documented literal hex values -- they are new tokens introduced
  by the Phase 9 decision on recommendation badges. They will be composed
  from the existing tint/shade methodology (DS §2.2) at implementation
  time, kept as isolated, clearly-named tokens so a literal hex can be
  dropped in later without touching call sites, per DS §23.2's
  "compose from tokens" rung of the interpretation ladder.
