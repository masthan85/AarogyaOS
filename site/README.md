# AarogyaOS website

A one-page marketing site in plain HTML and CSS. There is no build step and no framework: open `index.html` or serve the folder with any static host.

```bash
python3 -m http.server 8090 --directory site     # then open http://localhost:8090
```

## Files

| Path | What |
|---|---|
| `index.html` | The page: copy, structure, accessible descriptions of every screen |
| `assets/styles.css` | Styles built from the tokens in `DESIGN.md` (light and dark, follows the device setting) |
| `assets/site.js` | Opens and closes the menu on small screens. The page works without it |
| `assets/img/*.webp` | Screens captured from the app against the demo clinic with invented data, one light and one dark version of each |

## Before publishing

1. **Replace the contact placeholder.** `hello@your-domain.example` appears in three places in `index.html` (two `mailto:` links and the footer text, marked with `data-placeholder`), and a comment marks the first. Remove the "(placeholder, replace before publishing)" note in the footer too.
2. **Check every claim against the current state of the project.** The page is deliberately honest about what is untested; if a status in the "Where we are" table changes, change the table.
3. **Do not add** testimonials, customer logos, accuracy figures or prices until they exist. None are on the page today.
4. Add a real domain, a privacy statement and any cookie or analytics notice your hosting needs. The page itself sets no cookies and loads nothing from third parties.

## Updating the screenshots

The images come from the app's browser build running against the demo clinic (`python -m app.cli demo-seed`), hiding the developer-only recording banner. Capture new ones at a 390 by 844 viewport at 2x, in light and dark, crop to 780 by 1500 and save as WebP at quality 80, keeping the file names.

## Checked

Rendered at phone (390), tablet (820) and desktop (1280) widths in light and dark with no horizontal scrolling, broken images or console errors; operated with the keyboard only (tab order, visible focus, skip link, menu with Enter and Escape); and the menu links remain reachable with JavaScript off. Text contrast was computed for every colour pair in both themes (all at least 4.5:1). Not checked: real devices and screen readers.
