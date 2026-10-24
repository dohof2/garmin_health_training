# Readiness v5, forecast and recovery dial — 24 October 2026

## Implemented

Readiness v5 replaces the previous HRV/RHR 40%, sleep 35%, workload 25% model with six provisional penalty budgets:

| Factor | Maximum deduction |
| --- | --- |
| Last-night sleep quality/duration | 30 |
| Estimated recovery demand | 25 |
| HRV status | 15 |
| Previous three completed days' stress | 15 |
| Three-night sleep history | 10 |
| Acute/chronic load trend | 5 |

RHR remains dated/provisional context and cannot deduct score points, including through the forecast's regression features. HRV combines latest-night and seven-night deviations against a prior personal reference. Last-night sleep uses the larger quality or duration penalty; short sleep history has its own smaller budget. Stress uses daily-average records as a proxy, with gaps exposed. Missing required evidence produces a range or insufficient-data state, not invented measurements or zero penalties with a complete score.

### Recovery estimation

The accepted soft load-ratio threshold is 1.3 with a 28-day chronic time constant. Recorded compatible Garmin acute/chronic pairs anchor an explicitly app-modeled seven/28-day EWMA projection. Without anchors, the app reconstructs load from completed sessions and requires verified activity coverage. Both loads evolve in the no-further-training projection. Low chronic load disables ratio-based timing; it does not erase individual-session demand.

Each recent completed session has provisional assigned recovery hours derived from its recorded aerobic/anaerobic Training Effect. Interpolation knots are TE/hours: 0/0, 1/4, 2/12, 3/24, 4/36, 5/60. If TE is absent, the explicit fallback is `min(72, 2*sqrt(exercise_load))` hours. These are engineering estimates to calibrate, not Garmin's formula or a direct application of peak-EPOC thresholds to exercise-load units. Missing both inputs remains unknown. The displayed ±25% recovery range is heuristic sensitivity, not a calibrated confidence interval.

Countdowns use actual elapsed UTC time from session end, including offline periods and DST. FIT exports whose session timestamp repeats the start are reconciled against recorded start plus total elapsed time, so recovery does not begin before the activity finished. Active timer time alone is not substituted for elapsed time. A pure replay of activity and completed-sleep events applies each night's adjustment once, never once per sync/refresh. Sleep duration, quality and recent debt determine the bounded adjustment; its maximum is 10% of remaining hours and two hours per night. Unknown sleep has no adjustment. Old debt cannot be revived after expiration; sleep before an activity does not adjust that activity. Corrected sleep recomputes from the same stable event timeline. Latest eligible Garmin recovery snapshots, if supplied in future, are not sleep-adjusted again.

Recovery demand is the longer of session demand and load-settling time, not their sum. Explicit overlap credits prevent a second full load penalty and offset the sleep-induced recovery extension against the sleep deduction. These interactions and the weights remain provisional. Today's demand updates with the current clock; historical entries remain morning reconstructions.

### Forecast v5

Tomorrow uses the same six-factor calculation and projects the recovery clock to the assumed wake time. Future inputs blend 50% latest eligible observation, 25% recent-three median and 25% an up-to-28-day personal median. This fixes the fixed-seven-observation anchor that could carry a bad week forward despite improvement. Full-day RHR/stress are not treated as completed measurements during the current day. Projected sleep/stress are explicitly synthetic and never saved as observations. RHR is optional context and cannot block the forecast or enter the residual correction.

Forecast validation remains chronological and uses the same model version. Regression is chosen only with sufficient checks and lower error; the simpler blend otherwise remains. A forecast can be lower than today's score and is never artificially floored at today's result. Contributions, assumptions and uncertainty are available in its explanation popup.

### Interface

- Health has a recovery-time dial, updated on a one-minute visible-page interval, with a clear app-estimate label and details for individual demand versus load settling. Incomplete coverage is presented as a lower bound.
- Today/tomorrow readiness cards show the date, dial, short interpretation and forecast range. Each has a top-right **!** explanation button.
- Native modal explanations contain deductions, inputs, recovery estimates, assumptions and forecast diagnostics; Escape and Close dismiss them and restore focus. The existing **Why this result?** section remains below **Refresh readiness**, beneath both dials, with trend and adjustable parameters.
- Browser preview runs use `HT_APP_PREVIEW=1` and show a prominent fictional-data banner. The preview's high example scores are not the user's actual scores. Personal data was inspected read-only to check real deductions; it was not replaced by fixture data.
- If the frontend meets a still-running v4 backend, it asks for quit/reopen instead of showing v5 explanations for v4 scores. Normal launcher port 8765 was not interrupted.

## QC status from the user's notes

| Recorded issue | Status in this pass |
| --- | --- |
| RHR/sleep dominate and load/recovery is underrepresented | Addressed by new budgets, RHR context-only behavior, separate recovery/stress/history factors and visible deductions; physiological calibration remains ongoing. |
| Tomorrow anchored to a poor recent week | Addressed by the longer blended reference, latest-input sensitivity and consistent recovery projection. |
| Recovery countdown, individual hard session after rest and sleep adjustment | Implemented and covered by deterministic regressions. |
| Health recovery dial and clearer readiness cards | Implemented; browser verified with isolated fictional data. |
| Advice about tonight/tomorrow routed to a today-workout card | Exact forced-routing regression fixed and coaching instructions clarified; this is not sign-off on all conversational/model behavior. |
| Workout-block edits and persistent steady-endurance formatting | Still open; no saved workouts were modified in this pass. |
| Strength Garmin publishing; automatic rolling publication and one batch override | Still open; no Garmin writes or publication-policy changes in this pass. |
| Completion matching, actual-benefit adaptation, multiweek category coverage/variants and load-focus/ability-guided planning | Still open as recorded in the source QC notes. |
| General section-level ride analysis and complete app-data query coverage | Still open; recovery/readiness evidence is available through the existing readiness tools. |
| Telegram channel | Detailed plan only; no bot connection or implementation. |

The source [user QC notes](../2026-10-21-focused-qc/REPORT.md) remain the complete backlog; this report does not mark all trainer/Garmin requests complete.

## Verification and release limits

- **142 focused tests pass together** across readiness, forecast, recovery import, trainer adjustment, active program, advanced cycling, assistant routing, health layout, performance, load charts, sync-recovery and launcher behavior.
- New regressions exercise the countdown, once-only sleep adjustment, poor sleep, expiration, DST, unknown inputs, future-snapshot exclusion, hard session with a low ratio, evolution of both loads, RHR-independent scoring/correction, and bad-week forecast response.
- Frontend TypeScript/Vite production build and `git diff --check` pass. Browser verification covered the Health dial, both compact cards, both modals, keyboard dismissal/focus return and the retained lower explanation control. Local screenshots are ignored by Git and use fictional data.
- The legacy `test_training.py` suite still has 5 failures and 12 errors. The same 17 cases fail with the committed pre-change readiness modules; this is not full historical-suite sign-off. A separate existing `test_ai_tools.py` exact-catalog assertion omits an already-implemented event tool; no tool was added by this change.
- Existing configuration/calculation rows remain stored. On first v5 load, personal non-weight settings migrate while the old three-group weights are replaced by the new six-group defaults. No source activities, meals or saved plans are rewritten. Quit/reopen the normal app to load the changed backend.

Neither the weights nor the session-hour mapping, load projection or sleep coefficients are a validated physiological recovery formula. They are versioned, inspectable app estimates requiring ongoing calibration against actual experience.
