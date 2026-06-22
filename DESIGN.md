# Design language — "terminal dev-tool, dark"

## Vibe
Dense, fast, developer-native. Think a CLI that grew a GUI. No rounded
marketing fluff, no gradients-as-decoration, no emoji. Signal over chrome.
Think cloudflare or github interface

## Color (dark only)
- bg base        #09090a
- surface        #0e0e10
- surface raised #141416
- border         #1c1c20  (hover #3a3a42)
- text primary   #ededf0
- text muted     #9a9aa2
- text dim       #5f5f68
- accent         #f6821f  (hover #ff9233)   <- the ONLY accent, use sparingly
- accent tint bg #2a1c08 / text #f6a64f
- success        #2fd87a
Selection highlight = accent bg, near-black text.

## Type
- UI / headings: Space Grotesk (400–700), tight tracking (-0.3 to -0.7px)
- Mono everywhere data lives: JetBrains Mono — labels, metrics, scores,
  timestamps, tags, paths, kbd hints. Uppercase mono labels at 11px /
  letter-spacing 1px for section headers.

## Patterns
- Numbers/scores rendered big in mono, color-coded by value.
- Tags = mono, 11–12px, subtle bordered chips (#141416 / #26262b border).
- A left 3px colored spine on cards instead of heavy fills.
- Keyboard-first: show `↑↓ navigate · ↵ open` hints in dim mono.
- Blinking ▮ cursor in the wordmark. `>` `$` `~/path` `//comment` motifs.
- Borders + flat surfaces do the work; shadows minimal. radius 8–13px.
- Layout dense, generous use of CSS grid + gap.

## Don'ts
Inter/Roboto, rounded-corner+left-accent "callout" boxes, gradient heroes,
emoji, more than one accent hue, decorative illustration.