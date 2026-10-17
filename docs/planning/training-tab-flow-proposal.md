# Training tab flow proposal — 15 October 2026

Status: implementation authorized by the user and completed on 15 October 2026; browser QC and documented limitations remain. See [implementation QC](../qa/2026-10-15-training/REPORT.md). The planning constraints below describe the original handoff.

## Intended experience

1. **Training maker:** discuss goals with the trainer. Change the composer label to “Tell your trainer what you want to work on”, the placeholder to “For example: Help me build an endurance and strength plan”, and “Ask” to “Send”. Update the keyboard hint accordingly. Scope these labels to Training.
2. **Choose the duration:** after discussing the long-term direction, ask “How many weeks would you like to train for?” Offer 4, 8, 12 and 16 weeks plus a custom value within the supported 4–24-week range. If the user already supplied a duration or event date, show it for confirmation instead of asking again. Do not silently accept the existing 12-week default as the user's choice.
3. **Review the proposed plan:** show the goal, duration, dates, weekly time, sport mix, training phases, FTP used, upcoming events and first seven days. Allow adjustments before approval. The trainer may explain the plan in conversation, but must not claim activation before a successful save.
4. **Approve and activate:** provide one final “Approve and activate plan” action after the duration and plan review. This interprets the request as duration confirmation followed by final plan approval, avoiding two identical approval prompts. If another plan is active, explicitly include its replacement in the review. Persist activation atomically and refresh the active-plan card and next-seven-days view from the saved result. Repeated clicks/retries must not create duplicate plans or workouts.
5. **Active plan:** show a clear Active label with goal and start/end dates. Only an approved plan feeds the rolling Next 7 days view. Keep pause/resume/cancel available.
6. **Next 7 days:** show compact dated workout buttons with icons, duration and type. Give strength, running and cycling distinct icons, and distinguish cycling types such as recovery, endurance, tempo and intervals with consistent colors and text labels. Show rest days explicitly. Color must not be the only identifier. Clicking a workout opens its details immediately below the weekly overview; opening another replaces the previous detail view. Clicking the selected workout again may collapse it.
7. **Workout details:** reuse the existing lap table for warm-up, work intervals/repetitions, recovery and cooldown, with durations and numeric power targets where supported. Strength shows exercises, sets, repetitions, rest and load guidance. Include session purpose and existing feedback/edit controls. Preserve selection by workout identity when refreshing; close details if that workout is removed.
8. **Separate today card:** move “Suggest a training for today” into its own visually separate card, outside Active plan / Next 7 days. Keep available-time and sport inputs. Suggestions use the active plan and recovery context, remain previews, and require an explicit reviewed action to change the saved schedule. A suggestion must not silently activate or replace a plan.
9. **Edit active plan:** add an obvious “Edit active plan” button opening a dedicated editor for goals, duration/end date, weekly availability, sport mix, events and individual sessions. Preview the effect on future sessions, then use “Approve changes”. Cancel leaves the saved plan unchanged. Preserve completed sessions and feedback, detect stale edits, and reconcile future workouts without duplication. Continue using the existing canonical active program rather than creating a separate plan store.

## Garmin FTP

- Inspect imported and synced FTP sources and identify the latest applicable cycling FTP, its recorded date and provenance. Existing coaching code currently takes FTP from the brief; actual Garmin FTP availability has not been verified in this assessment.
- Prefill the plan from the latest suitable Garmin FTP and display “FTP: … W · recorded …” with an override option. Do not require manual re-entry of a value already available. Preserve an explicit user override until the user chooses the Garmin value again.
- Keep cycling and running values separate. Do not infer FTP from maximum activity power or invent a measurement date. If missing or too old under the existing calibration policy, explain the gap and request only the needed clarification; preserve effort-based targets where appropriate. Check power-meter availability separately.
- Show any changed FTP and affected targets during plan review; avoid silently rewriting an approved plan merely because sync supplied a new FTP.

## Existing foundation and implementation sequence

Inspection found `ActiveTrainingPlan.tsx`, `TodayWorkout.tsx`, `WorkoutLaps.tsx` and `TrainingCoachPanel.tsx`, backed by `active_training.py` and `training_coach.py`. Active-program persistence, lifecycle controls, horizon validation and lap rendering already exist. TodayWorkout is currently nested in the active-plan section, and every upcoming workout renders details at once.

