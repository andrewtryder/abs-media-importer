---
name: ReelDock Design System
colors:
  ink: '#0C0B09'
  panel: '#18140F'
  panel-raised: '#221C14'
  panel-line: '#2E2618'
  panel-line-soft: '#221D14'
  paper: '#EDE6D8'
  paper-muted: '#9C9284'
  amber: '#E8A33D'
  amber-container: '#3A2C10'
  on-amber-container: '#F2C878'
  moss: '#6FA25E'
  moss-container: '#1E3318'
  on-moss-container: '#A8D89A'
  rust: '#C1502E'
  rust-container: '#3A1710'
  on-rust-container: '#F0A386'
typography:
  headline-lg:
    fontFamily: JetBrains Mono
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: JetBrains Mono
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: 0.02em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  code:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 6px
  DEFAULT: 6px
  md: 6px
  lg: 8px
  xl: 8px
  full: 9999px
spacing:
  base: 4px
  container-padding: 24px
  gutter: 16px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
---

## Brand & Style

ReelDock converts video into tape-era audiobooks (M4B). The UI reads as a tape deck /
audio equipment console: warm near-black panels, amber accents, VU meters, and a
two-circle reel motif reserved for in-progress states.

One signature move, applied with restraint: job progress is a segmented VU-meter bar,
and in-progress states use a reel-spin icon instead of a generic spinner. Everything
else — cards, type, spacing — stays disciplined and quiet around it.

No new font assets — Geist (body) and JetBrains Mono (display/labels) are self-hosted
in `app/static/fonts/`.

## Colors

Six named colors; everything else is a tint/shade of these:

| Token | Hex | Role |
| --- | --- | --- |
| `ink` | `#0C0B09` | Page background (warm near-black) |
| `panel` | `#18140F` | Card / sidebar / app-bar surfaces |
| `paper` | `#EDE6D8` | Primary text (warm off-white) |
| `amber` | `#E8A33D` | Primary accent, focus rings, VU needle |
| `moss` | `#6FA25E` | Success / active-good |
| `rust` | `#C1502E` | Error / danger |

Semantic Tailwind names (`primary`, `error`, `success`, `background`, `surface-container`,
`outline`, etc.) map onto these tokens so existing template class names keep working.

## Typography

- **Display / label face** — JetBrains Mono, uppercase, tight tracking. Page titles,
  section eyebrows, card titles, stat numbers, nav labels.
- **Body face** — Geist, regular weight, normal case. Descriptions, helper text,
  settings copy.

Type scale tokens (`headline-*`, `body-*`, `label-md`, `code`) are unchanged; only
`headline-*` and `label-*` families point at JetBrains Mono.

## Shape & Surface

- Cards: 8px radius (`rounded-xl` / `rounded-lg`)
- Buttons / inputs / badges: 6px radius
- Borders: single `panel-line` hairline (1px)
- Cards get a subtle inset top highlight:
  `box-shadow: inset 0 1px 0 rgba(237, 230, 216, 0.04)`

## Signature Components

### Segmented VU bar

A row of segments (20 full-size, 10 compact) filling left to right by percent.
Color by position, not status: first ~70% amber, next ~20% lighter gold, final ~10%
moss. On failure, lit segments switch to rust.

### Reel spinner

Two circles connected by a thin line, each with spoke marks, rotating slowly via
`animate-spin-slow` (respects `prefers-reduced-motion`). Used only for in-progress
states — not as a general icon motif.

## Restraint

- Do not add VU/reel motifs to static icons (settings, folder, link stay Material Symbols).
- Do not set body copy in JetBrains Mono.
- Do not add texture/grain/skeuomorphic tape imagery.
- Do not re-architect page layout — this is a palette/type/component skin pass.
