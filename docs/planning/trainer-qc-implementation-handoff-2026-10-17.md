# Trainer QC implementation handoff — 17 October 2026

Status: implementation plan only. No fixes, migrations, tests, builds or live plan changes were executed while preparing this document. Intended for an implementation model that needs explicit scope, contracts, sequencing and acceptance examples.

## 1. Instructions to the implementing model

Work in `/Users/dotanhofman/Documents/garmin_app`. Read this entire document and the latest QC report before editing. Implement the phases in order; do not replace the app or rewrite the trainer from scratch.

The user explicitly said to run backend/frontend tests **only when asked**. Do not run `make test`, unittest, frontend tests, typecheck or a production build without a new user request. A plan containing validation cases is not permission to execute them. Source review and `git diff --check` are allowed. State exactly which behavior remains untested. Existing historical passing results do not validate new changes.

There are already uncommitted changes in backend planning, AI context, workout power presentation, larger cards, scrolling and QC documents. Inspect `git status --short` and relevant diffs. Preserve those changes. Do not reset files, switch away from the working checkout, commit, push or send this work to another chat unless the user requests it. Do not exercise cancellation, deletion, activation or event creation against the real database while validating.

Use existing API/database/revision patterns. Keep personal records local. This scope does not include Garmin publication, export, authentication, real account synchronization or a new automation.

Update the QC report item by item. Distinguish `implemented, source-reviewed`, `verified by an executed check`, and `pending`. Do not mark everything passed after editing source.

## 2. Authoritative scope and precedence

Primary source: `docs/qa/2026-10-17-trainer/REPORT.md`, especially the Pending sections and the additional weekly-total/daily-review/control notes.

Historical context: `docs/qa/2026-10-16-trainer/REPORT.md`, `docs/qa/2026-10-15-general/REPORT.md`, and the existing plans in `docs/planning/`. Later explicit user instructions override earlier assumptions. In particular, older plans requiring a confirmed weekly total and preserving clock-time intake are superseded here.

| ID | Required outcome | Current source-level situation |
| --- | --- | --- |
| QC-01 | Correct sports per weekday; up to three activities per day | `availability` permits one generic slot/day; separate `brief.sport_days`; generation often treats a date as occupied after one session |
| QC-02 | No redundant mandatory weekly-total question | `training.FIELDS`, `_context`, questionnaire and preferences form still require `weekly_minutes` |
| QC-03 | Manageable cycling/running volume derived from history and load, changes over time | Recent cycling dose helper exists, but chronic-load trends are not a complete shared sport-specific volume policy; running lacks equivalent integration |
| QC-04 | Named active-plan row expands blocks and controls | Existing name is synthesized from goal/event, blocks are separate; Latest review and Measured FTP progress are displayed |
| QC-05 | Delete active/canceled plan; retain completed activity records | Pause/cancel exist; no plan-delete endpoint/control |
| QC-06 | Remove “Build a week that fits”; keep today's suggestion | Heading sits inside a component containing essential trainer/review/preferences/history children; deleting the component would remove too much |
| QC-07 | Independent today suggestion genuinely ignores the plan | UI sends sport/minutes only; backend reads the active plan even when a sport was selected |
| QC-08 | Add upcoming cycling event and adapt surrounding week | Fixed-event parsing/reconciliation exists, but saving global setup does not itself reliably update the active program's separate accepted brief |
| QC-09 | Remove clock-time training preferences/intake | Date-only storage exists; preference form still exposes time inputs and legacy times can constrain generation |
| QC-10 | Review once per local day or on explicit review; reflect saved changes | UI posts review on mount/focus/revision; backend does substantial work before checking cached review; fill and review gates differ |

Pause/Resume remains required by the earlier QC note, even though the later simplified-card request lists Edit, Review, Cancel and Delete. Keep it inside the expanded plan controls.

Do not redo already implemented range parsing, early duration questions, named start dates, explicit activation, larger four-column cards, duration formatting, one expanded workout, scrolling or dated power estimates. Preserve them and cover them in acceptance review. Recent progression changes are source-reviewed but have not had tests/builds run under the user's current restriction.

## 3. Code map: inspect these exact areas

