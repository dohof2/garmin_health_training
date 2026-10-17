# Training coach acceptance QC — 12 October 2026

**Verdict: FAIL against the requested coach requirements. No product fixes were made.**

Snapshot: commit `b148031`. Existing regression: **389 backend tests passed**, frontend typecheck and production build passed. Independent acceptance: **16 probes — 4 pass, 7 partial, 5 fail**. Four additional live ChatGPT coach requests **all failed at runtime**. Passing regression tests therefore do not establish coach acceptance.

All plan creation, acceptance, feedback, rescheduling and cancellation used disposable invented databases. Offline recovery tests explicitly mock readiness to exercise repeatable paths; they do not validate biological thresholds. Live requests used invented records and the existing connected account, without importing user health data into the test database or sending it to the model. Existing real plans were not changed. Only this QA directory was added to the checkout.

## Requirement matrix

| Requested capability | Verdict | Executed evidence / missing behavior |
|---|---|---|
| Different long workouts with different lengths | Partial | Availability of 45/90/180/180 minutes produced 45/90/120/120-minute rides. Length varies, but generated cycling endurance is capped at 120 minutes and uses one conversational template. Availability slots themselves cap at 180 minutes. Fixed events can be longer. |
| Different workout types | Partial | Goal variants generated easy cycling and, for FTP, one controlled 2×6-minute interval session. No varied long-ride library or saved progressive tempo/threshold/VO₂/sprint prescriptions was established. Today's recommendation helper has more types than the weekly planner. |
| Save and follow the active plan | Pass at service level; live blocked | Accepted program, brief, blocks and workouts persist. Repeated review retained IDs/revisions without duplicate workouts. Actual model access fails as described in CQC-01. |
| Pause and cancel | Pass with UI naming limit | Pause stopped recovery-driven mutations. Finishing set the program to completed and cancelled outstanding sessions. The UI labels this **Finish plan**, rather than explicitly **Cancel plan**; Pause/Resume exist. |
| Different upcoming events | Partial | Trip/race flag, distance and ascent persist into fixed workout definitions. Hard/long/hilly events protect surrounding days, and race weeks are distinguished. Numerical route demands do not produce an event-specific climbing/terrain training progression. |
| Plan toward an event | Partial | Saved race horizon, building blocks, taper context and next-week continuation work. Tested consecutive weeks retained 120-minute easy sessions rather than a progressive event-specific build. |
| Surprise event / short-term adaptation | Fail for surprise replanning; partial overall | Saving a new hard three-hour event into a full active week produces a volume warning, but does not insert the event or rebuild existing neighboring long workouts. Feedback-driven reductions and checked schedule changes work. |
| Cycling plus strength | Pass at service level | Both sports appeared in the same generated week. This does not certify strength specificity or live coach delivery. |
| Strength primary/secondary and general-fitness/cycling focus | Fail | Strength-primary, endurance-primary and general priorities produced identical coached schedules/exercises. The weekly coaching selector does not use preference priority. Strength remains a generic foundation routine with no cycling-specific objective or progressive strength model. |
| Actual FTP-based power / HR goals; ask about power meter | Partial / absent requirements | Confirmed 250 W FTP gives a textual “90–95% of 250 W” work interval (225–237.5 W). Steps contain effort strings, not numerical watt targets. No power-meter availability question/option, threshold-HR configuration, HR zones or calibrated HR alternative exists. |
| Analyze past activity difficulty for future work | Partial | Six prior 30-minute rides capped generated sessions at 30 minutes; six 180-minute rides allowed 120-minute sessions. Garmin effects and feedback can suppress intensity. No comprehensive sport-specific power-duration/HR/load difficulty or demonstrated strength-capacity model was established. |
| Laps and times with power or HR | Partial | Timed steps exist and their durations sum to session duration. There are no structured per-lap numeric power/HR ranges or complete target-bearing workout export prescriptions. |

## CQC-01 — P1 — New coach tools fail through the assistant dispatcher

The model is shown `get_active_training_plan`, `propose_training_adjustment`, `suggest_today_workout` and `get_recent_training_mix`. All four were added **after** `TOOL_DEFINITIONS_BY_NAME` is constructed in `backend/app/ai_tools.py`. `execute_tool` looks up that stale map and raises `KeyError` for each name before its handler runs.

