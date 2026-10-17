# Training coach remediation plan

Prepared: 12 October 2026. **Implemented 13 October 2026 — acceptance evidence in [implementation QC](../qa/2026-10-13-coach/REPORT.md).**

Source: [coach acceptance QC](../qa/2026-10-12-coach/REPORT.md), snapshot `b148031`.

## Intended outcome

One persistent, agent-led training workflow. The user describes goals, available time, upcoming events, equipment and feedback in conversation. The coach asks only for missing essential facts, proposes a concrete plan, and follows it while active. Training displays the active direction/current block, next seven days and Upcoming events; preferences/history are supporting sections. Manual event correction remains available.

The saved workouts must be useful prescriptions: named timed laps, repetitions where appropriate, and explicit power/heart-rate targets when calibrated inputs and accessible equipment support them. Rest, recovery and effort-based fallback are valid outcomes. No invented FTP, HR thresholds, biological capacity or successful save claims.

## Implementation order

### 1. Restore actual coach tool execution — CQC-01

- Register definitions and handlers in one canonical registry; build lookup maps after registration or derive them directly from that registry.
- Validate every advertised tool can execute through the same dispatcher used by the connected coach. Cover the four failing tools, valid inputs, invalid inputs and missing-context results.
- Retest the four original live QC prompts using invented data. Do not bypass the dispatcher for these tests.

Acceptance: each advertised tool has a matching executable schema/handler; no registry `KeyError`. All four live prompts complete with grounded results or specific clarification. This is the first dependency for all agent-facing work.

### 2. Make the active program the single source of truth — CQC-03

- Define a versioned program containing conversational direction/goal, target events, confirmed FTP/HR calibration, sport roles, building blocks and preferences.
- Apply approved goal, FTP, event and constraint changes consistently to conversation context, the active program and future generation. Preserve completed sessions and earlier revisions.
- Eliminate drift between the separately saved coaching brief and the followed active program.
- Keep revisions internal. Provide explicit **Pause**, **Resume** and **Cancel plan**, with Finish retained separately if useful. Pause prevents generation/adaptation; cancellation stops future local sessions and preserves history.
- Use atomic updates, stale-state checks and idempotency for activation and changes. Prevent multiple competing active programs or duplicate sessions on reopening.

Acceptance: change an endurance direction to FTP and FTP to 250 W; the active program and future target calculations use the new values. Restart/reopen retains the same plan and sessions. Pause/resume/cancel each have verified API and UI behavior.

### 3. Model upcoming events and replan the affected schedule — CQC-02, CQC-05

- Give events stable IDs, independent of date, with name, activity type, distance, ascent, date, race status and optional timing/duration/effort.
- Make coach-created events and manual corrections use the same validated save path. Permit correcting one event without replacing another accidentally; ask about multiple same-day commitments rather than silently overwriting them.
- Preserve an event's stated distance/ascent. Treat comparable-activity duration estimates as estimates with evidence and a reviewable range; do not fabricate estimates when coverage is insufficient.
- When a surprise event arrives, assess the current week and adjacent days/weeks, then revise the affected **existing** future workouts, not just empty slots. Reduce, replace or move generated sessions around demanding commitments.
- Preserve completed work and explicit fixed commitments. Surface irreconcilable time/volume conflicts with concrete alternatives; do not silently shorten a race or report adaptation that was not saved.
- Reflect race preparation, sustained climbing and event duration in relevant blocks. Multiple events must have a clear priority when their preparations conflict.

Acceptance: reproduce the full 480-minute week plus Tuesday's surprise three-hour ride. The event is scheduled, surrounding demanding sessions are appropriately revised, and the displayed total matches the saved schedule. If the budget cannot fit, show a specific unresolved conflict and options. Editing date/distance/ascent/race status updates both short-term scheduling and longer-term preparation.

### 4. Collect calibrated intensity and actual equipment access — CQC-06

- Ask whether the user can use a power meter for the relevant workout, including indoor versus outdoor access. Stored historical power does not prove today's access.
- Store confirmed FTP with date/source. Ask for confirmation if stale, conflicting or missing; do not invent it from average or normalized power.
- Collect available HR sensor and valid calibration inputs for the selected sport. Use a disclosed, supported method for HR zones; do not derive HR thresholds directly from FTP.
- Prefer power when available and calibrated; offer HR when appropriately calibrated, otherwise explicit effort/talk-test targets. Keep these fallbacks visible in the prescription.
- Changes to calibration update uncompleted workout prescriptions consistently with the program version.

Acceptance: 250 W FTP at 90–95% produces saved numeric bounds of 225–237.5 W. Test meter available/unavailable, indoor-only access, missing/stale FTP, usable HR calibration and no calibrated sensor. Each path produces correct targets or a focused question rather than unsupported precision.

### 5. Assess past work and build varied, progressive workouts — CQC-05