| File | Relevant entry points / responsibility |
| --- | --- |
| `backend/app/training.py` | `SPORTS`, `FIELDS`, `QUESTIONS`, `validate_answers`, `_context`, `save_preferences`, `list_training`, `draft_week`, `accept_plan`, `progression_proposal`, workout editing |
| `backend/app/training_questionnaire.py` | `_contextual_reply`, `_extract`, `turn`, `merge_structured`, `extract_structured`, `candidate_snapshot`; durable partial answers and provenance |
| `backend/app/training_coach.py` | `DEFAULT`, `validate_brief`, `parse_request`, `_preview`, `save_setup`, `approve`, roadmap; fixed events and separate sport days |
| `backend/app/active_training.py` | `capability`, `_program_workouts`, `_fill`, `_reconcile_events`, `review`, `read_active`, `set_status`, `reschedule`, `suggest_today` |
| `backend/app/training_prescriptions.py` | `cycling_dose`, `recovery_policy`, `endurance`, `strength`; existing provisional policy and explicit per-lap targets |
| `backend/app/training_load_charts.py` | `daily_rows`: recorded date, acute, chronic, low/high, source; do not fetch external data in planning |
| `backend/app/main.py` | `TodayTrainingRequest`, `ActiveTrainingRequest`, `/api/training/*` routes and error mapping |
| `backend/app/ai_tools.py` | `suggest_today_workout`, `propose_training_setup`, preview/adjustment tools and schemas |
| `backend/app/ai_chat.py` | `_trainer_instructions`, deterministic today-workout routing and argument construction, evidence/proposal rendering |
| `frontend/src/TrainingPanel.tsx` | Outer Training tab, old weekly-builder heading/controls, preferences form, history and session editor |
| `frontend/src/ActiveTrainingPlan.tsx` | Review requests, focus listeners, controls, blocks, Next7days, detail scrolling |
| `frontend/src/TodayWorkout.tsx` | Current combined “Use my plan / preferences” selector and POST body |
| `frontend/src/TrainingCoachPanel.tsx` | Canonical preview/approve/edit flow; must remain reachable after weekly-builder cleanup |
| `frontend/src/TrainingSetupProposal.tsx`, `TrainingAdjustmentProposal.tsx` | Proposal saves and change notifications |
| `frontend/src/trainingCandidate.ts`, `trainingCalendar.ts` | Partial-candidate handling and timezone/date-only helpers |
| `frontend/src/WorkoutLaps.tsx`, `workoutPower.ts` | Explicit planner fractions → advisory watts; preserve source/date and actual calibrated targets |
| `frontend/src/styles.css` | Existing card layout, detail clearance, responsive controls |
| `backend/app/migrations/001_initial.sql`, `016_training_planning.sql`, `023_active_training.sql`–`026_training_questionnaire.sql` | Plan/workout relationships, feedback/revisions, active singleton, review history and durable questionnaire |

Current API: POST `/api/training/today`; POST `/api/training/active/review`; POST `/api/training/active/change`; GET `/api/training`; PUT `/api/training/preferences`; POST `/api/training/setup`; coach preview/approve routes; PATCH workout schedule. There is no plan-delete endpoint and no HTTP read-only active-plan route yet.

## 4. Design decisions: implement these contracts consistently

### 4.1 One canonical weekly schedule, without clock times

Introduce `answers.week_schedule`, with exactly seven weekday entries when complete. Weekdays remain Monday=0 through Sunday=6. A partial candidate may omit days; omitted means unanswered, not rest.

```json
{
  "week_schedule": [
    {
      "weekday": 0,
      "mode": "training",
      "total_limit_minutes": 120,
      "activities": [
        {"slot_id": "mon-primary", "sport": "cycling", "min_minutes": 60, "max_minutes": 90},
        {"slot_id": "mon-secondary", "sport": "strength", "min_minutes": null, "max_minutes": 30}
      ]
    },
    {"weekday": 1, "mode": "rest", "total_limit_minutes": null, "activities": []}
  ]
}
```

The abbreviated example above is a partial candidate. A complete saved schedule has all seven days. `activities` order supplies primary, second and third priority; no fourth slot. Stable slot IDs identify choices through editing/review. Repeated sports on a day are allowed for an explicitly requested two-session day, but slots have distinct IDs. Never infer a second session from a duplicate parser extraction.

Rules:

1. Rest means zero activities. Reject rest plus sport entries with one clear correction message.
2. Training means one to three slots. Sport and maximum duration are required for each filled slot. Minimum is optional and is an availability preference, not a required prescription length; recovery work may be shorter.
3. Durations are finite positive whole minutes within existing supported bounds. `total_limit_minutes`, when present, is an additional shared daily ceiling. Each slot cap also applies. No requirement to use every available slot/minute.
4. A day with multiple activities may generate multiple workouts, each tied to a slot. Keep workload/quality limits across all those sessions. Prioritize the primary slot when budget is scarce.
5. No `start_time` in this new preference contract. Preserve the selected program start **date** and timezone.
6. Use this same schedule resolver in chat, preferences, preview, approval, rolling fill, event reconciliation and rescheduling. Do not maintain two independent sources of truth in `availability` and `brief.sport_days`.
7. Add a small shared module such as `training_constraints.py` for normalization, day/slot lookup, date capacity checks and legacy conversion. Do not scatter another set of weekday tests across all callers.