This was independently reproduced through the actual dispatcher for all four names. The live model then reproduced the user-facing failure in all four scenarios: FTP/lap targets, event-focused mixed planning, primary strength, and a surprise event. Each returned:

> The grounded assistant could not complete the request: 'get_active_training_plan'

The failure happens before meaningful plan advice is delivered. A direct unit call to the helper and a catalog-name check can both pass while actual model tool execution fails. The new behavior needs dispatcher-level and live acceptance coverage. **No repair was made.**

## CQC-02 — P1 — Surprise events do not rebuild an already-full active week

Reproduction: accept an endurance week with four 120-minute rides and a 480-minute cycling budget. Save a new Tuesday hard event: 90 km, 1,500 m climbing, three hours. Run the opening review.

Observed: the event is stored in the program brief, but it is absent from the scheduled workout list. Existing Monday and Wednesday rides remain 120 minutes. The warning says fixed and existing cycling sessions total **660 minutes**, exceeding the confirmed budget. Those days would be protected in a fresh preview, but existing workouts are not revised by that protection. A warning is useful, but it does not satisfy adaptation of the active schedule.

## CQC-03 — P1 — Changed goal and FTP do not reach the active program

Saving a new FTP brief with confirmed FTP 250 W after accepting an endurance program leaves the active program's goal as `endurance` and its FTP as `null`. The save path copies fixed events into active state, but retains the other original brief fields. The saved conversation brief and the followed program can therefore disagree.

## CQC-04 — P2 — Strength specialization and progression are absent

The coach supports multiple sports, but the executed primary/secondary priority comparison produced identical plans. There is no explicit strength goal model distinguishing general fitness, primary strength development, or cycling support; no assessment of current strength, progression of load/repetitions, or cycling-specific exercise selection.

Pull-up and dip bars are accepted equipment selections, but no strength exercise uses them. With only those bars selected for strength, the context reports equipment unavailable and fewer than two supported movements. This is a confirmed implementation gap, not merely a model-answer limitation.

## CQC-05 — P2 — Workout variety and event-specific progression are limited

Long cycling doses can vary with slot length, but automatic generated endurance tops out at two hours and generally uses warmup / conversational steady / cooldown. FTP adds one fixed two-by-six-minute template. The saved building blocks are direction text; they do not specify a comprehensive overload/recovery progression in duration, intensity or event demands.

The separate reviewed volume proposal is useful, but it is not an event-specific periodized plan. Distance/ascent/race inputs are retained and can influence recovery and duration estimates; retention is not proof of individualized training prescription.

## CQC-06 — P1/P2 — Equipment-aware numeric intensity prescriptions are incomplete

The planner neither asks whether a power meter is available nor stores that capability. FTP exists as an optional confirmed value, but ranges remain prose. There is no parallel HR threshold/zone system. Warmup, recovery and easy steps usually have qualitative effort only.

Stored steps are not a fully specified lap contract: no numeric target type, lower/upper watt or HR bound, or repeat-set structure is returned. A model can describe these conversationally, but the live audit was blocked and that would not establish that the saved plan contains executable targets.

## Passed controls and limits

Persistence, duplicate prevention, pause/finish semantics, feedback reduction and mixed sport generation passed in isolated service tests. Recorded training history influences conservative duration caps. These are useful foundations, but do not override the live dispatcher failure or the missing acceptance features above.

This run did not perform a fresh browser/device, accessibility, Garmin publication or biological-calibration audit. It did not change source code, fix schemas or bypass the failing dispatcher in order to obtain better-looking live results. No commit or push was performed.

## Reproduction

Run from the repository root:

```sh
PYTHONPATH=backend .venv/bin/python docs/qa/2026-10-12-coach/probes.py
PYTHONPATH=backend:scripts .venv/bin/python docs/qa/2026-10-12-coach/live_probes.py
```

The first script is offline and mutates temporary databases only. The second requires the existing connected ChatGPT account and sends only its invented fixture records; it makes four live requests. Each writes evidence beside itself.

Evidence: [offline results](results.json), [live results](live-results.json), [offline probe source](probes.py), [live probe source](live_probes.py). Live answers were not treated as passing merely because a request started.
