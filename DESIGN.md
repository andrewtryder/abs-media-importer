---
name: abs-media-importer Design System
colors:
  surface: '#13161e'
  surface-dim: '#0d0f14'
  surface-bright: '#1c2030'
  surface-container-lowest: '#08090d'
  surface-container-low: '#101219'
  surface-container: '#13161e'
  surface-container-high: '#1c2030'
  surface-container-highest: '#252a3a'
  on-surface: '#e8ecf4'
  on-surface-variant: '#8892b0'
  inverse-surface: '#e8ecf4'
  inverse-on-surface: '#0d0f14'
  outline: '#2e3452'
  outline-variant: '#3d4566'
  surface-tint: '#6c8ef7'
  primary: '#6c8ef7'
  on-primary: '#0d0f14'
  primary-container: '#6c8ef7'
  on-primary-container: '#e8ecf4'
  inverse-primary: '#6c8ef7'
  secondary: '#8892b0'
  on-secondary: '#0d0f14'
  secondary-container: '#252a3a'
  on-secondary-container: '#e8ecf4'
  tertiary: '#556080'
  on-tertiary: '#e8ecf4'
  tertiary-container: '#1c2030'
  on-tertiary-container: '#e8ecf4'
  error: '#f87171'
  on-error: '#0d0f14'
  error-container: 'rgba(248, 113, 113, 0.12)'
  on-error-container: '#f87171'
  primary-fixed: '#6c8ef7'
  primary-fixed-dim: '#6c8ef7'
  on-primary-fixed: '#0d0f14'
  on-primary-fixed-variant: '#6c8ef7'
  secondary-fixed: '#8892b0'
  secondary-fixed-dim: '#8892b0'
  on-secondary-fixed: '#0d0f14'
  on-secondary-fixed-variant: '#8892b0'
  tertiary-fixed: '#556080'
  tertiary-fixed-dim: '#556080'
  on-tertiary-fixed: '#0d0f14'
  on-tertiary-fixed-variant: '#556080'
  background: '#0d0f14'
  on-background: '#e8ecf4'
  surface-variant: '#252a3a'
typography:
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.025em
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-sm:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.015em
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
  DEFAULT: 10px
  md: 10px
  lg: 16px
  xl: 16px
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
The design system of **abs-media-importer** is engineered to be a dark-mode first, clean, and highly focused utility for importing YouTube audiobooks to Audiobookshelf. The overall style is modern developer-centric, leaning into sleek high-contrast containers, solid accent borders, and elegant state alerts. It prioritizes legibility, spatial clarity, and responsiveness.

The brand color palette balances deep cosmic dark grays and blues with a bright electric-blue primary accent (`#6c8ef7`) to drive user interaction. High density data tables, progress monitors, and terminal log components provide immediate clarity for background task operations.

## Colors
The color scale focuses on layering deep dark background colors to establish depth.
- **Primary Accent (`#6c8ef7`)**: Represents action, highlights, active navigation, and primary button calls-to-action.
- **Background Architecture**:
  - Global background is set to a deep blackish blue `#0d0f14`.
  - Cards and primary modules use a slightly lighter slate background `#13161e`.
  - Hover states, table headers, and sub-containers step up to `#1c2030` and `#252a3a`.
- **Borders & Outlines**: Consistent solid strokes (`#2e3452`) frame all elements, shifting to a more visible `#3d4566` on hover or focused states.
- **Semantic Badges**:
  - Success is represented by a vibrant green (`#4ade80`).
  - Warnings are represented by yellow (`#facc15`).
  - Errors/Danger are represented by red (`#f87171`).

## Typography
The system uses the high-precision sans-serif **Geist** font family for all user-facing interfaces, ensuring clean lines and balanced visual weights. Monospaced text is designated for technical metadata, video IDs, durations, logs, and badge tags using **JetBrains Mono**.
- **Headlines**: Strong bold weights with negative letter spacing for a structural, solid appearance.
- **Body & Captions**: Muted secondary colors are used to establish a hierarchy, preventing visual clutter in data-dense layouts.
- **Log Terminal**: Specialized monospaced typography using `#556080` or `#e8ecf4` text over dark console panels to reflect real-time CLI feedback.

## Layout & Spacing
A strict spatial grid system governed by a 4px base ensures visual consistency.
- **Global Layout**: Fixed fluid header containing the logo, nav links, and system indicators, with centered main container cards.
- **Padding & Margins**: A standard container padding of 24px is applied to content card modules. Grid layouts use a 16px gutter.
- **Visual Gaps**: Related form elements are separated by 8px, while primary page blocks are separated by 32px to create distinct mental separations.

## Elevation & Depth
Depth is represented using high-contrast borders and subtle background shifts rather than diffuse drop shadows.
- **Standard Cards**: Outline-only or subtle dark borders (`#2e3452`) with a flat background.
- **Interactions**: On hover, interactive elements increase their border contrast (`#3d4566`) and background brightness slightly.
- **Glow Effects**: Muted radial glows using the primary accent color (`rgba(108, 142, 247, 0.08)`) are applied to critical components to draw attention.

## Shapes & Radii
Rounded corners reflect a "Soft-Tech" approach, keeping elements modern but structured.
- **Primary Cards**: Large 16px radius (`--radius-lg`) for major layout containers.
- **Standard Controls**: 10px radius (`--radius`) for default card elements.
- **Inputs & Buttons**: 6px radius (`--radius-sm`) to maintain sharp, tool-like interaction areas.