Partial-update semantics: omission preserves the existing value; an explicit rest row replaces that day’s activities; removing an activity targets its stable slot ID; clearing an optional cap uses an explicit null/removal operation. Do not shallow-merge whole nested sport/day maps in a way that erases siblings. The saved schedule is complete, while a conversational patch may be partial. Centralize that merge before validation.

Sports: use a shared catalog with stable IDs, labels and prescription capability. Include cycling, running, strength and hiking, plus a custom/other sport entry with a stored label. Rest is a day mode, not a workout sport. Hiking/other can be scheduled as a simple duration-based session/event without fabricated cycling watts, running capacity or strength exercises. Keep specialized generation only where supported; a generic slot can use an explicitly confirmed easy session, with no invented sport-specific calibration. Audit every current three-sport whitelist, AI schema, type, equipment rule and icon. Merely adding `hiking` to `SPORTS` will leave template lookups crashing.

### 4.2 Availability, optional cap and estimated dose are different values

Introduce `answers.weekly_caps` for optional user limits. Absence means no additional user weekly cap. An entry is `{max_minutes, range_min_minutes?}`. Explicit zero means the sport is unavailable that week; it is not missing. Preserve “6–7 hours” as 360–420 minutes, with 420 as a ceiling and no minimum-volume obligation.

Do not store the algorithm's changing estimate as a user answer or give it a user-confirmation timestamp. Return it in planning context as `volume_estimates[sport]` with estimate, availability ceiling, optional cap, evidence window, recorded coverage, load observations, rationale, confidence/status and policy version.

Every planning path resolves the operational ceiling from:

```text
effective sport ceiling = min(available sport capacity,
                             optional user cap if supplied,
                             current history/load-based dose estimate)
```

Shared daily limits constrain total allocation separately. Summing per-sport capacities does not authorize exceeding a shared day limit. Fixed events count against budgets and can produce an explicit exception requiring review; never silently shorten a confirmed event to force a feasible estimate.

### 4.3 Explicit today-workout source

Add `mode: "independent" | "plan"` to frontend requests, `TodayTrainingRequest`, AI tool schema and handler inputs. New callers always send it. For older callers omitting it, default to `independent`; update chat routing explicitly so intended plan requests still use `plan`. Return `mode_used` in the response.

Independent mode uses completed activities, recent load, current health/recovery, feedback, applicable personal safety restrictions, equipment/calibration, requested sport and available minutes. It must not read or constrain by active-plan blocks, goal, weekday assignments, planned rest, planned workout or program FTP snapshot. Use saved personal calibration instead. Keep `active_plan_id` and `planned_workout_id` null in this mode. Never mutate the plan.

Plan mode reads the active program and adapts its intended workout. If there is no active program, return a useful `needs_input` response offering the independent mode; do not silently claim the result follows a plan. Paused/canceled plans are not active. Missing sport in independent mode uses personal preferences or asks one focused question, not the active plan's workout.

### 4.4 Read, review and mutations are separate actions

Add a read-only GET `/api/training/active?timezone=...` returning active program identity/name/status, blocks, upcoming workouts, and small review metadata. It must not generate or adapt sessions.

POST `/api/training/active/review` accepts `trigger: "auto" | "manual"` (default `auto` for old callers). The auto gate is checked before expensive readiness/history decoding. Run once per plan and user-local day; saved event/feedback/schedule changes and resume are explicit invalidation triggers handled by their mutation services. Manual Review deliberately re-evaluates current data. None of these require a background automation or open browser at midnight.

Keep daily state in the database, not just React state: last reviewed local date/timezone, relevant input revision and policy version. A new migration may add a small gate table keyed by root plan ID; use the next available migration number after inspecting the directory. The gate and schedule changes commit together. Concurrent auto requests recheck under the existing write-transaction pattern. Gather data outside a long write lock if practical; recheck input revision before applying, with at most one retry or a clear conflict response. Own output-workout revisions must not continuously invalidate the auto gate.

Keep detailed review evidence internally and per-workout change reasons. The user requested removing the Latest review and Measured FTP progress **panels**, not removing recovery calculations or all explanations. A small “Reviewed today”/last-reviewed status near the Review control is sufficient.

## 5. Ordered implementation phases

### Phase A — Foundation and compatibility adapters (QC-01, 02, 09)

