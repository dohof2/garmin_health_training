# Seven-day HRV readiness revision — 13 October 2026

Evidence: Garmin describes HRV Status as a seven-day average compared with a personal historical baseline: https://www.garmin.com/en-US/garmin-technology/health-science/hrv-status/ . This supports smoothing HRV; it does not validate this app’s composite score or forecasting rule.

Readiness v3 uses the arithmetic average of nightly HRV over seven calendar days, requiring today’s observation and at least five nights. It compares the log of this average to a robust personal baseline taken from the preceding non-overlapping historical window. Single-night extremes no longer directly replace the average in the penalty; unusual high HRV retains a warning. Sleep, resting HR and workload retain their existing scoring. RHR has a separate baseline date window displayed in API evidence. Existing configurations migrate to a new formula-version identity preserving user parameters and old calculation records.

Forecast v3 projects one HRV night using the latest three-night arithmetic mean, then applies the same seven-day readiness calculation to six recorded nights plus the projected night. This recent-trend projection is an engineering heuristic, not a source-validated physiological prediction. Sleep/RHR use prior median projections; historical model evaluation recalculates all targets with v3. No guaranteed improvement or artificial score floor is imposed.

Local calculation check: today HRV mean 26.571 ms, projected mean 27.048 ms; today score 71, tomorrow uncorrected score 73. Final forecast may include a regression correction only when existing chronological validation rules select it.

Tests cover single-night smoothing versus sustained low HRV, missing nights, baseline separation, exact six-plus-one forecast average and improvement without a forecast cliff. UI displays measured/projected averages and forecast assumptions.
