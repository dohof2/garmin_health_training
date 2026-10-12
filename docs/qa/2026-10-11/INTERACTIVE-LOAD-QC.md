# Interactive plots and dashboard load QC

Completed 11–12 October 2026, after the activity-overlay fixes.

- All Cartesian dashboard and assistant plots support zoom in/out, reset and pan controls; keyboard +/− zoom, 0/Escape reset, arrows inspect values. A pointer selection rectangle and touch value inspection are implemented.
- One shared X guide lists every overlaid series with its color and recorded Y value. If display samples differ, the nearest recorded sample in the same uninterrupted segment is explicitly dated by elapsed time; missing segments and dates are unavailable, never interpolated. Single-series/scatter inspection uses the actual selected observation.
- Added a rolling 28-calendar-day acute-load chart with dots and line, an optional chronic-load overlay persisted in the existing dashboard layout, and a green Garmin-recorded optimal acute-load area. Existing widgets were preserved.
- Full daily Garmin responses are retained locally in `garmin_sync_payloads` under `training_load_history`. The chart uses payload calendar dates, not request dates, and prefers recorded live data over archive values. Missing historical boundaries are not estimated. Refresh reports failed dates without exposing credential errors.

Validation:

- `make test`: 355 backend tests passed; frontend TypeScript check passed. Seven new load tests cover real payload dates, zero values, rolling bounds, missing/inverted boundaries, overlays, validation, gaps and preservation of additional raw response fields.
- Production build passed.
- Existing activity-overlay live assistant tests passed using invented records; the requested actual two-activity power chart was also visually verified.
- Browser verification: zoom button changes the power chart axes, reset restores them, keyboard inspection shows both activities' watt values. Dashboard chronic toggle saves and redraws both lines; shared date guide shows acute/chronic values and exact optimal bounds. Green area visually verified.
- Connected Garmin refresh completed all 28 requested days with no endpoint errors. All 28 days had recorded acute/chronic load and range boundaries. The rolling window advanced after midnight; the new day has no recorded load yet, so the chart correctly displays 27 recorded days rather than inventing a point.
- Pointer drag and mobile touch gestures are implemented but were not independently confirmed by the browser automation surface; keyboard/button zoom and shared readouts were verified. No physical mobile device test was performed.

Private chart screenshots remain outside Git at `/private/tmp/overlay-hover-zoom.jpg` and `/private/tmp/acute-load-dashboard.jpg`. No personal health records, credentials or screenshots were committed.
