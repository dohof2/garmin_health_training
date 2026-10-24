# First implementation pass: roadmap areas 1–4 — 24 October 2026

The user asked to start smarter training, workout editing/Garmin, analysis/context and frontend improvements. They chose **one chat routing between Trainer, Assistant and Nutrition**. This pass implements useful connected workflows; it is not full release or all-tab QC sign-off.

## Implemented locally

### 1. Training completion and stimulus follow-through

- Date-only sessions can match a unique completed recording on the same local day and normalized sport, including indoor/virtual cycling and mountain biking. Explicit clock times still constrain matching. Ambiguous multiple recordings or competing same-day slots require manual linking. One activity cannot complete multiple sessions; in-progress recordings are excluded.
- Completed sessions remain visible in a separate last-seven-days list. Intended and recorded benefit are distinct; missing labels remain unknown.
- The benefit ledger shows last achieved and next materialized opportunities. Unplanned rides also contribute. Mismatches are reconsidered for up to 42 days, including later in the current week. A conservative adapter can replace one existing local quality slot, preserving total duration, a work-time ceiling and recovery spacing. Recovery, commitments, user edits, publication and advanced-work eligibility can defer replacement, with a reason.
- Two source-backed variants each for base, threshold, sprint and anaerobic cycling are available through the tool registry. Planner selection retains existing goal/category, phase, availability and tolerance gates. Threshold watt targets now use 95–100% of confirmed FTP rather than labelling 90–95% work as threshold. Total step time remains exact.

### 2. Workout format and Garmin

- Continuous easy-endurance format has a dedicated review/save path. It preserves duration, changes matching upcoming rides and stores the preference in both the personal brief and active program. Future steady/long-endurance prescriptions reuse it; interval warm-ups/cool-downs are unaffected. The original spelling-error/scope/“yes apply it” sequence retains the formatting request and presents the actual save proposal. Published rides become `update_needed`.
- Strength payloads preserve explicit sets, repetitions, prescribed numeric kilograms and timed rests using the installed `garminconnect` 0.3.17 helpers/catalog. Supported exact mappings include pull-ups, bodyweight dips, dead bugs, several dumbbell/barbell exercises, band rows and leg press. Unsupported variants (including uncertain assisted variants) are blocked before sending, rather than silently substituted. Strength read-back hashes include exercise, end condition, load and unit.
- The next-seven-days preview can opt into automatic publication after its initial approved send succeeds. Consent is bound to the Garmin account and active program. Subsequent complete app syncs review/reconcile that window using the existing durable worker, ownership hashes, revision checks and ambiguous-outcome safeguards. Unchanged remote workouts are not duplicated. Status, blocked items and an off switch are visible. One existing batch preview/approval covers the listed changes.
- Migration 031 adds the publication policy. Backup/JSON portability includes it; restoring a database disables automatic publication. Disabling before an initial worker completes prevents it enabling the policy afterward.

### 3. Analysis and shared data

- Activity IDs are retained from assessments, streams, comparisons and climb results, rather than only GPS comparisons.
- `analyze_activity_climbs` finds approximate sustained climbs from elevation, with a five-second median, descent/gap boundaries and explicit method limits. Power calculations use the full-resolution timestamps and recorded zeros. A full-climb mean is withheld when power coverage is incomplete; covered-only means are separately labelled. Elapsed/moving time and recorded-distance boundaries are available when supported. Comparable climbs require clarification.
- The reported “chunk of up hill” follow-up uses the retained activity directly, without replacing climb statistics with lap averages.
- Bounded app-data tools expose nutrition history (up to 31 days), saved profile/goals, sync state, every normalized health metric and retained archive categories. Existing activity/FIT/training/maintenance/chart tools remain available. Credential/account tables are excluded. Read-only snapshot tests pass.

### 4. One chat and activity plots

- **Chat** is the common conversation. It labels the answering role, offers Auto and manual role selection, and retains conversation/context in the browser tab across refreshes. Training and Nutrition entry points open this same chat. Food/target proposals return to the existing review controls; this does not bypass save review. New conversation clears the shared context.
- Activities have a **Plots** button beside More details. Available speed/elevation/power/cadence/HR traces support overlays, separate coloured scales, elapsed-time/recorded-distance switching, mouse selection zoom and reset. Axis switching retains the elapsed-time selection and overlays. Recorded gaps remain breaks. Distance comes from retained records/original FIT, never integrated speed or an invented fraction of total distance.

