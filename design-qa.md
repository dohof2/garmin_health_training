# Training journal design QA — 10 November 2026

## Follow-up: seven-day activity summary and sync explanation

The user subsequently requested replacing the dashboard's recurring availability with four recorded-history metrics. The original visual direction remains the layout/style reference; this scoped change uses the user's explicit metric list as its content target.

Current evidence: [desktop summary](docs/design-audit/2026-11-10/implementation/22-last-seven-days.jpg) and [mobile summary](docs/design-audit/2026-11-10/implementation/23-last-seven-days-mobile.jpg). These saved captures were opened and inspected. At 1440 × 1024 the right column shows all four metrics; at 390 × 844 they use a two-column list without horizontal overflow (client and scroll widths both 375 pixels). The prior comparison sheets below document the initial implementation before this requested content replacement.

The seven calendar days include today, dated in the browser's IANA timezone. Recorded activity pages are read to completion, deduplicated by ID, and filtered to the displayed period. Strength counts use recorded strength/weight/resistance activities. Bike counts, duration and kilometres include indoor and virtual rides. Missing duration/distance is explicitly flagged; an entirely unknown measure displays a dash. Planned sessions are excluded. Availability editing remains in Training preferences; Dashboard no longer writes preferences.

For Nov 4–10, the browser displayed **1 strength workout, 3 bike activities, 4h 51m ridden and 107.4 km**. An independent read-only database calculation matched these totals (17,464.551 seconds and 107.43702 km before display rounding).

Journal tests now also cover date boundaries, a DST-adjacent calendar week, sport classification, duplicate IDs, partial/all-missing measures, valid zeroes, pagination past 100 activities, and failure of a later page without publishing partial totals. Tests and production build passed.

The reported sync failure was investigated separately. Recent failed jobs identify `training_load_history` for Nov 10; a saved successful Garmin `get_daily_training_status` response requested for that date contains a Nov 9 dated load. Current-day sleep duration and score are also missing, while the main feeds committed data. The UI now shows **Partially synced** when an unsuccessful job received records, and exposes failed steps and missing-measure details inside the sync disclosure. Backend failure status, current-day validation and publication guards are unchanged. A new sync attempt was running during verification, so no claim of a complete sync is made.

No P0/P1/P2 layout issues were observed in the scoped replacement. The current final result remains passed for visual/UI verification; the separate Garmin source-data problem is pending.

## Visual target and scope

Source visual truth: [selected design](docs/design-audit/2026-11-10/selected-direction.png), the first concept's journal layout with the third concept's blue/navy/coral palette. The user explicitly replaced the goal area with today's training readiness and asked for implementation in the existing app.