- Establish sport-specific baselines from recent volume, longest comparable sessions, intensity distribution, power/HR coverage, Garmin load/effects, completed plans and user feedback. Show coverage and uncertainty.
- Separate recorded stimulus from demonstrated capacity. Do not use one sport's longest session as another sport's endurance baseline. Account for terrain, stops, sensor gaps and session intent where known.
- Add a reviewed library of recovery, endurance, longer steady endurance, tempo, threshold, VO₂ and short-effort cycling sessions with different doses. Include running/strength only under their own constraints and calibrations.
- Support genuinely long rides beyond the current two-hour generated cap and three-hour availability limit where experience, recent tolerance, event demands and user availability support them. Confirm the user's limits instead of imposing unexplained caps.
- Turn building-block text into explicit weekly objectives and dose ranges. Progress duration/intensity based on demonstrated tolerance, with recovery/consolidation and event taper. Avoid treating every missing training label as an obligation to add intensity.
- Reconcile recorded activities with planned completion and deviations, asking when matching is ambiguous.

Acceptance: compare several baselines, time budgets and event profiles. Plans differ meaningfully in workout type/duration, progress toward the event, and recover after adverse feedback. A long event receives appropriate preparation rather than repeated identical 120-minute easy rides. Missing data produces conservative, explained alternatives.

### 6. Give strength a real role and progression — CQC-04

- Ask whether strength is primary or secondary, and whether its purpose is general fitness, cycling support or strength development. Save that role and use it in scheduling/volume decisions.
- Ask for essential strength experience, current capabilities, equipment and restrictions. Do not prescribe arbitrary repetitions for movements the user cannot perform.
- Add supported pull-up/dip-bar exercise variants and progressions. Distinguish equipment ownership from ability to perform unassisted pull-ups/dips.
- Build strength prescriptions with exercises, sets/repetitions or hold duration, rest and effort/load targets. Progress from recorded performance and feedback, with recovery around demanding endurance work.
- Cycling-support sessions should have an explicit rationale and exercise selection distinct from generic primary-strength plans; avoid promising cycling improvement from any single exercise.

Acceptance: primary strength, secondary general-fitness strength and cycling-support strength produce appropriately different schedules and prescriptions. Bar-only equipment has usable supported options or a specific capability question. Repeated completion/feedback leads to reviewable progression, and movement exclusions remain honored.

### 7. Save complete lap-based prescriptions — CQC-06

- Define a provider-neutral workout contract: sport, total duration, ordered named laps/steps, duration/distance termination, repetitions, target type and numeric lower/upper bounds where available, recovery, warmup and cooldown.
- Store canonical units and calibration provenance. Structured targets are authoritative; readable descriptions render from them.
- Validate target bounds, exact duration/repetition totals, permissible effort and equipment compatibility. Do not allow model prose to silently override backend calculations.
- Display every lap's time and target in the active-plan view. Strength uses a corresponding structured set/rep/rest contract.
- Keep local workout portability in scope; Garmin publishing remains deferred under the project roadmap.

Acceptance: prescriptions have consistent lap totals and numerical power/HR targets on the correct steps. Recovery/warmup/cooldown targets and repeat counts are unambiguous. Saved/reloaded/exported prescriptions match what the user reviewed.

### 8. Finish the agent-led Training experience and end-to-end QC

- Replace the competing goal/planning forms with one trainer conversation and concrete proposal/save flow. Infer direction only from user statements; goals are optional for a daily recommendation.
- Show active direction/current block and next seven days prominently. Show Upcoming events as the agreed list with manual Edit. Keep preferences/history collapsed and revision numbers out of ordinary presentation.
- Support “I have 60 minutes today”, surprise events, moving a long ride, “too hard”, rest/recovery, and primary/secondary strength through the same agent and saved state.
- Explain what changed and why. Distinguish advice, proposed changes, saved changes and unresolved conflicts. Respect the user's authorization for automatic reviews while keeping major direction changes reviewable.
- Re-run the independent QC matrix, dispatcher integration tests, persistence/restart checks, API/UI save flows and live coach scenarios using invented data. Assess semantic correctness, not just completion or HTTP 200.

Acceptance: all original failed/partial cases have evidence-backed passing results or explicitly agreed scope limits. Test ambiguous requests, stale proposals, unavailable sensors, gaps, conflicting events and interrupted saves. No real user plan changes occur merely for QC.

## Release gates

1. Tool dispatch works before further live-coach claims.
2. Saved program/state consistency and schedule-change semantics work before automatic adaptive-plan claims.
3. Calibration and structured workout contracts work before claiming power/HR lap prescriptions.
4. Variety, progression and strength specificity pass independent tests before claiming a complete personal training coach.
5. Full matrix and live agent/UI verification pass before marking the remediation complete.

Each implementation stage should remain reviewable and update the QC evidence. Passing existing regression tests alone is insufficient. No implementation, migration, model request, commit or push is authorized by this planning document itself.
