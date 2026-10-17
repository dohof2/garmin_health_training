# Trainer loop and optional-time QC — 17 October 2026

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

- **Larger workout cards with sport icons.** Increase the size of Next7days cards and improve readability. Explore upright/portrait cards (the user's “cards should stand” suggestion) across desktop/mobile layouts. Show a recognizable cycling icon for cycling and a strength icon for strength; retain readable workout-type labels and existing type colors. Verify multiple sessions per day and the single expanded workout detail behavior. Orientation is a design preference to assess, not an already implemented change.
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
