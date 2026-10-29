# Design review and redesign of the mobile app

Method: I rendered the real app in a headless browser at phone width (390 px, light and dark) with a demo clinic, and looked at the home screen, the queue, the consultation and the Draft EMR tab. This is a browser rendering of the same React Native screens, **not a phone**: fonts, safe areas, keyboard behaviour and touch feel still need a look on a real Android phone and an iPhone.

## What was wrong

1. **Everything had the same weight.** The home screen was a list of identical bordered cards, so "Pharmacy" looked as important as "Results to review". Nothing said what needed attention first.
2. **Eleven section pills wrapped over four rows** on the consultation screen. A third of the screen was navigation before any content appeared.
3. **The recording bar shouted.** A thick border, four rows and two oversized buttons for a state that is mostly "not recording".
4. **The Draft EMR was a feed, not a note.** Each of twelve findings was a full card with three chips, a heading, details, a quote, an "If accepted" line and three large buttons, about four screens in all. A doctor reading a clinic note wants headings with short lines under them.
5. **No type scale.** Sizes were chosen screen by screen (12, 16, 17, 20, 22).
6. **Buttons had two states, filled or outlined.** The outline looked the same for "Edit" and "Reject", and the red "Stop" button had white text on a pale pink background in dark mode (low contrast).
7. **Flat and generic.** No depth, no brand moment, status chips drawn as thin outlines.

## What changed

- **Design tokens** (`src/design-system/tokens.ts`): a calmer palette with soft tints for success, warning, danger and software-suggested content; one type scale; a light shadow in light mode. Every text and background pairing used was computed against WCAG AA (4.5:1) in both themes.
- **Components** (`src/design-system/components.tsx`): buttons are now primary, tinted (secondary), text-only (ghost) or danger, with a compact size that stays at the 44-point minimum; chips are soft fills; cards can carry a coloured edge and tint (`tone`); alert banners are tinted; new `TabBar` (one scrolling row, underline, count badge) and `Avatar`.
- **Home** (`features/dashboard`): a coloured header with greeting, name, organisation and roles; a "Needs your attention" row with live counts (results to review with how many are critical, follow-ups overdue or due today); tiles grouped under "The day at the clinic", "Clinical work" and "Manage", two to a row, and only what the person's role allows. The tile arrangement is a tested function.
- **Consultation**: a compact patient header with initials, the tab bar replacing the wrapped pills (Draft EMR shows how many findings wait), and a compact recording bar with the same wording as before (colour is never the only signal; "PAUSED — NOT RECORDING" and the development warnings are still stated in words).
- **Draft EMR**: one card per heading of the note; each waiting finding is a short row (the finding, its details, the words it came from, any warning, and Accept, Edit, Reject); decided findings collapse to a single line with a tick or cross; a progress bar; the kind label only where a heading mixes kinds.
- **Fix found on the way**: the danger button's text now uses a dedicated colour (`dangerText`) so it is readable in dark mode, and the API client no longer calls `fetch` as a bare reference (browsers refuse that; phones were unaffected).

Before and after: [home](design/home-before.png) → [home](design/home-after.png); [Draft EMR](design/draft-emr-before.png) → [Draft EMR](design/draft-emr-after.png).

## Second pass: the other screens

The same system was then carried through the rest of the app, checked in the same way:

- **Sign-in**: a brand mark and heading, with the form in a card.
- **Short choices** (Name / Mobile / MRN, Lab / Imaging / Other, Routine / Urgent / Immediate, Suspected / Provisional / Confirmed) are now one connected control; longer lists still wrap as chips.
- **Findings from the assistant** use one row design in both the Assist tab and the Draft EMR tab (the older heavier cards are gone).
- **Lists that open another screen** (Administration) use a new `NavRow` with an arrow; introductory text uses a `Lead` style; empty states sit in a tinted box.
- **Text sizes** on about twenty screens were moved from ad hoc numbers to the shared type scale (a scripted change, then looked at).
- **Fixes**: the tab bar no longer collapses on long pages; the recording bar is a little shorter.

Looked at in light and dark: sign-in, home (doctor and administrator), patients, appointments, queue, results, follow-ups, pharmacy, settings, administration, and every consultation tab. Not looked at individually: triage, consent, patient profile and new-patient forms, the booking form, most administration sub-screens, lab entry, and cover; they use the same components and should look consistent, but check them.

## Not done

- Layouts were not reworked screen by screen beyond what is listed above; everything else follows from the shared components.
- No icons: the project has no icon library. Meaning is carried by words, position and colour together. Adding icons is a dependency decision for later.
- Not checked on a phone, with large system fonts, with a screen reader, or in Telugu, Hindi or other long scripts. Text sizes use fixed points and some rows may need to wrap differently.
- The new look is a proposal: show it to a doctor and a receptionist before settling on it.