1. Add shared schedule normalization and optional-cap resolution. Extend `validate_answers`, partial-candidate types, durable questionnaire schema and frontend types together.
2. Keep legacy reads working. Convert old `availability` plus `brief.sport_days` through the shared adapter. For each old day, use explicitly allowed sports; carry its old generic `minutes` as a shared daily limit so conversion cannot multiply capacity. No day entry becomes explicit rest unless the user supplied rest/unavailability. If sport membership is ambiguous, preserve it as legacy unresolved and ask only about the affected day rather than inventing a primary sport or discarding the whole setup.
3. Retain old raw preference/revision and approved-plan snapshots for audit. Normalize for new calculations. Do not mass-rewrite real approved schedules during migration. Save the new representation on the next authorized edit.
4. Existing `weekly_minutes` values have mixed historical meaning. Preserve them as labeled legacy limits until explicitly replaced/cleared; do not reinterpret them as proven fitness or silently raise them. New saves use `weekly_caps`. New derived estimates do not create an awaiting weekly-total question.
5. Remove weekly-total completeness from `FIELDS`/`_context` and questionnaire readiness. Retain optional natural range parsing for voluntary caps. Update stale-field logic so optional absence is not stale/missing. Keep real restrictions, equipment and unresolved required durations as meaningful blockers.
6. Update `_extract`, structured extraction whitelist, quote validation, partial merge and pending-answer handling. Support per-day/sport corrections without replacing unrelated days. Weekday60–90 plus Friday300 must not propagate300 to all cycling days or strength.
7. Remove preference `type="time"` inputs, clock questions, clock placeholders and `datetime-local` preference/schedule controls in this training flow. Use date-only editing. Legacy explicitly timed records remain readable, but clock values must not determine eligibility or appear as required user preferences. Reuse existing `scheduled_date`, `time_unspecified`, `schedule_timezone` and storage-noon convention; never display noon as a chosen start time.
8. Update all model-facing tool schemas/instructions and Save/preview payloads. Do not leave frontend submission emitting fields rejected by strict backend validation.

Completion checkpoint: the original sixteen-week request can retain cycling Mon/Wed/Fri/Sun, strength Tue/Thu/Sat, ordinary cycling60–90 and Friday up to300, without a clock or weekly-total question. A second strength slot on a cycling day survives Save and reload.

### Phase B — Shared dynamic volume policy (QC-02, 03)

Implement a focused module such as `training_volume.py`; reuse the evidence gathering and existing `cycling_dose`/`recovery_policy` instead of introducing a second disconnected planner. The existing research rationale is `docs/planning/training-progression-review.md`. Thresholds are provisional product rules, not physiological guarantees.

1. Build per-sport weekly duration/intensity evidence from completed records, using user-local dates and no future records. Normalize mountain biking/indoor cycling into cycling, appropriate run types into running, and hiking separately. Avoid double-counting a completed planned workout and its linked recorded activity.
2. Use trailing completed seven-day windows consistently. Retain the current robust recent-week approach as the initial baseline, with explicit coverage information. A covered week with no activity can reduce the baseline; an unsynced week is unknown, not zero. One isolated five-hour ride is not a repeatable long-ride dose. Retain the existing multi-ride/multi-week long-duration requirement.
3. Read recorded acute/chronic observations and personalized high/low bounds from `daily_rows`. Include measurement dates and freshness. These Garmin values can reflect mixed sports: label them as overall load unless a recorded sport-specific measure exists. Never split aggregate load arbitrarily between cycling and running, fabricate missing chronic load, convert load units directly to minutes, or fetch a real account while planning.
4. Make the load influence explicit and inspectable: `normal`, `elevated`, `rising`, `stale`, `missing`. Elevated current acute load or corroborated recovery difficulty can reduce a history-based ceiling; recent rising load prevents an increase. A rising chronic value can support a progression decision only alongside completed volume, consistency and tolerance. A single ratio or low-readiness value does not certify a safe dose or require universal rest.
5. Initial progression policy: preserve the existing conservative cycling increment rule (up to the smaller of15minutes and5% after multiple tolerated completions) as an explicitly versioned app heuristic. Add a separate running policy/config rather than implicitly importing cycling doses, watt assumptions or minimum durations. For a first implementation, do not add a running growth increment without repeated run-specific tolerance evidence. Any new reduction coefficient must be named/configured and documented; use existing graded easy/recovery reductions where possible rather than burying unexplained arithmetic in call sites.
6. When actual completed volume drops or recovery worsens, allow the estimate to decrease. When multiple weeks/completions support progression, allow it to increase up to available time/optional caps. Do not advance it from plan week number alone. Keep long-session and weekly ceilings separate.
7. Missing history: return a disclosed provisional estimate and one focused clarification if essential. Do not ask for past experience when records already answer it, or demand a total weekly budget solely to satisfy the old schema.
8. Return a complete explanation object including underlying baseline and factors, not only a number. Snapshot it in previews/reviews for reproducibility. If an estimate has changed, return a short reason and previous/current values. UI shows current estimated manageable volume separately from editable optional cap; no false “user confirmed” state.
9. Route `_preview`, `_fill`, `_reconcile_events`, active-week audit, `suggest_today`, legacy draft/progression APIs and manual reschedule capacity checks through the same constraints/budget resolver. Search every remaining `weekly_minutes` access. Do not leave an old zero-default blocking a valid new schedule.

