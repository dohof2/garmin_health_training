# Assistant QC verification — 2026-10-10

Executed the [QC plan](../planning/assistant-qc-plan.md). Scope: conversational graph context, metric/period selection, GPS scope, analysis overlays, visible plots, basic history queries and existing provider/write validation.

## Fixes and checks

- Plot query context travels independently of the last 20 text messages. It includes metric, date range, sport, chart kind, GPS reference and overlays. The backend validates specifications and re-queries records; it does not treat assistant prose as evidence. Context survives refresh within the browser tab. Write authorization is never retained in this context.
- Checked metric replacement, period changes, repeat requests and adding/removing overlays. Explicit new requests are distinguished from changes to an earlier graph. Ambiguous replacement among multiple graphs asks which graph to change.
- Replayed the actual misspellings `macthed`, `mathced`, `refferance`, and `linair`. Matched-ride plots use all GPS matches plus the reference ride, not the displayed ten or all activities.
- Supports one to four named plots, semicolon-separated requests, ordinary lists of metrics, and relative days/weeks/calendar months/years. Explicit ISO ranges and leap-year boundaries are covered.
- Reference lines are **off by default**. An explicitly requested unspecified reference line uses the mean and is labeled Mean. Numeric horizontal lines use the graph's Y units. Trend lines and correlation are also opt-in.
- Linear regression and Pearson correlation use all selected observations before the 2,000-point display reduction. Health comparisons pair real local dates; activity comparisons pair activity IDs. Missing data are never filled. Empty sets, fewer than three points and constant axes produce explanatory results instead of invented statistics.
- Dashboard line, bar and scatter graphs have Add trend line / Remove trend line buttons. Toggling saves the widget configuration; verified weight and power-versus-speed, including reload persistence. Dials have no trend control. Changing an analyzed graph to a dial clears incompatible overlays.
- Plot creation scrolls the graph into view; Show these plots brings previous plots back into view. Graphs expand and retain CSV/pinning controls.
- Long assistant replies are bounded when included as text history, preventing oversized history from breaking subsequent requests. Stream errors remain visible even after partial text.
- A live Qwen 3.5 2b smoke test found recent-activity and seven-day health questions choosing unrelated tools. Added direct validated routing for these ordinary questions. Retested against actual records: three recent activities with recorded HR/power summaries; seven-day sleep/step coverage. Model access was local Ollama only.

## Recorded-data checks

The reproducible read-only command is:

```sh
PYTHONPATH=backend .venv/bin/python scripts/assistant_qc.py
```

Aggregate results are in [assistant-qc-results.json](assistant-qc-results.json). At the time checked:

| Request | Observations | Result |
| --- | ---: | --- |
| Weight, last year | 75 | Optional mean line; full weight history has 925 dated values |
| Cycling power versus speed | 389 paired activities | Pearson r 0.533; R² 0.284 |
| Resting HR versus cycling VO2 | 366 paired dates | Pearson r −0.214 |
| Four separate graphs | 925 / 14 / 100 / 2,978 | Independent requested metrics and periods |
| October 6 GPS-matched speed | 52 attempts | 51 GPS matches plus reference; mean 22.28 km/h |
| Same scope, add regression | 52 attempts | Fitted change +0.27 km/h, R² 0.003 |
| Follow-up last year after refresh | 23 attempts | Same scope and overlays retained |
| Follow-up replace speed with power | 22 attempts | Scope and period retained; missing power excluded |

The October 6 full-history speed trend explains very little variation and does not establish consistent improvement. A power-versus-speed scatter trend describes their relationship; improvement over time requires a date axis. Weather, effort, equipment and other conditions are not adjusted.

## Verification

- `PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests`: **222 tests passed**. Includes provider adapter contracts, GPS/date matching, history validation, sparse pairing, regression/correlation arithmetic, defaults, context retention and layout persistence.
- `npm run build --prefix frontend`: **passed** (TypeScript and Vite).
- Browser: verified GPS-scoped regression/mean/correlation together, chart expansion, Show these plots, refresh followed by a period-only request, dashboard weight regression and scatter regression, and saved trend persistence.
- No health observations, goals or training plans were changed by QC. Dashboard trend controls were exercised on the weight and power-versus-speed graphs.

## Limits

This QC covers the stated workflows and regression cases; it is not a guarantee for every wording. Less structured requests still use the selected model and validated tools. Correlation/regression are descriptive; no confidence intervals, significance tests, causal inference or adjustment for ride conditions are implemented. Chat text is session memory; only the bounded read-only graph/ride selections survive a page refresh in the same browser tab. The recent-activity shortcut searches up to 20 years of history and says which period it searched.