## Verification

- **21 new cross-service workflow tests pass.**
- Combined selection: **206 tests, 194 passing, 11 failures and 1 error**. All 12 unsuccessful cases also fail on committed baseline `a1cf887` (the checked-out HEAD); there are no new failing cases. The same baseline selection had 14 failures and 1 error; three completion cases now pass. This is not a clean historical-suite claim.
- Frontend production build, Python compilation and `git diff --check` pass. Vite still reports its bundle-size advisory.
- Browser checks used a separate `/private/tmp` database and a visible **TEST PREVIEW — FICTIONAL DATA** banner. Verified shared Chat, Training→Chat and Nutrition→Chat role selection, activity plots, three metric overlays, pointer-drag zoom, retained selection/overlays after switching to distance, and Reset zoom. The selected distance window was approximately 0.55–1.50 km before reset.
- Saved [shared-chat screenshot](shared-chat.png), [activity-plot screenshot](activity-plots.png), and [test comparison](validation-summary.json) contain fictional/test evidence only.
- No personal workouts/meals were edited, credentials copied, live AI request made, Garmin write sent or automatic publication enabled during this run. The isolated preview server was stopped after verification; the existing normal app server was preserved. No commit/push was requested or performed.

## Remaining work and rollout

- Live strength publication/read-back and device execution still need sport/device validation; catalog support is not external verification. Unsupported exercise mappings remain visible limitations.
- Cross-week stimulus follow-through and category-specific variant selection are implemented in the follow-up below. Fully individualized category cadence/dose and adaptation through successive real syncs remain broader QC/development. The replacement/ledger is an app heuristic, not a validated physiological response model.
- Reviewed edits support uniform work intervals, repetitions, recovery and current-method targets, plus explicit reductions in a named strength exercise. Heterogeneous/nested blocks, inferred or increased lifting loads and destructive batch replacement of externally edited Garmin workouts remain unsupported. Existing conflict safeguards remain.
- Automatic chat routing is a conservative first pass, not the full semantic/mixed-task orchestrator described in the Telegram plan. Complete pending-proposal/media handoff behavior and live-provider conversational QC remain. Telegram itself is still unimplemented.
- Phone/touch-device checks, unusual FIT distance resets, and large/missing original-record combinations need further verification. Available source files determine distance availability.
- Normal-use trial, legacy regression cleanup, readiness calibration and detailed all-tab QC remain open.

Quit and reopen the normal app before using this pass so the new backend and migration load with the frontend. Review/save the workout-format proposal and review the initial Garmin publication in the app when wanted; this development run did not apply them to personal data.

## Template references