Allocation invariants: fixed/completed commitments count once; remaining budgets never go negative; minimum-workout floors never increase a dose beyond remaining time. Allocate a whole week's adjustable doses together rather than repeatedly subtracting stale original totals. Preserve useful short sessions where feasible; real rest remains valid when no safe useful dose fits.

Completion checkpoint: the same supplied availability can yield different conservative doses as completed history/load/tolerance change, without changing the stored user availability or optional cap. No global five-hour prescription follows from a single long ride.

### Phase C — Multiple daily sessions throughout generation (QC-01)

1. Replace date-only `occupied` short circuits in `_preview` and `_fill` with per-date/per-slot occupancy and capacity checks. A fixed event consumes its selected/matched slot and shared daily budget, not the entire date unconditionally.
2. Attach `schedule_slot_id` to generated workout definitions. Legacy workouts lacking it must be matched conservatively by day/sport and counted toward capacity; do not generate duplicates just because a slot ID is missing.
3. Remove or redesign the blanket six-sessions-per-week cutoff. It would suppress valid multiple-activity days. Bound sessions by permitted slots, dose budgets and appropriate recovery/quality rules. Frequency is availability, not an obligation to fill every slot.
4. Account for same-day and adjacent-day strength fatigue when assigning key cycling/running sessions. Avoid adding a hard second session solely because another slot is free. Recovery cycling uses only allowed cycling slots.
5. Update rescheduling, candidate-session edits, approval revalidation, event reconciliation and rolling children to enforce per-slot and total-day limits consistently. Use date-only comparisons in the user's timezone, not raw UTC `.date()`/timestamp prefixes.
   Date-only sessions may share the storage-noon timestamp. This is not a real timed overlap. Match their separate slot IDs and aggregate duration rather than rejecting them as simultaneous or deduplicating by timestamp alone.
6. Ensure frontend Next7days renders every session with a distinct ID, correct sport label/icon and existing single-detail/scroll behavior. Hiking/custom sports need their own readable labels and a neutral suitable icon, never a bicycle fallback.

Completion checkpoint: Monday cycling plus strength produces two permissible distinct cards when load/budget supports both; Tuesday strength-only never gets a recovery ride. Saving/reviewing twice never duplicates those sessions.

### Phase D — Independent today suggestions (QC-07)

1. Split Today's UI into source selection (Independent / Follow active plan), sport selection and minutes. Do not conflate blank sport with plan mode. Selecting a sport for an independent suggestion must not enable plan use. Plan mode can show/choose the scheduled workout when multiple exist today.
2. Update request/response contracts from section4.3 and all deterministic/chat tool paths. For explicit “ignore my plan” select independent. For “today's planned workout” select plan. For a simple standalone ride question, use independent unless the conversation explicitly chose plan mode.
3. In `suggest_today`, branch on mode **before** `read_active` and selecting `planned`. Build independent context from completed evidence and personal preferences/calibration. Delete all implicit plan-derived branches from that path, including `cycling_days`, `rest_day`, program goal and approved program calibration selection.
4. Keep genuine personal restrictions, symptoms, equipment and blocked-sport constraints in both modes. An explicit ride-today request supplies today's sport/time, so a plan's usual strength-only day cannot veto independent mode. This does not override a safety restriction.
5. In plan mode, preserve appropriate block/session intent within available minutes and recovery conditions. Do not use a scheduled run's duration/targets to construct a requested cycling workout without explaining a substitution. Multiple planned workouts need an explicit workout selection or focused clarification.
6. Return useful no-plan/paused/canceled/no-session states. Keep suggestions read-only. Show estimated watt provenance where applicable using the shared lap renderer, not a new guessed conversion.

Completion checkpoint: changing only the active plan's rest day, goal or workout does not change an independent suggestion given identical personal history/health/request. Plan mode deliberately responds to those changes.

### Phase E — Review lifecycle and near-term events (QC-08, 10)

First implement the read/review gate from section4.4; then connect event changes to that lifecycle.