1. Assess the current proposal/save/accept paths, conversational duration handling and FTP data lineage. Identify which existing operations mutate an active plan and ensure proposal editing does not apply changes before approval.
2. Implement duration selection, explicit preview/activation and FTP resolution with existing revision guards and canonical storage. Determine whether explicit duration confirmation and FTP provenance need additional persisted fields before changing the schema.
3. Update Training-specific copy; build the weekly icon overview and single expanded detail panel; separate the today card.
4. Add the active-plan editor with a preview and atomic confirmed save, reusing existing session editing and scheduling behavior where suitable.
5. Verify the complete flow in an isolated database and browser, then update QC evidence. Keep this proposal pending until assessed and approved for implementation.

## Acceptance and QC

- A new long-term request prompts for duration with suggestions; an explicit duration is retained. A preview never becomes active without the final approval action.
- Approval survives reload and feeds the correct rolling seven local-calendar days. Repeated approval does not duplicate records; replacing a plan preserves history and leaves one canonical active plan.
- Available Garmin cycling FTP is used with the correct date and units; missing/stale values and manual overrides follow the stated behavior. Numeric lap targets use the chosen calibration.
- All workout types have readable icons, colors and text, keyboard operation and visible selection. Only one workout detail panel is open. Laps and repeated intervals sum to the prescribed duration.
- Today's suggestion is a separate card and does not alter the active plan without approval.
- Manual plan edits preview their impact, respect completed history, reject stale saves and refresh the weekly view after approval. Cancellation does not change stored data.
- Confirm Training copy, loading/error/empty states and narrow-screen layout in the browser. Run focused backend checks for approval/replacement/calibration/edit persistence and frontend typecheck/build.

## Assessment decisions

Recommended interpretation: one duration confirmation followed by one final plan approval; compact workout buttons with sport icons plus type colors; a separate editor opened by “Edit active plan”. Verify Garmin FTP availability and the existing confirmation policy before committing to the exact data changes. Any unresolved source or lifecycle issue should be recorded in QC rather than represented as already working.

## Detailed execution handoff

This section is the execution specification for the next model. It supersedes any assumption that this is only a cosmetic change. Read the repository instructions and inspect the current checkout before implementation; this document records inspected behavior, not a guarantee that files have remained unchanged. Do not reset unrelated local changes. No other model has been messaged or started as part of planning.

### 1. Establish the baseline and mutation boundaries

Read these files together before editing:

- `frontend/src/App.tsx`: shared Training/Assistant composer and proposal cards.
- `frontend/src/TrainingCoachPanel.tsx`: brief form, preview, draft creation and proposal events.
- `frontend/src/ActiveTrainingPlan.tsx`: review fetching, lifecycle buttons, workout rendering and change form.
- `frontend/src/TodayWorkout.tsx`, `frontend/src/WorkoutLaps.tsx`, and the Training page parent and styles located through their imports.
- `backend/app/training_coach.py`: `validate_brief`, `read_brief`, `save_brief`, `_store_brief`, `_preview`, `create_draft`, `propose_setup`, `save_setup`.
- `backend/app/training.py`: `accept_plan`, workout updates and revision history.
- `backend/app/active_training.py`: `activate`, `_fill`, `_reconcile_events`, `review`, `request_change`, `propose_adjustment`, `suggest_today`.
- `backend/app/training_prescriptions.py`: calibration validation, questions and target selection.
- `backend/app/main.py`: Training routes; `ai_tools.py` and `ai_chat.py`: tool contracts and trainer instructions.

Observed hazards to resolve:

1. TrainingCoachPanel's preview submit calls preview and then PUT coach. `_store_brief` also changes the active program. Make preview read-only end to end; do not simply relabel this button.
2. `create_draft` currently cancels planned workouts and supersedes the replaced plan before inserting the new draft. Defer those replacement effects to approved activation.
3. ActiveTrainingPlan invokes the mutating review endpoint on mounting/focus. Preserve existing recovery behavior during this work, but ensure opening an editor or preview cannot apply its candidate values through review. Assess event listeners and parent revision callbacks for repeated requests.
4. Brief revision and active-program revision are different concepts. Guard activation/editing against both, rather than assuming the brief revision protects the schedule.

Use disposable test databases for all mutation checks. Do not activate, cancel or edit the user's real plan while implementing or testing.

### 2. FTP discovery and resolution

`supplementary_sync.py` requests `get_cycling_ftp` and `get_functional_threshold_power_range`. Trace where their full responses are retained through sync and database code. Inspect the local stored shapes read-only; report only the fields needed for this feature. Do not print full personal payloads or credentials. Build small synthetic fixtures from verified shapes.