The library uses app-specific conservative variants informed by [TrainerRoad power zones](https://support.trainerroad.com/hc/trainerroad-support/articles/115005942786-understanding-power-zones), [threshold workout formats](https://www.trainerroad.com/blog/threshold-intervals-for-cyclists-benefits-examples-and-tips-for-success/), [sprint formats](https://www.trainerroad.com/blog/how-to-improve-your-maximum-sprint-power/) and [anaerobic formats](https://www.trainerroad.com/blog/anaerobic-intervals-for-cyclists-how-they-make-you-faster/). These examples are not personalized prescriptions or a guarantee of a Garmin benefit label. Strength schema/mappings were inspected from the installed pinned library rather than inferred from exercise-name similarity.

## Activity-axis labels follow-up — 24 October

Added numeric Y ticks and explicit X/Y axis names with units. Each selected overlay has its own colour-matched Y axis in a separate reserved column; empty ranges show unavailable ticks and constant traces use a padded scale. The X title switches between elapsed time (minutes:seconds) and recorded distance (km). A horizontally scrollable frame preserves legibility on narrow screens. Build and whitespace checks pass. A fictional browser preview verified all five selected metrics with readable names/ticks, then switching to distance with all labels retained. See [axis screenshot](activity-axes.png). Only the isolated preview server was started/stopped; the normal app session was preserved.

## Overview chat and answer-start scrolling — 24 October

Removed the separate Chat navigation tab and moved the shared conversation to the top of the Dashboard overview, ahead of graphs. Existing `#assistant`/`#chat` links resolve to the overview. Training/Nutrition entry points navigate there and focus the chat input, carrying their role/context.

Answer scrolling now runs in a layout effect after the first nonempty text delta is rendered. The conversation viewport aligns that answer's beginning once; later chunks and completion do not force another scroll. The latest answer reserves enough height to align a short initial chunk. The same path handles errors, and scrolling waits if another page is active. No server-side changes are required for this UI change.

Production build and whitespace checks pass. An isolated fictional-data browser test used a fake delayed response, without any model or Garmin call. The new answer was approximately 22 px below the chat viewport's top while streaming; its offset and scroll position were unchanged after it grew to 5,943 characters and completed. Navigation contained Dashboard/Activities/Health/Training/Nutrition/Maintenance/Profile/Data & sync/Settings, with no Chat tab. [Overview layout](overview-chat-layout.png) and [answer-start evidence](overview-chat.png). The isolated preview was stopped afterward; the normal app was preserved.

## Training edits and cross-week follow-through — 24 October

Outstanding quality categories now include explicitly skipped sessions and completed sessions whose recorded benefit differed from intent. A deduplicated 42-day ledger survives calendar-week boundaries, shows the next planned date, and clears when a later finished recording supplies that benefit, including unplanned rides. Unknown labels remain unknown. The adapter considers existing quality slots over the rolling seven-day materialized horizon; it never adds a session, increases total duration/work time, edits a published/manual/fixed/held session, or bypasses recovery, protected phases, advanced eligibility and spacing. Only one slot can be reassigned per review. Repeated review leaves an already scheduled category in place.

Variant choice now uses recent, completed cycling recordings with matching category benefit and explicit tolerable effort/soreness feedback. Calendar weeks or unrelated strength/easy-session feedback no longer unlock a different structure. The chosen variant includes its evidence and reason; automatic replacements retain the existing work-time ceiling, falling back to a smaller default structure when necessary.

Chat prepares reviewable, fingerprinted block edits. For example, **“Change today cycling to 2 x 4 minutes, recovery to 3 minutes”** preserves warm-up/cool-down and total duration, redistributing the steady portion. Current-method work targets accept explicit W, bpm or RPE ranges; sensor/calibration changes require plan review. Small demand increases require two recent tolerated recordings in that category and normal recovery, with app editing limits of 20% work time and 5% target increase; these are conservative product bounds, not physiological guarantees. Recovery cannot be compressed beyond proportional reductions in work duration. Larger changes ask for a replacement-week review. Named strength exercises accept sets/reps/load reductions and longer rest, preserving other exercises; unknown/new or increased lifting loads require recorded-performance review. Unsupported, ambiguous and negated requests produce no saveable partial change.

Saving recomputes the proposal against current recovery, active-program and workout revisions. Daily review, target reconciliation and volume/event reconciliation preserve manually edited instructions; conflicts remain reviewable. Published edits become pending Garmin updates. Fake-client verification covers updating the same cycling/strength workout, reps/load/rest read-back, and opt-in rolling publication applying an edit once without duplicate workouts/calendar entries. No live Garmin/device execution is claimed.

Mixed food/chart plus workout-edit requests now clarify the two tasks before either deterministic handler runs, avoiding a silently dropped task or unintended meal logging. They remain sequential requests within one chat; full semantic multi-task orchestration and live-provider QC are still open.

**11 new regression tests pass.** The focused training/roadmap/publication/active-program selection has **77 passing tests**. The broader **217-test selection has 205 passes, 11 failures and 1 error**, exactly the previously recorded unsuccessful IDs, with no new failing case. Frontend production build and whitespace checks pass. See [follow-up validation](followthrough-validation.json). Browser testing submitted a real deterministic edit to an isolated fictional database and verified the exact review card and successful Save: [review](block-edit-review.png), [saved result](block-edit-saved.png). The preview server was stopped. Personal records, live Garmin, normal app processes, commits and pushes were untouched. Quit/reopen the normal app to load the changed backend.