1. Frontend mount/focus reads current state and requests `trigger:auto` at most as needed. Backend is the authority for the daily gate across tabs/restarts. The Review button sends `manual`. Deduplicate overlapping requests; ignore stale responses after plan/timezone changes. No repeated mutation chain from `training-plan-changed` → review → `onChanged` → revision effect → review.
2. Define explicit invalidation paths for saved feedback, approved schedule changes, resume and event additions/edits/removals. These may refresh the affected week immediately, even if the daily auto review already ran. Failed validation must leave the last valid schedule intact.
3. Add a reviewed active-program event proposal/save path. Prefer an explicit endpoint/service, e.g. POST `/api/training/active/events`, receiving root plan ID, expected program revision, timezone and a stable-ID event upsert/removal. Do not silently make every global `save_setup` change overwrite the active accepted program.
4. Chat extraction creates an unsaved event proposal from the user's words and current program. Show date/title/demands and that surrounding training will be reviewed. Its save action calls the active-event service. Reuse proposal UI patterns; a simple event-entry UI may use the same service. Do not call `request_change` to create a new event; that service currently moves existing workouts.
5. Resolve “tomorrow” and “in a few days” with user-local date logic; ambiguous dates require a focused clarification. No clock question. Duration can be explicitly estimated from comparable recorded rides, with provenance, or requested if essential. Preserve supplied distance/climbing/effort. Do not overwrite unrelated events by date alone.
6. Save accepted event state to the active program's brief, increment its input/commitment revision, reconcile surrounding generated workouts and return the revised Next7days/change reasons. Also update the relevant saved setup consistently if the UI claims it saved there; state exactly which scope changed. Use one transaction or a durable pending-reconciliation state so a saved event cannot be silently ignored after failure.
7. Stable event ID makes retries idempotent; move/edit updates the same event and its linked workout. Ensure events just outside Next7days can affect recovery/preparation inside it. Count the event once across root and rolling child plans.
8. Preserve fixed event demands if they exceed available time or the estimated manageable volume. Show an explicit conflict/review state and reduce flexible surrounding sessions where appropriate; do not shorten the event, fabricate capacity or erase other accepted events. Preserve completed/published sessions and longer-term goals.
9. Make preview and immediate event changes obey sport slots/daily caps; an explicitly accepted exceptional event on a normally unavailable day is a labeled exception, not a permanent availability change.

Completion checkpoint: adding a hard Friday ride after today's review immediately changes the surrounding flexible workouts, appears once, and still appears after reload without activating a replacement sixteen-week plan.

### Phase F — Plan identity, controls and deletion (QC-04, 05)

1. Return the actual root `training_plans.name` and stable root ID in active responses. Do not use an arbitrary weekly child name or derive identity only from an event label. Preserve existing names; a future rename is outside this request unless needed by the editor.
2. Add a clickable accessible plan-name row (`button` + `aria-expanded`/controlled details, or native `details/summary`). Show name/status/date range. Expansion contains grouped training blocks with week ranges/durations and focus, plus Edit, Review, Pause/Resume, Cancel and Delete. Use existing block/summary helpers rather than inventing a second roadmap.
3. Fix Edit to pass the canonical root ID and open the existing reachable coach preview/editor. Current event dispatch uses optional `plan_id` even when response primarily exposes `id`; remove that ambiguity. Editing produces a reviewable replacement proposal; it does not silently activate changes.
4. Remove Latest review and Measured FTP progress panels from this card. Keep a compact last-reviewed indicator, per-session adjustment reasons and relevant missing-data/errors. Keep actual FTP calculations and preserved provenance behind the scenes.
5. Keep Next7days visible outside the expanded plan details. Preserve large responsive cards, hours/minutes, watts and one open workout detail. Paused status is clear and stops generation/adaptation; canceled status cannot Resume. Do not relabel canceled root plans as completed in history simply because the old `set_status` does so.
6. Provide Cancel and Delete as separate actions. Cancel stops future generated sessions and retains the visible plan/history. Delete removes the plan from normal app lists and prevents any further use. Both operate on a specified root ID with an expected revision, not whichever singleton happens to be current when a stale request arrives.
7. Implement deletion as an internal soft deletion/tombstone initially: add nullable `deleted_at` to `training_plans` via a new migration. This meets app-level removal while preserving completed workouts/feedback and avoiding fragile FK cascades. It is not a secure-erasure feature. Set the root and all rolling child plans deleted in one transaction, cancel their remaining local planned workouts, and remove the active singleton only if it points to that root. Do not touch another active plan. Completed activity records and completed workout feedback/performance remain retained.
   Add a root-plan revision column (default1) as well: `training_plans` currently has no revision and the active singleton’s revision is unavailable for an older canceled plan after another activation. Return `plan_revision` in plan/history responses and increment it on lifecycle/edit/delete changes. Delete uses `expected_plan_revision`; active status/event changes separately check the active program revision and root ID. Do not confuse workout, singleton and plan revisions.
