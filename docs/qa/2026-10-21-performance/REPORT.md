# Performance pass — 21 October 2026

Order agreed with the user: performance and smooth data loading → user’s detailed QC across all tabs → daily-use packaging.

## Measurements

Direct Python function timings on disposable SQLite copies of the real database. The source database was opened read-only for snapshot creation. Warm timings below average the two non-profiled repeat calls; initial calls include cProfile and cold filesystem/cache effects. These are not browser/network/model-response percentiles.

| Read path | Before, warm ms | After, warm ms | After first call, ms |
|---|---:|---:|---:|
| readiness_forecast | 10027.15 | 222.68 | 542.01 |
| plot_weight_all | 384.26 | 7.68 | 16.09 |
| plot_power_vs_speed | 1561.99 | 314.39 | 308.32 |
| plot_sleep_90_days | 431.12 | 5.22 | 11.05 |
| plot_recorded_power | 372.93 | 2.71 | 9.00 |
| plot_vo2_dial | 383.38 | 2.35 | 10.06 |
| plot_load_28_days | 1126.41 | 2.43 | 1174.43 |
| chart_catalog | 376.88 | 1.05 | 706.75 |
| import_coverage | 697.75 | 0.10 | 2331.09 |

Training history JSON used by the tab: 935,543 → 100,204 bytes (89.3% smaller). Editable definitions, IDs, revisions, feedback and displayed historical context remain; full source snapshots remain stored and available through the original API/export.

## Changes

- Load tabs on first visit, retain their DOM/state afterward, and load activity records only when their tab is active. Leave the data inventory/sync plan out of the dashboard’s startup barrier; load them with a separate status/error/retry in Data & sync.
- Share simultaneous GET reads and identical read-only chart POSTs, including development remounts. Each caller can cancel independently; all callers cancelling stops the transfer. Completed reads are not retained as a stale browser cache. Writes are never coalesced; successful writes prevent subsequent refreshes from joining pre-write pending reads.
- Start rendering dashboard widgets from the saved layout without waiting for the full archive/FIT metric catalog. Preserve assistant-to-dashboard pin review even when the dashboard has never mounted.
- Memoize plot coordinates and SVG geometry so hover/drag does not rebuild every mark; memoize the shared dashboard/assistant plot renderer. Zoom/pan/reset still use the full displayed evidence and gap boundaries.
- Build readiness sessions once per forecast and reuse them across 100 historical checks. Full output matches an unprepared reference; future observations and unfinished workouts remain excluded.
- Validate ordinary plot metrics through indexed existence checks rather than rebuilding the entire archive/FIT catalog per plot. Fetch only the scalar activity fields needed for summary plots; keep recorded speed extraction and the single-FIT-session fallback.
- Bound metadata/load caches and invalidate them with SQLite data_version on any other-connection commit, including same-count corrections/deletions. Recheck the version after calculation; never cache through concurrent changes. Close retained read connections on eviction and shutdown.
- Fingerprint incoming activity summaries so repeat sync does not reparse and reserialize large preserved FIT payloads. Reprocess changed summaries, retain enriched fields, repair absent normalized metrics and avoid no-op metric/payload updates. Keep per-interval atomic commits, overlap catch-up and Garmin request pacing.
- Poll sync progress only while manual/scheduled sync is active, using sequential requests. Keep other controls usable while it runs.
- Invalidate retained activity views and dashboard plots after sync/import completion; reload activity data on the next visit, or once immediately when already active.

## Calories correction reported during this pass

The weekly card queried garmin_export only. It now merges Connect and export days, preferring live corrected readings once per metric/day rather than summing overlapping copies. It distinguishes an incomplete past day from an upcoming day and labels the current week as week to date. The browser showed 19–25 October, 3/3 elapsed days, today ongoing. Past gaps stay explicit; future days and duplicate sources do not inflate totals.

## Browser checks

- All ten tabs navigated to the requested heading. Tool-observed click-to-snapshot intervals were 186–282 ms, including automation overhead; these are not paint/INP measurements.
- Dashboard weight plot zoom/pan/reset; assistant-generated weight and cycling power/speed plots, scatter zoom/reset; pin review from a fresh assistant-only tab without a mounted dashboard. No dashboard layout was saved by the test.
- Calories/readiness display; cached tabs retain forms/plots on navigation. The detailed business-function QC remains the user’s next step. Destructive/save/send buttons were not exercised against personal records as a performance test.

Evidence: [corrected dashboard](dashboard-calories.png), [navigation observations](navigation.json).

## Verification

- Chart/stream/load suites: 29 tests passed. Readiness forecast: 13; readiness calculation/persistence: 31; sync/recovery: 27; history: 5; FIT access: 6; QC remediation: 15; new performance contracts: 6.
- Node request test passed: shared reads, independent cancellation, fresh repeat reads, distinct chart requests and unshared writes.
- TypeScript/production build and whitespace validation passed.

## Limits

Cold catalog discovery and full import coverage still scan retained history (roughly 0.7–2.3 seconds in this run); they load independently and no longer hold the entire dashboard in its loading state. Warm values require unchanged committed data; a sync/correction deliberately invalidates caches. Model generation, Garmin responses and large imports retain external/I/O costs; no claim that every button completes in a fixed number of milliseconds. No detailed all-tab business QC or daily-use release sign-off is claimed. No commit/push was requested for this pass.
