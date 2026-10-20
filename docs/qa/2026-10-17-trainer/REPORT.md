# Trainer loop and optional-time QC — 17 October 2026

Detailed handoff for remaining trainer QC: [17 October implementation plan](../../planning/trainer-qc-implementation-handoff-2026-10-17.md). Planning only; pending items below are not marked fixed by this document.

Execution plan: [start/review repair](../../planning/trainer-start-and-review-fix-plan.md), including17October optional-time follow-up. Covers natural questionnaire parsing, concise clarification, loop prevention and optional-time scheduling/display integration.

## Date-only scheduling

Availability accepts `start_time: null`. Unspecified sessions retain `scheduled_date`, `time_unspecified: true` and `schedule_timezone` in their definitions and API projections. Existing timestamp column uses a timezone-local noon anchor for storage only; it is not represented as user-chosen clock time or used as fictitious overlap evidence. Date-level capacity checks replace timed overlap checks where clock times are absent. Legacy explicitly timed workouts remain compatible.

Preview, activation, rolling fill/reconciliation and candidate/session edits preserve metadata. Schedule PATCH accepts scheduled_date, nullable start_time and timezone; assigning an explicit clock clears unspecified status. Frontend labels/grouping/editors display date only until a time is supplied. Initial direct approval now atomically UPSERTs previously absent preferences, fixing an activation path whose program could not roll.

## Regression evidence

- Full backend suite:466 passed24.015s (including the range follow-up below).
- Frontend executable tests:9 passed, including5calendar/date-only cases.
- TypeScript/Vite production build and whitespace checks passed.
- Focused training78 and date-only5 pass. Date-only tests cover16week direct activation and rolling, no clock metadata, preview duration/date editing, actual schedule PATCH movement and explicit08:00 transition, and legacy timed compatibility.
- Questionnaire17tests cover natural no-clock conversation through FTP authorization, cycling/core purpose, approximate capacities/budgets, restrictions and ready16week activation.
- The existing coaching follow-up test now selects actual coaching evidence rather than assuming it is the first tool; ready turns correctly emit setup review before preview. Routing and all plan assertions remain checked.

## Browser fixture and boundaries

Fresh isolated dynamic fixture at `/private/tmp/trainer-ui-qc/dynamic_server.py` seeds only synthetic cycling history and a225W11June measurement in `/private/tmp/trainer-dynamic-ui-qc/data`. Its chat middleware invokes real questionnaire `turn` and `assistant_answer`; no selected model/network call. All other Save/preview/approve APIs are real. The actual browser sequence on18018 passed: opening request without a clock → sure for stored FTP → cycling/core purpose → about5 pullups → identical about5 dips → about5hours cycling → about60minutes strength → none → review → explicit activation. The resulting program displayed active19October–7February. This exercises the real questionnaire, rendering and approval without a language-model call. [Browser evidence](natural-chat-activation.png). Production chat/preferences/active plan were not changed by implementation tests. No Garmin publication implemented.

## Conversation repairs

### Additional pending user QC notes — Next 7 days and plan controls

- **Accept ranges and explain unusable answers.** User reports that replying “6-7” to a weekly-hours question was not accepted. Use the pending question's units to interpret a range such as6–7hours, preserve the range, and avoid silently selecting a precise value. Weekly total remains optional when daily availability is already supplied. If a calculation genuinely requires a single value, explain that and ask for one exact number with an example. More generally, when a reply cannot be interpreted or validated, explain what was unclear and what input is expected (for example, “I couldn't interpret that as a number. Please give one number, such as6.”), rather than merely repeating the original question or echoing the answer. Test hyphen/en-dash ranges, inherited units, explicit units, invalid/reversed ranges, genuinely ambiguous replies and useful recovery prompts. Repaired by the range/clarification follow-up below; the original user report is retained here for context.

