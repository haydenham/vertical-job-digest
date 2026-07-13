# Design language v2 — "premium dark product" (D-080/D-081)

*v1 ("terminal dev-tool, dark") is retired — chosen from screenshot candidates on the live
dashboard, 2026-07-12. Reference: Linear. Softer, more premium dark; the CLI cosplay is gone.*

## Vibe
Dense, fast, dev-native — but a *product*, not a terminal. Signal over chrome, executed with
air: lifted surfaces, quiet borders, one muted accent. Think Linear.

## Color (dark only)
- bg base        #08090c   (blue-tinted near-black)
- surface        #0f1014
- surface raised #16171d
- border         #24252d  (hover #3c3e4a)
- text primary   #e6e7ec
- text muted     #9c9eab
- text dim       #63656f
- accent         #6e79d6  (hover #8b93e8)   <- the ONLY accent, use sparingly
- accent tint bg #191b2e / text #a5adf0
- success        #4cc38a  (verdict green — semantic, not an accent)
Selection highlight = accent bg, near-black text.

## Depth
Borders stay primary. Raised containers (table, panels, menus) may carry a soft shadow
(`--shadow-raised`); no glows in the app. The landing page alone may use one restrained
hero glow/gradient. Radius 10px (chips/small 6px).

## Type
- UI / headings / controls / labels: **Inter** (400–700), letter-spacing -0.1px at body size,
  tighter (-0.3 to -0.5px) on headings. Uppercase section labels: Inter 600, 11px,
  letter-spacing 1px.
- Mono for **true data only**: **JetBrains Mono** — scores, timestamps, dates, tags/chips,
  company codes, paths, kbd hints. Never for buttons, nav, labels, or prose.
- Landing gets a real marketing scale (display sizes, `text-wrap: balance`); the app stays
  dense at 14px body.

## Patterns
- Numbers/scores big in mono, color-coded by value.
- Tags/chips = mono, 11–12px, subtle bordered pills on raised surface.
- A left 3px colored spine marks the selected/expanded row and semantic states.
- Layout dense; CSS grid + gap does the spacing.
- Buttons: quiet by default (raised surface + border); primary = accent border/tint, still flat.

## Don'ts
Terminal motifs ($ prompt, blinking ▮ cursor, `//comment` strings, `~/paths` as chrome);
more than one accent hue; gradient/glow inside the app (landing hero excepted); decorative
illustration; emoji; heavy shadows; rounded-corner "callout" boxes with fat left borders.
