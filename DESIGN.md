# AarogyaOS design system

This file records the visual decisions for AarogyaOS. The mobile app's tokens (`apps/mobile/src/design-system/tokens.ts`) are the source of truth for colour, spacing, radius and the type scale; the marketing site (`site/`) uses the same values so the website and the product look like one thing. Where the website needs something the app does not (a display typeface, page layout, a nav), it is decided here.

Direction: calm, clinical and documentary. The product's promise is that software proposes and the doctor decides, so the site should feel like a well-kept clinic note rather than a start-up launch page: plain surfaces, one deep teal, generous reading width, and a purple used only for what software suggested. This direction comes from the product itself and its design review (`docs/DESIGN_REVIEW.md`), not from a comparison with other websites; the UXKIN design library was not connected.

## Colour

Every text and background pair below is at least 4.5:1 (large text 3:1) in its theme. Meaning is never carried by colour alone.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#F3F6F8` | `#0A1220` | Page background |
| `--surface` | `#FFFFFF` | `#131C2D` | Cards, panels, the phone mock-up |
| `--text` | `#0E1B2C` | `#EAF0F8` | Body and headings |
| `--text-muted` | `#4E5D75` | `#9AA8BF` | Secondary text, captions |
| `--border` | `#DCE3EB` | `#26334B` | Hairlines and card edges |
| `--primary` | `#0A6468` | `#5CC6C6` | Buttons, links, key marks |
| `--primary-text` | `#FFFFFF` | `#06201F` | Text on primary |
| `--primary-soft` | `#E1F0F0` | `#133A3D` | Quiet tinted backgrounds |
| `--hero` | `#0A4F53` | `#0F3F43` | Hero band and footer |
| `--hero-text` | `#FFFFFF` | `#EAF0F8` | Text on the hero band |
| `--hero-muted` | `#BFE3E3` | `#9CC9C9` | Secondary text on the hero band |
| `--ai` | `#5B3FA6` | `#C7B6F2` | Only for "suggested by software" |
| `--ai-soft` | `#EFEAFA` | `#27204A` | Background behind software suggestions |
| `--success` | `#1B6B3A` | `#8FD6A8` | Confirmed or accepted |
| `--success-soft` | `#E3F2E8` | `#14301F` | Background behind confirmed text |
| `--warning` | `#8A5A00` | `#F5C97A` | Notices that need attention |
| `--warning-soft` | `#FBF0D9` | `#3A2E12` | Background behind notices |

Rule: purple means "software suggested, a person has not decided yet", green means "a clinician has decided". The site never uses purple for decoration, because the product uses it for a safety meaning.

## Typography

Two families, both already on every device, so the site loads fast and sends no data to a font service.

- Display (page and section headings): `"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif`, weight 600. The serif gives headings the feel of a printed clinical document and sets the site apart from the all-sans look of most software pages.
- Body and interface: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`, weights 400, 600 and 700 (matches the app).

Scale (px, line height): 56/1.05 hero display, 40/1.1 section heading, 28/1.2 sub-heading, 20/1.5 lead, 17/1.6 body (never below 16), 14/1.5 small, 12/1.4 caption. Reading width is capped at 68 characters for paragraphs. Letter spacing: -0.02em on the two display sizes, 0.08em on overlines.

## Spacing and layout

Spacing scale (px): 4, 8, 16, 24, 32, 48, 72, 112. Section padding is 72 on phones and 112 from tablet width. Content width 1120, with text columns narrower. Layouts are left aligned and asymmetric (copy on one side, a product screen on the other); sections alternate their weight so the page does not read as the same block repeated. Breakpoints: 640 and 1024.

## Shape and depth

Radius: 8 (inputs, chips), 12 (cards), 16 (phone frame and large panels), 999 (pills). Depth comes from borders first; the only shadow is `0 1px 3px rgba(14,27,44,0.08)` on the phone mock-up and floating cards, and none in dark mode.

## Components

- On the hero and call-to-action bands the primary button inverts: `--hero-text` fill with `--hero` text, and the secondary has a `--hero-muted` border, because teal on teal has no contrast.
- Primary button: `--primary` fill, `--primary-text`, 48 px high, radius 12, weight 700. Hover darkens 8 percent, focus shows a 3 px outline in `--primary` offset by 3 px, disabled is 45 percent opacity.
- Secondary button: transparent with a 1.5 px `--primary` border and `--primary` text. Quiet button: text only, underlined on hover.
- Links: `--primary`, underlined; visited keeps the same colour.
- Cards: `--surface`, 1 px `--border`, radius 12, padding 24, used sparingly (the product screens and tables). Lists of principles are ruled lists (a 2 px top rule, a heading and a paragraph), not rows of identical cards.
- Step markers: numbered circles are used only for the visit walkthrough, because that content really is a sequence. They sit above the phone, never on it.
- Chips: pill shape, soft background with matching strong text and a word (for example "Suggested", "Confirmed"), never colour alone.
- Navigation: a plain top bar with the wordmark, three anchor links and one primary button; it collapses to a menu button under 640 px.
- Footer: `--hero` band, plain links, the honest status line.

## Imagery and icons

No stock photography and no emoji. The site shows the real product: screens rendered from the app itself (Draft EMR, consultation, billing) inside a simple phone frame, plus small inline SVG diagrams. Icons, where needed, are simple outline SVGs, 1.75 px stroke, `currentColor`. Screenshots in the site are of the demo clinic with invented data only.

## Motion

Motion answers an action only (menu open, focus, hover). No scroll-triggered entrances, no parallax. `prefers-reduced-motion` removes all transitions.

## Voice

Plain, specific and honest about status. Sentence case. A button says what happens ("See how a visit works"). The site never claims what has not been proved: where something is untested or unreviewed, it says so.
