# Dashboard and analytics redesign — review plan

Requested 10 October 2026. Planning and mockups only in this round; implementation follows design selection.

## Confirmed design choice

The user selected **Modular Canvas (concept 6)**. Use its navigation and widget canvas as the implementation direction. Every dashboard graph is user-replaceable; the initial layout is only a starting point. Add graph and Replace graph use the same builder, with access to all supported stored metrics and activity fields, chart types, periods, filters and sizes. Replacing one graph preserves the rest of the dashboard. No default graph is mandatory or locked. Save changes locally and restore them on reopening the app.

## What exists

- The React app uses anchor links to sections on one long page.
- Dashboard cards can be reordered and hidden, but the registry contains only steps, last activity, weekly calories, and readiness.
- Settings already stores birth date, sex, height, weight, timezone, and units. Weight history is imported separately from Garmin.
- Local read-only inspection found 1,061 `max_met_fitness` archive records through 29 September 2026 and nine `activity_vo2_max` records. Both include `vo2MaxValue`. These are preserved archive records; VO2 is not yet exposed as a normalized metric or supported by the assistant's metric catalog.
- Existing assistant tools supply summaries and activity evidence; a general plotting response contract and plot renderer still need to be added.

## Proposed navigation

Use separate routed screens, with a persistent navigation bar styled as tabs or a sidebar according to the chosen mockup:

| Screen | Purpose |
| --- | --- |
| Dashboard | User-selected graphs and summary widgets |
| Activities | Ride/run history and activity detail |
| Health | Weight, VO2 max, resting HR, HRV, sleep and other imported metrics |
| Assistant | Conversation and a large plot workspace |
| Training | Preferences, goals and training calendar |
| Nutrition | Meals, recipes and targets |
| Maintenance | Equipment and maintenance history |
| Profile | Personal details and manual weight entries |
| Data & sync | Garmin connection, coverage, imports, exports and backups |
| Settings | Provider and application preferences |

Each screen has its own URL, reload/deep-link behavior, and browser Back/Forward support. Only the selected screen is visible; forms may remain mounted to preserve useful drafts and filters during navigation. Existing assistant links open the relevant screen or activity detail. Mobile navigation wraps or uses an accessible menu.

## Design exploration

The ten interactive concepts use illustrative values, not personal health results. They vary structure as well as color:

1. **Quiet Indigo** — light/dark neutral surfaces, indigo accents, familiar sidebar and balanced dashboard.
2. **Graphite Studio** — compact horizontal tabs, graphite surfaces, precise analytics layout.
3. **Cobalt Rail** — narrow navigation, more room for plots, blue emphasis.
4. **Warm Editorial** — warm neutral surfaces, orange details, open chart rows and editorial typography.
5. **Violet Workspace** — dashboard with a companion assistant column and violet accents.
6. **Modular Canvas** — rearrangeable-looking widget grid with a clear graph library.
7. **Performance Console** — compact navigation and a dominant performance scatterplot.
8. **Wellness Journal** — health-first summary, VO2 dial and a large weight-history view.
9. **Research Desk** — analytics-first page with coverage table and plots above the assistant.
10. **Dashboard Focus** — minimal top navigation, one dominant chart and compact supporting widgets.

Use neutral backgrounds and restrained accents; green is not the primary theme. All concepts have responsive equivalents and keyboard-accessible controls. Pick or combine concepts before applying a design system to the application.

## Customizable main dashboard

- Add graph opens a builder: metric(s), chart type, period, aggregation, sport/activity filters, and size.
- Support time-series lines, bars, scatterplots, dual-metric comparisons, and summary/dial widgets where appropriate.
- Permit multiple instances of the same metric with different periods or filters.
- Add, replace, configure, resize, move, remove, duplicate, and restore widgets; persist the complete configuration locally. Replacement opens the graph builder for the selected widget and retains its position unless the user changes it.
- Provide drag-and-drop plus Move up/Move down controls.
- Pin an assistant-generated plot to the dashboard using the same saved chart specification.
- Start with a suggested layout, but let the user replace every widget. Defaults include VO2 dial, weight history, resting HR/HRV, and recent activity.
- Widget-specific periods can override the shared dashboard period and are visibly labeled.
- Display units, source, date, coverage, and missing-data states. Do not connect lines across substantial gaps silently.

## Personal profile and weight