Implement a shared FTP resolver, preferably a focused `training_ftp.py` module. Its response should include watts, source, measurement date if present, fetch timestamp separately, usability status and a reason. Never substitute fetch time for measurement time. Explicitly whitelist supported fields and units from the observed payloads; avoid recursively choosing the first numeric field. Ignore nonfinite, nonpositive, out-of-supported-range, future-dated and wrong-sport records. Resolve multiple measurements by actual measurement time with deterministic tie-breaking. A static value without a measurement date may be shown as a candidate, but must not be presented as a fresh dated measurement.

Selection order: explicit manual override, otherwise latest usable Garmin cycling FTP, otherwise missing/stale guidance and existing effort fallback. Expose “Use Garmin FTP” when an override is present. Carry source/date into the existing calibration fields and add explicit selection mode if necessary to distinguish an override from an auto-filled value. Existing briefs without a mode need a compatibility rule: treat a saved explicit FTP as an override until the user chooses Garmin, rather than replacing it silently.

The existing power prescription requires power access, a dated FTP and an age of at most 90 days. Preserve that policy for this task; display unavailable/stale status rather than secretly weakening it. Reuse the same resolver in the form, assistant context and preview, with no sync/network request during rendering. Snapshot the selected value in the approved program. A later sync can offer an update but cannot rewrite the approved plan through resolution alone.

If no usable FTP is actually retained, document the precise missing endpoint/normalization step and implement only the necessary supported extraction or sync persistence. Do not claim FTP is available merely because the fetch method is listed.

### 3. Proposal state and API contracts

Use the flow `discuss → needs duration/details → ready preview → approving → active`. Editing follows `active → editing candidate → ready change preview → approving → active`. Failure returns to the same candidate with a visible error. Cancel discards candidate state. These UI states must not introduce a second authoritative active-plan store.

Duration must be explicitly supplied or confirmed. Add nullable confirmation metadata to the proposal/brief as needed; a legacy horizon of 12 alone does not establish confirmation for a new plan. Existing active plans remain valid. Include chosen weeks, start date and computed end date in the preview. Resolve event-date/duration conflicts visibly. Keep 4–24-week validation unless separately authorized to expand it.

Recommended contracts, adapted to repository conventions during execution:

- Extend the read-only coach preview to return normalized candidate brief, missing questions, duration confirmation state, resolved FTP provenance, roadmap, first-week sessions, affected future-session summary, source revisions and fingerprint.
- Add one atomic approval operation for a coaching preview, or strengthen the existing acceptance path to provide equivalent behavior. Request includes candidate input, preview fingerprint, expected brief/preference/program revisions, replacement identity if applicable and an idempotency key. Do not expose a new generic write tool to the model.
- Recompute validation and context under a write transaction at approval. On stale context return a conflict requiring a fresh preview. Persist brief, program, initial sessions and revision records together. Replacement cancellation happens inside this transaction. Roll back everything on failure.
- Store/reuse the approval result for an idempotency key; reject reuse with different candidate content. Two concurrent approvals must not duplicate sessions or supersede a newer plan. Reloads and request retries return the existing result.
- For editing, return a preview of changes to future sessions, then apply under the same revision checks. Preserve completed/skipped history and feedback. Show cancellations/rescheduling and horizon shortening explicitly. An end date before today or before a protected future event requires resolution rather than silent truncation.
- Existing draft routes must remain safe: creating or abandoning a draft must not cancel active sessions. Inspect callers before changing contracts. Reuse transaction-level helpers rather than nesting public functions that open separate database connections.

Choose the next unused migration number only after checking current migrations. Prefer fields in existing validated state JSON for brief metadata; use a small dedicated approval receipt table if needed for durable idempotency. Include schema changes in backup/restore validation and round-trip tests. Do not hardcode an assumed migration number.

### 4. Conversation integration

Update trainer instructions and registered tool schemas so a long-term request obtains the current active-plan context, asks only missing questions, and offers duration choices. An answer like “8 weeks” must continue the pending proposal; it must not be routed as an unrelated general question. Retain goal/sports/events from earlier turns. Add explicit confirmation fields to frontend types and tool validators together.

Use the proposal card for final approval; conversational “yes” can advance clarification but must not bypass the visible activation action. Avoid making “Save setup”, “Create draft” and “Accept week” three mandatory user steps. The main new-plan path should end in one reviewed activation button. Existing preference/event workflows may remain, but must clearly distinguish saving preferences from activating a program. Update success text only from a successful persisted response.

### 5. Frontend implementation