Implementation: [local app](http://127.0.0.1:5173/#dashboard).

Main evidence: [final dashboard](docs/design-audit/2026-11-10/implementation/18-dashboard-final.jpg), [full comparison](docs/design-audit/2026-11-10/implementation/comparison-final.png), [settings comparison](docs/design-audit/2026-11-10/implementation/comparison-settings-focus.png). Source is on the left of each comparison, implementation on the right. Both comparison sheets were opened and inspected.

Desktop comparison viewport: 1440 × 1024 CSS pixels; document client width 1425 pixels including the browser's scrollbar allocation. Source bitmap: 1487 × 1058. Captured implementation bitmap: 1425 × 1013. The in-app browser capture's bitmap dimensions differ from the requested CSS viewport; both images were normalized to 1425 × 1013 for the comparison sheet, rather than asserting pixel-perfect CSS/density equivalence. The combined full-view bitmap is 2850 × 1013. The focused settings comparison is 1000 × 780, with equal-size crops after normalization. State: dashboard, Tuesday's availability expanded, actual local data, light theme, 10 November 2026 in Asia/Jerusalem. The final capture includes a background readiness refresh while retaining the last calculation and its evidence; it is not an initial blank/loading state.

Mobile evidence: [overview](docs/design-audit/2026-11-10/implementation/19-mobile-final.jpg), [availability editor](docs/design-audit/2026-11-10/implementation/20-mobile-availability.jpg), [nutrition](docs/design-audit/2026-11-10/implementation/21-mobile-nutrition-final.jpg). Viewport: 390 × 844 CSS pixels. Document width and scroll width both measured 375 pixels: no page-level horizontal overflow. The navigation itself deliberately scrolls horizontally and keeps the current section visible.

## Findings and comparison history

- **Resolved P2 — availability started too low.** Earlier [desktop capture](docs/design-audit/2026-11-10/implementation/02-dashboard-settings.jpg) placed the right heading below the main title. Moved the availability section upward to match the source's editorial composition. Final evidence: dashboard and full comparison.
- **Resolved P2 — day editor hid the end of the week.** The first implementation exposed a separate day-plan control before the sport/time fields. Moved day-plan and multiple-activity settings into secondary options; retained minimum/maximum time, rest days, activity order and daily limits. All seven rows fit in the final desktop reference frame.
- **Resolved P2 — weekday icons touched the day label.** Increased the first grid track to 44 pixels. Final full and focused comparisons show separate, aligned labels and icons.
- **Resolved P2 — mobile workout column was too narrow.** The earlier [mobile capture](docs/design-audit/2026-11-10/implementation/09-mobile-dashboard.jpg) wrapped the title and action awkwardly. Stacked workout and readiness below 700 pixels; final mobile overview has readable text and an unbroken primary action.
- **Resolved P2 — mobile nutrition totals clipped.** The earlier [nutrition capture](docs/design-audit/2026-11-10/implementation/10-mobile-nutrition.jpg) required horizontal scrolling to read Remaining. Removed inherited container padding and applied a fixed compact table layout at mobile widths. Final nutrition evidence shows all four columns.
- **Resolved P2 — mobile active navigation could remain outside the scroll area after resizing.** Added page/resize handling that reveals the current item within the navigation only. Verified active Dashboard is visible and navigation scroll is zero at the mobile starting view.
- **Resolved P2 — repeated chart controls competed with data.** Zoom/pan controls now sit behind Explore chart; layout/export/edit operations sit behind Chart options. Browser checks exercised zoom and reset. Native disclosures keep the controls reachable by keyboard.
- **Resolved markup/accessibility issue — information dialogs were nested inside paragraph/heading content.** Portaled their native dialog elements to the document body, preserving their trigger and focus behavior. A clean browser run showed no console errors.

## Required fidelity surfaces

- **Fonts and typography:** Georgia serif display headings, personal brand, weekday and sport summaries reproduce the journal character. System sans is retained for dense labels and form controls for legibility; this is an intentional production adaptation. Hero wrapping, secondary headings and inline fields were inspected at desktop and mobile widths.
- **Spacing and layout:** pale sidebar, open main surface, two-column desktop overview, aligned day rows and one focused editor match the chosen structure. Ordinary sections use dividers instead of nested rounded cards. Existing standalone workout objects retain compact tinted surfaces. Mobile uses a horizontal navigation row and stacked daily content.
- **Colours and tokens:** near-white #fbfcfd, powder-blue #eaf0f6 and navy #20364d are shared across all sections. Coral text uses #b85d46, darker than the mock's accent, to keep small action text readable. Selected rows use a blush tint. Existing chart/status colours retain their meaning.
- **Images and icons:** a generated raster contour asset is used in the page and sidebar; it was opened and inspected. New navigation/sport/action icons use Phosphor. Existing activity maps and muscle diagrams remain intact. No screenshot is used as application UI.
- **Copy and content:** real workouts, readiness, dates, nutrition and recurring availability replace the mock data. The readiness area explicitly shows insufficient data/ranges, calculation time and an explanation action. Recurring availability uses weekdays without calendar dates to distinguish recurring preferences from scheduled workouts. All nine existing destinations remain available. HRV and sleep summaries use the readiness evidence, without an extra data request.

## Functional checks

Browser checks covered navigation across the nine sections, the workout dialog, readiness explanation, shared coach drawer, closing with Escape, focus restoration, retaining a chat draft without sending, nutrition's Open chat action, grouped profile/assistant/training editors, chart zoom/reset, and availability editing. Invalid zero-minute input was rejected. A valid day change updated the staged Training summary; it was restored before leaving, without saving personal preferences. No messages or workout publications were submitted for testing.

Dashboard day saves use the existing preference API and revision guard. A separate client guard retains the revision from when editing began and refuses to overwrite newer preferences after a background refresh. Save errors retain the editor and draft. Readiness requests are coalesced; the compact hero does not fetch tomorrow's forecast. UTC database timestamps and explicit offsets are normalized before displaying calculation time.

Automated verification:

- Production build and TypeScript check: passed.
- Journal tests: passed; single-day updates, preservation of other preferences, rejection of stale/unversioned edits and UTC/offset timestamp handling.
- Chat rendering tests: passed.
- Activity visual/data tests: passed.
- Backend preference validation/stale-revision test: passed against a temporary database.
- Diff whitespace check: passed.

One additional backend test, `test_api_requires_review_and_validates_preferences`, still fails at its existing draft-generation expectation (400 versus expected 200). This exact failure is already listed in [the earlier QA record](docs/qa/2026-11-04-daily-review-test-failures.md). No backend source was changed for this redesign. The complete backend suite was not run.

## Follow-up polish and limits

- P3: the mock's hand-drawn headline underline and circular workout-icon backing are omitted; the working interface uses the actual contour asset and a clear icon instead.
- Existing long coaching/review forms remain available behind their existing disclosures; this pass preserves the app's full planning behavior.
- Browser verification did not submit changes to the user's real preferences, food log, provider connection or Garmin publishing. Automated checks cover the request/revision boundary; real saves still use the existing backend validation.
- This is visual and interaction QA, not a WCAG compliance audit. Screen-reader journeys, 200% zoom and touch hardware keyboards were not comprehensively tested.

## Implementation checklist

- [x] Apply the selected journal system to the existing app.
- [x] Replace the goal slot with actual readiness and evidence.
- [x] Simplify repeated settings, maintenance fields and chart controls.
- [x] Keep navigation, forms, reviews and integrations available.
- [x] Verify desktop/mobile states and compare against the visual target.
- [x] Confirm the final rendered readiness calculation timestamp after UTC normalization: the browser showed “Calculated 09:41 AM” in Asia/Jerusalem, and naive UTC/explicit-offset equivalence is covered by the journal tests.

final result: passed
