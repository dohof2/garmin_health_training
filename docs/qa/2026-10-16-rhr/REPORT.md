# Same-day resting heart rate correction — 16 October 2026

Today's stored RHR now takes precedence in readiness. A date-only current-day reading is explicitly provisional; yesterday is used only when today's reading is absent. Selected evidence includes value, date, source and selection reason. The previous `rhr_previous_day` field remains actual yesterday evidence for compatible clients; new clients use `inputs.rhr` and `rhr_selection`.

Historical same-day records are labeled corrected reconstructions, not claimed to have been available at a past morning cutoff. Future-dated readings remain excluded. The personal reference baseline still uses prior offsets 3–30; today's value is not included in its own reference.

Readiness formula and forecast versions advance to v4. Saved parameter values migrate without deleting old configuration rows. Snapshot identity includes the new version/policy. Forecast uses completed-day historical RHR and labels its target-day value as projected; current provisional and future actual measurements cannot leak into its fitted history.

Frontend RHR detail and autonomic evidence now show selected same-day/fallback/projected status, date, source and provisional explanation.

## Verification

- Temporary-fixture regression verifies today 64 bpm is selected over yesterday 74 bpm and gives a smaller penalty; missing today uses explicitly dated yesterday fallback.
- Historical, forecast and configuration migration coverage verifies no future measurement leakage and preserved parameters.
- Full backend suite: 441 passed on final checkout. Focused readiness/forecast: 42 passed.
- Same-day input correction creates a new calculation identity/hash while keeping the earlier persisted snapshot intact.
- Frontend TypeScript/Vite build and whitespace checks passed.
- No production training plan or measurement was changed. No backend restart performed. Current listener PID 83760 requires restart to load v4.
- Browser visual verification remains unavailable through current computer-use connections.
