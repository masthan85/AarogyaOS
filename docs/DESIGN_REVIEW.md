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
- No icons: the project had no icon library at this point (added in the fourth pass below).
- Not checked on a phone, with large system fonts, with a screen reader, or in Telugu, Hindi or other long scripts. Text sizes use fixed points and some rows may need to wrap differently.
- The new look is a proposal: show it to a doctor and a receptionist before settling on it.

## Third pass: whole-app review, performance and fixes

Method: the real screens were rendered in a headless browser against a demo clinic for six roles (doctor, nurse-facing consultation tabs, billing, administrator, reception, pharmacist and lab), at phone width in light and dark and at 1000 px wide, with every console error and failed API call recorded. As before this is a browser rendering of the React Native screens, not a phone. No console errors and no failed API calls appeared in any role.

Found and fixed:
- **Boot could hang on "Starting AarogyaOS…"** if the secure store or biometric prompt threw while the app started. The boot now falls back to the retry screen. It does not skip the biometric lock.
- **Transcript view re-rendered every line every second** while recording (a once-a-second timer and a transcript poll that always replaced state). Lines are now memoised with stable callbacks and the poll keeps old state when nothing changed, which matters in a long consultation.
- **The staff screen** offered a loud "Deactivate account" button on every row, including your own. The button is now quieter and hidden for your own account.
- **Home tiles:** doctors and billing staff saw a Facilities tile they cannot use. It now needs facility management rights.
- **Procedure date** was an empty field with a made-up example; it is prefilled with today's date like the vaccine form.
- **Prescription route chips** read "iv", "im", "sc" in lower case. They now read IV, IM, SC.
- **Wide screens:** the billing forms stretched edge to edge. They are now capped at a readable width.

Performance of the API (local, demo data, median of five): most screens' requests take 10 to 20 ms and 6 to 13 database queries, of which about five are the per-request sign-in and permission lookup. Login takes about 80 ms because of password hashing, which is intended. Two real problems were fixed: the invoice list ran about 600 queries for 100 invoices and now runs 11 (26 ms); the staff list ran a query per person and now runs one for all roles.

Not done or not checked: nothing was run on a phone, so touch feel, fonts, keyboard behaviour and safe areas are unchecked; the web bundle is 2.4 MB (the Android bundle size was not measured); lists use plain scroll views, which is fine for clinic-sized data but would need virtualised lists for very long ones; the per-request permission lookup (about five queries) could be cached if load ever requires it.

## Fourth pass: wide screens, navigation, icons and a display face

Prompted by seeing the app in a desktop browser, where the phone layout stretched edge to edge and left most of the screen empty. Checked as before, in a headless browser against the demo clinic: 1440 px, 820 px and 390 px wide, light and dark, as doctor, receptionist and administrator, with no console errors. Not checked on a phone or tablet.

- **Wide screens (1024 px and up)** now have a sidebar: the wordmark and clinic name, Home, the same role-filtered sections as the home tiles, and the signed-in person with Settings and Sign out. Content sits in a column capped at 960 px. Below 1024 px nothing changes: the stack fills the screen and navigation starts from the home tiles. See `features/shell/Sidebar.tsx` and `app/(app)/_layout.tsx`.
- **Icons**: outline icons (Feather, through `@expo/vector-icons`) on the sidebar, the home tiles and the attention cards. This is the dependency decision the first pass deferred. Icons always sit beside a label and are hidden from screen readers.
- **Headings use the website's serif** (`displayFont` in the tokens: Iowan Old Style, Palatino or Georgia, whichever the device has). Nothing is downloaded. Section labels are now sentence case; capitals are kept for warnings.
- **Home**: the header shows the date; Settings moved from a loose link at the bottom to the header (phones) or the sidebar (wide); the role line reads "Doctor at Demo Clinic".
- **Honest counts**: the attention cards used to show "None critical" beside a dash while the number was still loading or had failed. They now say "Checking…" or "Could not load. Open to try again."
- **Sign-in**: on wide screens a panel states what the product is for beside the form; the form has a "Show password" control.

Screens: [home, wide](design/home-wide.png), [sign-in, wide](design/sign-in-wide.png), [home, phone](design/home-phone.png).

Not done at this point: the inner screens, which the fifth pass below covers. The sidebar repeats the home tiles on wide screens, which is deliberate for now. As with the earlier passes, show it to a doctor and a receptionist before settling on it.

## Fifth pass: every inner screen

Method: all 26 routes and the 11 consultation tabs were rendered at 1280 px as doctor, nurse, receptionist, lab technician and administrator, against a demo clinic with four patients at different stages of a visit, and again at 390 px for the doctor, receptionist and consultation. No console errors. As before, this is a browser rendering, not a device.

The same few faults appeared on nearly every screen, so most of the work is in the shared components:

- **Buttons** fill the row on phones and are as wide as their label on wide screens (`Button`, with `block` to opt out, used on sign-in).
- **Text fields and short segmented choices** stop at 560 px on wide screens instead of running the width of the column.
- **Empty states** carry an icon and more room, so "nothing here" reads as a state, not a stray grey bar.
- **Page titles** in the navigation header use the display serif.
- **Status words** are sentence case everywhere ("In consultation", "Active"). Before, some chips shouted in capitals and others did not; capitals are now left for clinical warnings. `domain/text.ts` holds the helper, with a test.

Screen-specific changes:

- **Queue**: the token sits in a circle beside the name and status, and on wide screens the action is on the same line, so four patients fit where one and a half did.
- **Appointments**: time, patient and status on one line; day stepping uses icon buttons and a "Back to today" link.
- **Usage and audit**: the activity log is one ruled list with clinic-style dates, in place of a card per entry with raw action names and US dates.
- **Patient profile**: "Speaks English" in place of the language code. **Facilities**: readable kind and status.
- **Billing screens**: aligned with the page title instead of floating in the centre.

Screens: [queue](design/queue-wide.png), [appointments](design/appointments-wide.png), [consultation](design/consultation-wide.png), [audit](design/audit-wide.png).

Not done: the invoice screen with a real invoice, the lab result entry form with a real order, and the Draft EMR with real findings were not exercised, because the demo data had none; they use the same components. Dates are still typed as text (YYYY-MM-DD), which wants a proper date picker. The staff list still puts "Deactivate account" on its own line. Dark mode was checked on the home screen only in this pass.

## Sixth pass: phones and tablets

Method: the doctor's screens and consultation tabs were rendered at 360 by 740 (a small Android phone), 768 by 1024 (a tablet held upright) and 1180 by 820 (an iPad on its side), and the receptionist's at 390 by 844. Nothing overflowed, was cut off or needed sideways scrolling at any of them. At 1180 px the sidebar layout applies and the consultation shows its two columns; below 1024 px the app uses the phone layout, which also covers a tablet held upright and an iPad in split view. Layout follows the window size as it changes, so rotating the device switches between the two.

A browser cannot show how an app sits around a notch, a status bar or a keyboard, so these were fixed from the code and still need a device:

- **iPad support was not declared.** `app.json` lacked `ios.supportsTablet`, so on an iPad the app would have run as a scaled-up iPhone app and never reached the tablet layout. It is now set.
- **Safe areas.** The sidebar, the connection banner and the home header on wide screens now keep clear of the status bar, the home indicator and side cut-outs. Screens with a navigation header were already handled by the header.
- **Keyboard.** Every scrolling form now moves its focused field clear of the keyboard on iOS and keeps a tap on a button working while the keyboard is open. Before, only the sign-in screen did.

Touch targets were already sized for fingers and stay so: buttons are 48 points high, sidebar rows and icon buttons 44. On wide screens buttons are narrower, not shorter.

Not checked, and only a device can settle them: the real effect of the safe-area and keyboard changes; Android's keyboard behaviour with edge-to-edge display; large system font sizes; a hardware keyboard on a tablet; and the tablet in split view beside another app. These are added to `DEVICE_TEST_PLAN.md`.

## Seventh pass: an operational home screen and restrained motion

Asked for a more polished, enterprise feel. No Figma file was supplied, so nothing was imported from a design tool; the changes were made in code with the animation library already in the project (Reanimated).

- **Today at a glance.** The home screen now opens with up to four figures, each shown only to roles allowed to see it: people waiting now with the longest wait, appointments booked today with how many are done, results to review with how many are critical, and follow-ups due. Each opens its screen. A figure that has not loaded says "Checking…" and never carries a description it has not earned. A wait of 45 minutes or more turns the waiting figure amber, with the reason in words.
- **Next in the queue.** For roles that see the queue, the next five people waiting are listed with token, triage state, doctor and how long they have waited, refreshed every 30 seconds. It shares its data with the Queue screen, so no extra requests are made.
- **Motion, used once.** When the home screen opens, its sections fade and rise into place 45 ms apart over about 260 ms (`design-system/motion.tsx`). Nothing moves after that. With the device's reduce-motion setting on, the sections appear at once; this was measured frame by frame in a browser in both settings. Tiles shrink slightly while pressed.
- **Details.** Two faint rings give the header band some depth; the active sidebar section carries an accent bar as well as its tint and bold label; development builds show "Development build · synthetic data only" in the sidebar, so nobody mistakes a test build for the real one.

Screens: [home, wide](design/home-wide.png), [home, tablet](design/home-tablet.png), [home, phone](design/home-phone.png).

Not checked: the animation on a real Android or iOS device, where Reanimated runs natively rather than in a browser. In the browser the first frame of the home screen may paint fully visible for one frame before the fade begins; this was not visible to the eye in captures but should be watched for on devices.

## Code review, November 2026

The five lint warnings left from the third pass were reviewed rather than silenced. Two were real defects: Organisation settings and the GSTIN form reloaded from the server whenever the browser window regained focus, wiping anything typed but not saved. Both now keep unsaved edits on top of the saved values and drop them after a successful save. The other three (the payment amount, the note layout offered once, and the recording hook's pause reference) were rewritten in the patterns React recommends. Both rules are errors again, so new cases fail the build.