8. Add DELETE `/api/training/plans/{plan_id}` with expected revision/conflict handling and a JSON confirmation request from the UI. Show “Delete [name]? This removes the saved plan and its upcoming workouts. Completed activities remain.” Active deletion includes stopping the program; no separate prior cancellation required. A canceled plan also has Delete in history. No real plan deletion during development.
9. Resolve rolling membership exactly as `_program_workouts` does: root plan ID plus child `context_json.program_id`. Centralize this membership helper for deletion/history/review and validate parsed contexts. Current FKs: active/review rows reference plans; workouts use ON DELETE SET NULL; feedback/revisions/performance reference workouts. Do not issue a naïve physical DELETE of the root. Soft deletion leaves internal review/audit rows intact; completed workouts can render a neutral “Plan removed” label without resurrecting the plan.
10. Filter tombstoned roots/children from normal history, active reads, preview replacement selection, generation and coach context. Guard approval retry: `approve` currently reuses deterministic `plan-approved-<fingerprint>` rows; an old approval request must never resurrect a deleted plan. Return a useful conflict requiring a fresh proposal identity. Deletion retry is idempotent; stale deletion of a superseded/new active root must not affect the new root.
    Preserve fingerprint-based approval idempotency rather than assigning a fresh random ID on every click. In the delete transaction, advance the source planning revision so a newly recomputed preview has a new fingerprint; the current preview includes `source_brief_revision` and source program state. Retain the old tombstone so retries of its old fingerprint are rejected. A fresh identical-intent plan is allowed through its newly reviewed fingerprint, not by resurrecting the deleted row.
11. Publish-status exception: do not imply a local deletion removes a workout from a Garmin device/account. Preserve published records and give an accurate local-only result if encountered. No Garmin API writes are part of this task.

Completion checkpoint: cancel preserves a named historical plan; deleting active or canceled plans removes them from app plan lists without deleting a recorded ride, feedback or strength performance. A stale tab cannot delete/cancel a newly activated plan.

### Phase G — Training tab cleanup (QC-06, 09)

1. Remove the “Build a week that fits” heading, its introductory weekly-builder copy and redundant advanced weekly Draft/Accept/progression controls from the normal Training tab flow. Do not delete `TrainingPanel` or blindly remove `TrainingCoachPanel`; both contain required functionality.
2. Keep: trainer chat and ready plan review/activation, active named plan/Next7days, standalone “Suggest a training for today”, collapsed training preferences with the new day editor, relevant plan history and session feedback editor.
3. Keep preferences reachable through the active plan Edit flow as well as their collapsed entry. Replace required “Manageable weekly minutes” inputs with the read-only changing estimate and optional weekly cap. Distinguish them in labels. A blank optional cap must submit absence/null-removal, not0.
4. Use day rows with Rest/activity choices and “Add another activity” up to three slots; duration controls per slot and an optional shared daily limit. No time-of-day inputs. Make removal/reordering explicit and keep stable slot IDs.
5. Ensure `aria-labelledby="training-title"` still references a real sensible Training heading after removing the old heading. Keep focus/scroll targets used by chat review and session editing. Verify no remaining text tells the user to open a removed card or clock field.

Completion checkpoint: the user sees an understandable trainer/active-plan/today-workout flow with no “Build a week that fits”, Latest review panel, Measured FTP progress panel or08:00 preference.

## 6. Acceptance matrix for later authorized validation

These are scenarios to implement against and, when requested, execute on disposable data. They are not executed results.

| Case | Input/action | Required observable outcome |
| --- | --- | --- |
| A1 | Original16week FTP/endurance/bodyweight request; cycling all except Tue/Thu/Sat; weekday60–90; Friday up to5h | Correct sport days, separate Friday cap, no clock/weekly-total re-question, blocks plus reviewable week |
| A2 | Mon cycling90 + strength30, shared total100 | Distinct slots retained; generated combined time≤100 and per-slot caps; no requirement to fill both |
| A3 | Three explicitly selected sports on one day | Save/reload/preview retains all three; meaningful labels; no fourth slot |
| A4 | Explicit rest; later change only Thursday to strength | Rest has no sessions; only Thursday changes; unspecified does not become rest |
| A5 | Legacy one-slot/day + sport_days and old08:00 | Adapter preserves shared capacity/sport restrictions; date-only flow has no clock gate |
| A6 | Hiking/custom sport entry | No three-sport lookup crash or cycling watts; readable session/event retained |
| B1 | Daily availability supplied, no weekly total | No required weekly-total question or0-minute default budget |
| B2 | Voluntary6–7hours cap; then remove cap | Range preserved,420 ceiling; blank removes cap rather than means0; explicit0 still respected |
| B3 | One310min ride among repeated short rides | No automatic300min starting prescription; evidence/rationale explains repeatable baseline |
| B4 | Same availability, several tolerated weeks, then interrupted/covered-zero weeks | Estimate can rise conservatively then fall; user availability remains unchanged |
| B5 | Missing/stale chronic load or aggregate multi-sport load | Confidence/source explicit; no zero invention or arbitrary sport split |
| B6 | Current high acute load plus fatigue vs a moderately low readiness score alone | Graded adjustments from combined context; no automatic all-week rest from the score alone |
| C1 | Independent ride request on active plan strength/rest day | Uses requested cycling/time and personal evidence; plan IDs null and no plan-day veto |
| C2 | Change only active plan goal/workout with identical independent inputs | Independent result unchanged by that plan change |
| C3 | Plan mode active / paused / absent; two planned activities today | Follows selected planned session or useful clarification; no silent fallback claim |
| D1 | Open/focus two tabs repeatedly on same local day | One automatic adaptation; cached read is cheap and stable |
| D2 | Local midnight / Jerusalem DST; then explicit Review twice | Date gate uses local day; manual review works without duplicate workouts/revision churn |
| D3 | Save upcoming Friday event after daily review | Event saved once, surrounding flexible work adjusts immediately, persists reload |
| D4 | Retry/edit/move event, two events same date, event just beyond7days | Stable identity, no duplicate/overwrite; appropriate visible surrounding adjustment |
| D5 | Fixed event exceeds estimated dose/day cap | Event demands retained and conflict explained; no fabricated safety/fitness claim |
| E1 | Click plan name; Edit; return from ready preview | Correct named root/blocks/control set, reachable editor, no unintended activation |
| E2 | Pause/resume/cancel | Clear persisted status; paused does not generate; canceled cannot Resume |
| E3 | Delete active and canceled synthetic root with rolling children and completed feedback | Hidden/deactivated locally; future local work canceled; completed activity/feedback/performance retained |
| E4 | Deletion retry, stale tab, old approval retry | Idempotent or clear conflict; never touches a different active root or resurrects deletion |
| F1 | Normal desktop and narrow Training view | No removed panels/clock fields; four-column cards adapt; all controls readable |
| F2 | Click cycling then strength card | Exactly one detail expands and scrolls/focuses correctly; correct hours/watts/exercises |