- Scope composer label, placeholder, Send button, loading text and keyboard hint by page. Preserve the Assistant page behavior. Put the copy in one small configuration object to keep labels consistent.
- Make TrainingCoachPanel the candidate editor/review, with duration chips and custom input, FTP source controls, roadmap summary and explicit activation. Keep candidate changes local until approval. Disable duplicate submissions while pending without discarding the preview on errors.
- Separate Active plan summary from Next 7 days within the section. Calculate seven local dates as today through today + 6 in the validated browser timezone; avoid elapsed UTC-day arithmetic across DST. Group sessions by local scheduled date and allow multiple workouts per day.
- Use one `selectedWorkoutId: string | null` for the weekly overview. Render one detail region below all seven days, linked by accessible button attributes. Order multiple sessions by time, then stable ID. Render explicit rest/no-session states without inventing a workout.
- Add a shared workout presentation mapping for sport, kind, icon, color and readable label. Proposed cycling labels: Recovery, Endurance, Tempo, Threshold, VO₂ max, Sprint; also Strength, Run, Race/Event and a neutral fallback. Match actual backend enums and use a fallback for older definitions. Use existing icons if available; avoid a new dependency just for icons.
- Reuse WorkoutLaps for the selected session; retain repetitions and units, feedback/edit and move-session controls. Keep expanded content readable on mobile. Show held/cancelled status accurately and exclude cancelled sessions from the normal upcoming list.
- Render TodayWorkout as a sibling card in the Training parent, mounted once, with the heading “Suggest a training for today”. A preview does not alter the schedule. Preserve the existing suggestion behavior; adding a new save-suggestion workflow is outside this task unless essential to an existing authorized action.
- Add “Edit active plan” opening a dedicated panel/dialog. Seed from a fresh persisted snapshot. Include explicit future-session editing rather than exposing only a free-text request. Preview before approval; show a conflict on stale revision and preserve unsaved user input for comparison/retry.
- On successful saves, refresh the canonical state once and update the overview. Audit `training-plan-changed`, focus listeners and `onChanged` propagation to avoid refresh loops. Do not fold the separate readiness-performance QC item into this task.

### 6. Verification matrix

Extend `test_training_coach.py`, `test_active_training.py`, `test_training.py` and `test_coach_remediation.py`; add focused FTP/approval test modules if useful. Required behavioral cases:

| Area | Required evidence |
| --- | --- |
| Preview isolation | Compare persisted brief, program and workout identities/revisions before and after preview and abandoned replacement draft; no active-plan changes |
| Duration | Missing duration prompts; explicit 8 weeks persists; legacy default is not silently confirmed; invalid bounds/event conflict rejected |
| Approval | Atomic new activation and replacement; retry/concurrent submission creates one result; changed context conflicts; injected failure rolls back all writes |
| FTP | Latest valid cycling record selected; dated versus fetch-only record; invalid units/value/future date; stale >90 days; missing meter; override wins; sync does not rewrite accepted targets |
| Plan editing | Goal/horizon/availability/event/session edits preview correctly; cancellation is read-only; stale save rejected; history and feedback retained; one canonical active plan |
| Calendar | Seven local dates, midnight/DST boundaries, multiple sessions/day, rest days and selected workout removed after refresh |
| Workout details | One expanded detail; exact lap totals including repetitions; power provenance and effort fallback; strength sets/rest preserved |
| Compatibility | Existing active/paused plans, old briefs, non-coaching weekly drafts and backup/restore still work |

Run focused tests first, then the repository backend suite, frontend typecheck/build and whitespace check. Browser-verify on a disposable database: new discussion → duration → preview → activate → reload → select two different workouts → edit/cancel → edit/approve → today suggestion. Verify keyboard and narrow-screen behavior. If a connected model is available, test “build me an endurance plan” followed by “8 weeks” and a follow-up change using synthetic data; report unavailable live checks honestly.

### 7. Execution deliverables and scope

Deliver source changes, any migration, focused fixtures/tests and a dated QC report with actual results, screenshots where useful, limitations and commands used. Link this proposal from that report and mark each acceptance item verified or outstanding. Do not reuse old passing-test counts as evidence for the new change.

This task covers the Training flow described above. The other recorded QC requests—activity deduplication on sync, Explore date ranges, readiness speed, VO₂ trend and general assistant tone/tool routing—remain separate. Do not publish Garmin workouts, change the user's real plan, send another chat a message or start another model as part of this planning-only handoff. The execution model should reassess the current files and the FTP discovery findings before implementing the specified design.