- **Larger workout cards with sport icons.** Implemented in the larger-card follow-up below: increased Next7days card size and readability. Explore upright/portrait cards (the user's “cards should stand” suggestion) across desktop/mobile layouts. Show a recognizable cycling icon for cycling and a strength icon for strength; retain readable workout-type labels and existing type colors. Verify multiple sessions per day and the single expanded workout detail behavior. The portrait layout is implemented; other pending items remain separate.
- **Weekly total is optional.** Do not require total weekly time after daily availability is given. Allow a user to supply a weekly cap voluntarily; when present, respect it alongside daily limits. This extends the weekly-time note below, and does not authorize filling all available time with training.
- **Review Next7days once daily or on request.** Refresh/adapt the upcoming sessions once per user-local day and when the user explicitly selects Review. Use the active plan, current block, load, recovery/health inputs and feedback. Verify persisted last-review date, local midnight/DST, repeated opens and concurrent requests so normal rendering/focus does not trigger unnecessary repeated schedule reviews. Show when the last review occurred and explain material adjustments. This is an in-app behavior requirement; no recurring Codex automation is requested.
- **Clear pause and cancel plan buttons.** Ensure the active plan has obvious, working Pause/Resume and Cancel controls, with clear status and consequences. These actions already exist in the implementation; investigate whether they are missing in a relevant state, hard to find, or ineffective rather than adding duplicates. Verify persistence, future-session behavior and paused/cancelled states without losing completed history. No real plan was paused or cancelled while recording this note.

All items above are recorded for later implementation/assessment; no app changes made for these notes.

- **Daily availability should be sufficient for planning.** The user finds “How much cycling time per week feels manageable? You can answer in hours or minutes” redundant after providing training days, weekday60–90minute availability and a separate Friday allowance up to5hours. Derive available weekly time from those day-specific limits without requiring a second weekly-total answer. Keep available time distinct from prescribed training volume: use recorded workload, recovery and the plan's progression to choose an appropriate dose rather than filling every available minute. Ask a focused clarification only if the day-specific availability is genuinely missing or conflicting. Pending implementation; no app changes made for this note.

Clarification answers contain only the next missing question, without repeated setup/availability summaries or save disclaimers. Identical new replies are processed against distinct typed pending fields; only replay of prior history is deduplicated. Approximate repetition counts retain approximation provenance; weekly hours convert to minutes for the pending sport without dropping other sport budgets. Bare beginner/regular answers, zero/none capacity, natural FTP consent, and broad optional time preferences are supported. No clock is inferred from morning. Old pending exercise questions retain compatibility. Incomplete or ambiguous replies get a targeted example instead of silently being discarded. Structured date-only availability accepts null clock values.

The17October pending notes in the prior trainer report are superseded by this execution evidence. Real connected-model semantic extraction remains unverified beyond existing synthetic contracts; browser testing bypasses only that extraction/model network layer.

## Weekly range and invalid-answer repair

Replies such as6-7,6–7,6to7hours, decimal hours and explicit minute ranges are accepted for the pending sport. Bare numbers inherit the explicit question units; an older prompt without clear units requests only the missing unit. Both bounds persist in the coaching brief and approved plan snapshot; the upper bound supplies an operational cap, never a required volume. The trainer acknowledges that rule once when accepting a range. Invalid/reversed/out-of-bound answers do not fill the field: feedback explains the problem and gives a valid example. Numeric capacity/duration and consent clarification prompts also explain what is expected instead of echoing the same question.

Regression tables cover hour/minute inheritance, hyphen/en-dash/to separators, word/decimal values, malformed/reversed ranges, negative/oversized values, progression to the next question, invalid reply recovery, and range persistence through explicit activation. Full backend466 tests pass24.015s. Frontend build and whitespace check pass. No live preferences/plan changed. Other pending cards/daily-review/optional-total notes remain separate.

## Larger Next7days cards

Implemented upright day cards with larger text and sport SVG icons, four per row above720px, two up to720px and one up to480px. Workout durations use hours/minutes (90minutes→1h30m;300minutes→5h) in both cards and expanded detail. Existing date grouping and one-open-detail behavior retained. Visually checked in the running app; no tests or build run, per user instruction. Other pending weekly-total/daily-review/control items remain unchanged.

## Cycling power display and detail navigation

User requested watts instead of RPE. Cycling lap presentation uses the workout's stored FTP reference and existing prescription ratios for recognized recovery/endurance/work laps, replacing RPE text with rounded watt ranges; the reference is labeled and original saved calibration/measurement dates remain unchanged. Existing power targets, running and strength guidance are retained. Applied to active detail, coaching preview, history and today suggestion presentation. User's225W reference visually yielded79–113W recovery,203–214W threshold and135–169W long endurance. Unknown workout mappings are left unchanged rather than guessed.

Selecting a workout scrolls/focuses the detail region after rendering, with sticky-header clearance. Closing a selection does not trigger another jump. Visually verified on the running app by selecting Long endurance: one expanded detail region focused with the correct lap table. No tests or build run, per user instruction.


## History-led progression and recovery context

User reports a generated five-hour ride at135W is too demanding and asks for gradual progression, more easy/recovery cycling, less reliance on the readiness score, and stronger training-theory context.

Implemented a shared cycling dose policy based on recent repeatable ride durations and recorded weekly volume, bounded by the user’s daily and weekly availability. A single longest ride and elapsed plan weeks do not authorize increases. Progression considers completed-session tolerance; availability remains a ceiling. Upcoming local generated rides are audited against these references during active-plan review, with a recorded explanation. Fixed commitments and published sessions require review rather than silent rewriting.

Recovery decisions combine recent workload, demanding sessions, feedback, autonomic/sleep observations and readiness. A low readiness score alone no longer automatically means rest. Short easy cycling can be selected on suitable available days; pain/illness and explicit restrictions retain their holds. Immediate recovery observations adjust the near term, rather than imposing the same response across the full coming week.

Trainer instructions now include goal-specific blocks, mostly easy endurance, separating demanding work, coordinated strength, individualized recovery, completed-versus-planned review, and avoiding catch-up stacking or simultaneous duration/intensity jumps. Scientific rationale and the distinction between research principles and provisional product heuristics are documented in `docs/planning/training-progression-review.md`.

Long-endurance guidance is lighter (55–70% of the stored FTP reference). Frontend watt estimates consume explicit per-lap fractions supplied by the planner, rather than guessing from workout names. Estimates retain the saved FTP reference date and do not refresh calibration. Actual calibrated power/HR targets remain authoritative.

Validation: source review and read-only inspection of local ride durations. No tests, builds or typechecks run, per user instruction. No real plan, preferences or measurement dates were edited during development. Runtime and end-to-end behavior have not been tested in this change.

## Pending: delete a canceled plan

After canceling an active plan, provide an obvious Delete option for that canceled plan. Define and explain what is removed, retain completed activity records, and confirm deletion before removing the saved plan and its remaining planned workouts. Verify that the deleted plan no longer appears in plan history or can become active again accidentally. User requested a QC note only; no deletion feature implemented and no plan deleted.

## Pending: weekday-specific sports and multiple activities per day

User reports that the trainer cannot correctly handle cycling on some weekdays and strength on other weekdays. Capture and preserve sport-specific availability through chat, saved preferences, plan preview, activation and subsequent reviews; do not replace one sport's allowed days with another's or schedule cycling on strength-only days.

Proposed backend model for assessment: each weekday has a primary value such as rest, cycling, strength, hiking, running or another supported sport, plus optional second and third activity values for users who want multiple activities on the same day. Distinguish an explicitly selected rest day from missing availability. Clarify how rest interacts with additional activities, and retain sport-specific time limits and any overall daily limit. Multiple allowed activities are options, not a requirement to prescribe all of them.

Acceptance scenarios for later implementation: cycling Monday/Wednesday/Friday/Sunday and strength Tuesday/Thursday/Saturday; cycling plus strength on one day; three activities on one day; an explicit rest day; hiking or another sport; and a chat correction affecting only one weekday or sport. Confirm that saving, reloading, activating and adapting the plan preserve these choices and that Next7days can display multiple sessions on a day. This is a QC note and proposed design only; no scheduling code changed and no tests run.

## Pending: history- and load-based manageable weekly volume

Manageable weekly time is a changing estimate, not a fixed value for the entire plan. Reassess it over time as completed training, fitness, acute/chronic load, recovery and reported tolerance change. Allow gradual increases when supported by sustained tolerance and reductions during fatigue, interruptions or reduced capacity, while respecting the user's current availability and optional cap. Do not increase it merely because another plan week has elapsed. Show the current estimate and explain material revisions.

Estimate manageable weekly cycling and running minutes from the preceding weeks of completed training, considering recent weekly duration, consistency, intensity, acute load and chronic load where available. Use sport-specific history rather than treating cycling and running minutes as interchangeable. Available daily/weekly time is a ceiling, not evidence of a tolerable training dose; an optional user-supplied weekly cap remains an additional limit. Do not require the user to supply a manageable weekly total when the stored history supports an estimate.

Extend and review the existing history-led duration caps so that load trends inform the estimate explicitly, alongside recovery and reported tolerance. Do not directly equate load units with minutes or use a single acute/chronic ratio as a guaranteed safe threshold. Account for missing load data, limited history, missed weeks and return after a break; disclose a provisional estimate when evidence is insufficient. Explain material changes to the recommended weekly volume and apply them consistently to plan generation and upcoming-session reviews. User requested a QC note only; no planning code changed and no tests run.

## Pending: simplify the active plan card

Show a clear row containing the active training plan's name. Clicking that row expands the plan details, including its training blocks and their durations. Include visible Edit, Review, Cancel and Delete buttons with working actions for the selected plan. This extends the earlier delete-canceled-plan note: the active-plan details should also expose a Delete control, with explicit confirmation and clear consequences before removal; preserve completed activity records.

Remove the Latest review and measured FTP progress sections from this card. Keep the Review action available; removing these displayed sections does not disable the underlying review or adaptation behavior. User requested a QC note only; no UI or plan data changed and no tests run.

## Pending: remove the weekly builder card

Remove the "Build a week that fits" card from the Training tab. Keep "Suggest a training for today" as the standalone workout-suggestion card. This concerns the weekly builder card; retain the trainer chat, active plan and Next7days. User requested a QC note only; no UI changed and no tests run.

## Pending: respect independent today-workout mode

User reports that "Suggest a training for today" still follows the active plan when the option to use the plan is not selected. Make the choice explicit and honor it throughout the request and backend recommendation flow. In independent mode, do not use the active plan's scheduled workout, blocks, goal, sport-day assignments or rest-day rules to choose or constrain the suggestion. Use the user's requested sport and available time, recent completed activities/load, current health/recovery, feedback and applicable personal restrictions instead. Do not save the independent suggestion into the plan or alter the plan automatically.

When the user selects the plan option, use the active plan and adapt its intended session to today's context. Verify both modes with an active plan, including a planned rest day, a different planned sport and a planned demanding workout; also verify independent suggestions without an active plan. The selected mode must persist in the request rather than being inferred merely from whether an active plan exists. User requested a QC note only; no recommendation code changed and no tests run.

## Pending: upcoming cycling events reshape the week

Support adding a cycling ride/event in the next few days and ensure the upcoming training week adapts appropriately around it. Capture the event date and relevant demands (duration, distance, climbing and intended effort when supplied), retain the event in the schedule, and account for its load when adjusting surrounding sessions, demanding-work spacing, recovery and weekly volume. Avoid duplicate sessions on the event date and preserve the active plan's longer-term goals. Show the resulting event and explain material changes in Next7days. Check events added through chat as well as any available event-entry UI; ask only for essential missing details. This records a capability to review/fix, not a request to create a real event now.

## Pending: remove clock-time training preferences

Remove specific times of day (for example08:00AM) from training preferences and trainer intake questions. Scheduling should use the date/weekday, permitted sports and available duration; a clock time should not affect the daily workout recommendation or whether a date-only session can be generated. Keep duration limits, including distinct long-ride availability. Review existing saved preferences and generated sessions so legacy clock times do not continue to impose unnecessary constraints or appear as required fields. This extends the earlier note that time of day is irrelevant to training intake. User requested QC notes only; no scheduling code or live events changed and no tests run.

## Full handoff implementation checkpoint — 17 October

Implementation follows [A–G execution handoff](../../planning/trainer-qc-implementation-handoff-2026-10-17.md). The original Pending descriptions above preserve the requests and observed pre-repair behavior; they are superseded by this current checkpoint, not deleted.

| QC ID | Source implementation | Evidence status |
| --- | --- | --- |
| QC-01 | Shared canonical seven-day schedule, up to three stable sport slots, explicit rest/unanswered, shared daily limits, slot-based generation/rolling/editing, hiking/custom duration sessions and multiple visible cards | Implemented, source-reviewed; acceptance cases not executed |
| QC-02 | Optional weekly caps/ranges/null removal/explicit zero; no required manageable-total intake; changing estimates separate from saved answers | Implemented, source-reviewed; not runtime-verified |
| QC-03 | Shared sport-specific completed-volume/load estimates, covered-zero versus unknown windows, dated mixed-sport load, tolerance/progression and long-session ceilings | Implemented, source-reviewed; provisional policy, not physiologically validated |
| QC-04 | Canonical named root row expands blocks and controls; correct Edit identity; Next7days remains visible; review/FTP panels removed | Implemented, source-reviewed; UI interactions unexecuted |
| QC-05 | Revision-bound confirmed local soft deletion for active/canceled roots and rolling children; preserved completed records/feedback/published ownership; old approval tombstone conflict | Implemented, source-reviewed; destructive scenarios not executed |
| QC-06 | Removed normal weekly-builder heading/legacy Draft/Accept/progression controls; retained trainer/review/today/preferences/history/feedback | Implemented, source-reviewed |
| QC-07 | Explicit independent/plan request mode, independent defaults and personal calibration/history without active-plan coupling; plan multiple-session clarification | Implemented, source-reviewed; invariance scenarios unexecuted |
| QC-08 | Read-only active event proposal and reviewed revision-protected save, stable identity, active-scope reconciliation and change reasons | Implemented, source-reviewed; event retries/partial boundaries unexecuted |
| QC-09 | Date-only preference/day editor, no clock controls/intake; legacy clock records retained for audit | Implemented, source-reviewed |
| QC-10 | Read-only active GET, durable local-day/input/policy gate before heavy review, explicit manual review, mutation invalidation and frontend request deduplication | Implemented, source-reviewed; concurrency/midnight scenarios unexecuted |

Migration027 adds plan tombstones/root revisions and durable review gate. Migration is supplied as source only; no production migration or live plan deletion/activation/event addition was exercised during implementation. Legacy raw revisions and approved snapshots remain retained; adapters expose ambiguity rather than inventing sport/rest assignments. Existing weekly totals remain labeled legacy limits until replaced/cleared. Local removal does not delete anything from Garmin/device.

No backend/frontend tests, typechecks, builds, browser mutation checks or live database operations were run under this handoff because the user expressly prohibited those checks without a later request. `git diff --check` is the only executed development check; historical passing counts elsewhere do not validate this new implementation. Runtime correctness, compilation, migration execution, multi-tab races and full acceptance matrix remain pending explicit validation authorization. Garmin publication remains planning-only. No commit/push performed.

### Runtime startup follow-up

Parent restarted the local backend after source freeze. Uvicorn completed application startup and is listening on127.0.0.1:8000 with the updated code and normal startup migrations. This supersedes the source-only migration/restart boundary above; no cancellation, deletion, activation or event-addition check was performed. Successful startup is not functional acceptance or a frontend compilation result. No tests, builds or typechecks were run.