Useful existing regression locations: `backend/tests/test_training.py`, `test_training_coach.py`, `test_active_training.py`, `test_training_questionnaire.py`, `test_training_date_only.py`, `test_training_ftp.py`, `test_training_load_charts.py`, and `frontend/tests/`. Add focused meaningful coverage where appropriate, but do not execute it until the user asks. Old temporary UI fixtures under `/private/tmp` may not exist later and are not repository dependencies.

## 7. Older QC and work not to lose

Older reports contain historical failures subsequently fixed. Read their superseding status before opening new repair work. Preserve these behaviors: current-day readiness sources without yesterday-as-today labels; source/date-aware FTP authorization; date ranges through today; activity rename upsert identity; VO₂ trend controls; educational questions without unnecessary record tools; natural trainer tone; sleep score once with HRV embedded in its plot. Do not certify them from old test counts.

The 15October general report still describes browser verification gaps for readiness loading reliability and VO₂ interaction. The current user request is a trainer implementation handoff, so these belong in a separate follow-up validation checklist, not an unbounded rewrite of health/sync/nutrition/export. If the next model is explicitly asked to execute all unresolved general QC too, inventory current evidence first and add those checks as a separate batch. Account/device/live-provider checks remain external and unverified; do not reopen them as proven regressions.

## 8. Execution checkpoints and final delivery

Suggested work units, each complete across its contract before continuing:

1. Schedule/cap/date-only schema + shared adapters + chat/preferences integration.
2. Dynamic sport-specific budget context + all planner consumers.
3. Multiple sessions per day + rolling/event/reschedule capacity rules.
4. Independent/plan today mode end to end.
5. Read/review gate + active-event proposal/save/reconciliation.
6. Named plan UI + state controls + deletion semantics/history guards.
7. Remove redundant UI + final source/acceptance review + QC evidence update.

At each checkpoint, inspect the diff for accidental removal of existing uncommitted work, stale required fields, implicit plan coupling and inconsistent request types. Do not run the whole frontend/backend test suite as a habit. If the user later requests tests, choose the relevant focused checks once and record exact commands/results; broaden only for actual failures or unresolved risk.

Deliver: changed-file list, completed QC IDs, any genuinely pending cases, migration/legacy behavior, source-only versus executed evidence, and whether backend restart is needed. Restart only after coherent source changes; do not apply destructive operations to the user's live plan as a demonstration. Do not say a live model conversation or Garmin device was verified unless actually authorized and observed.

## 9. Ready-to-copy execution prompt

> Implement `/Users/dotanhofman/Documents/garmin_app/docs/planning/trainer-qc-implementation-handoff-2026-10-17.md` in its specified phase order. First read the full plan, latest QC report and current working diff. Preserve all existing uncommitted work. Complete the weekday/multi-sport, optional/dynamic weekly-volume, independent-today, review/event, active-plan/delete and UI-cleanup requirements together through their shared contracts. Do not run tests, typechecks or builds unless I explicitly ask; report source-only limitations honestly. Do not mutate my real plans or Garmin account while checking the work. Do not commit or push unless asked. Update QC item status with actual evidence and report any remaining gaps.