- Move existing personal fields into a discoverable Profile screen; retain current validation/storage.
- Birth date calculates current age automatically. If the user prefers age-only entry, store age together with its as-of date; do not silently invent a birth date.
- Include relevant reference-population input for VO2 comparison, height, unit preferences, timezone, and goals.
- Show Garmin weight history automatically with latest reading date and source.
- Add a dated manual weight entry when Garmin has no measurement or the user wants to log one. Manual entries support correction/deletion history and kg/lb conversion.
- Keep profile weight and dated measurements consistent through an explicit latest-reading rule. Do not turn a single profile value into a historical measurement.
- Keep imported and manual readings identifiable; manual entries do not overwrite Garmin originals. Define a deterministic same-day selection rule while preserving both observations.

## VO2 max

1. Inspect source payloads and sport identifiers to separate running and cycling estimates, validate units, timestamps, duplicates and positive numeric values.
2. Normalize preserved history idempotently without losing the raw records. Add a supported live-sync path if the Garmin client exposes it; otherwise clearly show archive-only coverage and last measurement date.
3. Add latest value and history to Health, the dashboard widget library, and assistant tools.
4. Build a dial showing the value in mL/kg/min, measurement date, source and sport. The dial indicates position on a documented reference scale, rather than implying a physiological maximum.
5. Select and cite an authoritative, versioned age/reference-population table during implementation. Display its category and applicable age band. Keep Garmin's own category separate if available.
6. Missing age/reference input shows the number with a Profile prompt; missing VO2 shows a clear unavailable state. Unsupported age bands do not receive a guessed rating. Fitness age is a separate measure.

## Assistant plot workspace

- The assistant can query any supported stored metric or activity field through validated application tools and request line, bar, scatter or comparison plots. It does not execute arbitrary generated code or SQL.
- A shared chart specification carries metrics, axes, units, date range, grouping, aggregation, filters, source, pairing method and coverage.
- Return numeric data and chart specifications as structured results, separate from explanatory text. Persist them with the conversation so reload works with both configured providers.
- Show one plot at full width, two side by side on wide displays, and three/four in a readable 2×2 workspace. Stack on smaller screens; target at least 360 px plot height on desktop. Every plot has Expand, Pin to dashboard and export controls.
- Four visible plots is a presentation limit, not a query cap. Additional results can be opened separately; never silently discard requested plots.
- Use all eligible history, beyond current list limits; aggregate or downsample only for rendering and report the method. Compute statistics before display downsampling.
- Include labels, units, date coverage, sample counts, excluded records, and readable hover details. Allow period/filter refinement in conversation and in chart controls.

### Required examples

| Request | Result and data rules |
| --- | --- |
| Weight over the last year | Dated Garmin/manual measurements; unit conversion; explicit gaps; relative year resolves using the user's timezone |
| Power versus speed across my rides | One point per eligible ride by default; measured mean power versus consistently defined mean speed; filter indoor/outdoor and cycling types; disclose rides missing power/speed; optional within-ride sample analysis is a separate mode |
| Resting HR versus VO2 max | Pair actual observations by local date first; optional explicit weekly aggregation or bounded nearest-date pairing; separate sports; show pairing coverage and method; no silent daily filling of sparse VO2 readings |

Flexible comparisons extend to supported metrics and filters. An unavailable field produces an explanation and a useful alternative, never invented observations. Correlation summaries do not assert causation; ride comparisons identify unadjusted factors such as terrain and conditions.

## Implementation sequence and acceptance

1. **Design direction selected:** Modular Canvas (concept 6). Finalize its typography, palette, responsive navigation, widget sizing and plot workspace during implementation.
2. **Navigation and shell:** split App.tsx into routed screens; migrate section links; verify deep links, reload, Back/Forward, drafts, mobile and existing modules.
3. **Profile, weight and VO2 foundation:** expose profile; implement dated manual weight; normalize VO2; verify source provenance, sport separation, units, idempotence and missing-data handling.
4. **Shared chart engine and dashboard builder:** validated specifications and query endpoints; persistence, duplicate widgets, reorder/resize and chart interactions. Existing layouts migrate without loss.
5. **Assistant plots:** structured streaming results with provider-neutral tools; large workspace; pinning, export and refinement. Verify all three example questions end to end with real local coverage checks and synthetic automated fixtures.
6. **Polish and regression:** chosen design across all screens; accessible contrast/focus, responsive layouts, production build, relevant backend tests, and regression checks for import/export, sync, training, nutrition and maintenance.

Completion means separate navigable screens, a saved user-built dashboard, sourced age-aware VO2 display, accessible personal/manual-weight data, and up to four large visible assistant plots. Existing data and unfinished work in the checkout must be preserved.
