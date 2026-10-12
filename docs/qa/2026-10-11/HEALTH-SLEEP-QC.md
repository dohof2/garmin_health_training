# Health dashboard and compact sleep card

Completed 12 October 2026.

Health now uses an independent saved layout, with Add, Remove, Edit, Duplicate and reorder controls. Defaults are a half-width sleep card and weight history. Main Dashboard widgets and underlying measurements are unaffected.

The sleep card shows the latest recorded night initially, with previous/next recorded dates, a date picker and Latest action. It displays the selected night’s score and Garmin qualifier, sleep start/end, a timestamped overnight HRV graph, and foldable sleep measurements and score components. It uses stored full Garmin sleep/HRV responses and normalized measurements. Nonpositive HRV, out-of-sleep observations, invalid timestamps and synthetic fixture measurements are excluded; gaps are retained. Dates with only summaries show no invented HRV trace.

Validation: 366 backend tests, frontend typecheck and production build passed. Scope separation/persistence and overnight data tests cover missing dates, actual payload date validation, UTC timestamps, sleep bounds, gaps and fallback HRV arrays. Browser verified Add form save, date navigation, latest return, exact HRV clock/value readout, metrics expansion/collapse and compact layout. A temporary QA card was removed, preserving the final two-card layout. No physical mobile device check was performed.

Private screenshot is kept outside Git at `/private/tmp/health-sleep-card.jpg`.
