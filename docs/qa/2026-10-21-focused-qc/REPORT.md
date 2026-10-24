# Focused pre-trial QC — 21 October 2026

**24 October implementation update:** [Readiness v5, forecast and Health recovery dial](../2026-10-24-readiness/REPORT.md) now address the readiness-specific observations below, including RHR dominance, short forecast history, recovery countdown and sleep adjustments. Compact cards expose explanations via top-right **!** popups. The exact two-ride advice forced-routing case is corrected. Earlier “not implemented” statements are historical; the linked report gives the current per-item status and explicitly retains the broader trainer/Garmin backlog.

The user agreed to focused QC first, then a week of normal use, followed by detailed all-tab QC. Proposed observation period: 21–27 October, with detailed review from 28 October (Asia/Jerusalem). No background monitoring or reminder was created.

146 tests passed together across sync/recovery, sleep/history, readiness/forecast, casual training adjustments, active plans, trainer-section scenarios, Garmin publication and performance contracts. The 50-request chat/save bank was rerun successfully: 26 reviewable changes, 13 reasoned declines and 11 focused clarifications, using disposable databases. Three sport/goal programs activate and roll their next-seven-day schedules in the trainer-section tests. Garmin publication uses fake providers; the previously user-confirmed live cycling publication remains the real-world evidence. No new Garmin write was made.

Two test-harness corrections were necessary: SQLite snapshots must use backup rather than copying a main file while committed WAL data remains; older active-training tests now explicitly select plan mode and reflect the existing contextual recovery policy (readiness score alone does not force rest). Long-session move tests use a controlled long workout rather than assuming a no-history fixture generates one. Production training rules were not loosened to make tests pass.

Browser checks: active program visible; seven dates 21–27 October; independent today's suggestion returned a 60-minute endurance workout with targets and no saved schedule changes; previous Garmin publication shown as verified.

## Open finding before full trial sign-off

Update — 22 October: the allocation finding below was [corrected and verified](../2026-10-22-friday-allocation/REPORT.md) without replacing published sessions. Friday's planned dose is 84 minutes; current recovery evidence temporarily caps it at 60 and is explained on the card. The original finding is retained here as historical evidence. Normal-use and detailed all-tab QC remain outstanding.

The user's saved Friday 23 October remains 54 minutes, shorter than the 60-minute weekday rides. This is a persisted schedule finding, not covered by declaring the current generator's synthetic fixtures green. A replacement-week preview is currently blocked by an already published session (`Published sessions cannot be replaced locally`). The published workout and personal schedule were preserved. Resolve the local Friday allocation with publication-aware review before claiming the long-ride preference is satisfied. The user then steered work to the nutrition chat; this finding remains open.

This is focused QC, not all-tab business QC or daily-use packaging sign-off. Launch/quit lifecycle and closed-app background behavior remain as documented in the main plan.

## User observation for detailed QC — 22 October 2026

- **Open: training readiness appears too dependent on resting heart rate (RHR) and sleep.** User feedback from normal use; the imbalance has not yet been validated or corrected.
- Review actual score contributions and downstream workout adjustments across representative days, including elevated RHR or poor sleep alongside otherwise favorable recovery evidence. Check whether recent training load, HRV, trends and available subjective recovery context receive appropriate consideration.
- Code reference: `backend/app/readiness.py` currently defaults to 40% autonomic, 35% sleep and 25% workload. The autonomic component is not synonymous with RHR; inspect its actual inputs and any saved parameter overrides before drawing conclusions about effective weighting.
- Record findings and proposed calibration during detailed QC. No algorithm or weight changes were made for this note.

## User observation: trainer advice routed to a workout suggestion — 22 October 2026

**Open:** The trainer responded mechanically to a conversational advice question by starting today's workout suggestion instead of discussing the proposed two-session sequence. User-reported reproduction; not yet independently reproduced or fixed.

User question:

> I want to do today in the evening 30-45 minutes ride on my indoor trainer and tomorrow morning I will do a 2 hours ride does it make sense?

Reported response:

> Steady endurance  Easy session based on your saved preferences and recent training.  Warm-up: 9 min. 78.75–112.5 W  Steady endurance: 31 min. 123.75–157.5 W  Cool-down: 5 min. 78.75–112.5 W  Recommendation only; your saved plan is unchanged

Expected behavior: answer the question conversationally as a trainer, considering both tonight's 30–45-minute indoor ride and tomorrow morning's two-hour ride, the short recovery interval, intended intensity and available training/recovery context. Explain the reasoning and any suggested adjustment; ask a focused follow-up only if needed. A structured workout can accompany advice when useful or requested, but must not replace the answer.

Detailed QC should trace why this advice request selected the today-suggestion flow and check both intent routing and response presentation. Retain this exact prompt as a regression scenario: the response must address whether the two rides make sense together, rather than returning only a generic workout card. No trainer behavior or saved plan was changed for this note.

## User requirement: send strength workouts to Garmin — 22 October 2026

**Open feature requirement:** Add compatibility for sending planned strength workouts to Garmin, alongside the existing workout publishing flow.

Implementation and QC should verify supported Garmin strength-workout structure and exercise mappings, including sets, repetitions, weight and rest intervals where supported. Make unsupported exercises or fields clear before publishing, and verify that the published workout retains its intended structure in Garmin. Include strength-specific coverage for publication status, retries and duplicate prevention. Device compatibility and any Garmin limitations still need investigation; this note does not establish current support or successful publication.

Recorded as a requirement only; no implementation or Garmin publication was performed.

## User observation: trainer cannot edit workout blocks or retain the steady-endurance rule — 22 October 2026

**Open:** The trainer cannot apply a requested workout-structure change. It initially misclassified a cycling endurance request as strength, then understood the requested change conversationally but repeatedly invoked an adjustment control that only offered duration, intensity or rest changes. After asking for confirmation and receiving it, the trainer still could not save the change.

Reported conversation and reproduction:

1. User: “In my steadty edurance I dont need warm up and cool down it is very easy as is”. The adjustment tool replied with strength-specific instructions about exercise load, sets and repetitions.
2. User clarified: “in general for cycling edurance steady”. The assistant acknowledged easy steady endurance should be one continuous ride without separate timed warm-up/cool-down blocks.
3. User extended the request: “also for the pkanning ahead”. The assistant offered to apply it to all upcoming easy endurance rides while keeping total duration unchanged, but the adjustment tool asked whether the user wanted a harder, less intense, shorter or rest session.
4. User confirmed: “yes apply it”. The assistant reported that removing workout blocks was unsupported; another adjustment call returned the same generic clarification. Saved workouts remained unchanged.

**Explicit user rule:** For this user's easy steady endurance cycling workouts, use one continuous endurance block without separate warm-up or cool-down blocks. Apply the preference to upcoming matching workouts and future planning/generation, preserving total duration. This is a user-specific workout-format requirement, not a universal physiological claim. Harder interval workouts are outside the requested change.

Implementation and detailed QC should cover:

- Correct cycling intent routing despite spelling errors and conversational follow-ups; do not route this request to strength adjustments.
- Support changes to workout blocks, including merging warm-up/cool-down time into the continuous endurance block while preserving total duration and an appropriate endurance target.
- Persist the preference so future generated easy steady endurance rides follow it, rather than changing only the current workout.
- Carry the agreed scope and confirmation through “also for the planning ahead” and “yes apply it”, without repeatedly asking unrelated adjustment questions.
- Verify saved workout definitions, displayed blocks and Garmin payloads agree. Route already-published workout changes through the existing Garmin update workflow and report whether remote updates remain pending.

Retain this conversation as a regression scenario. This entry records the requested behavior and user authorization; no workout, generation rule or Garmin publication was changed while recording it.

## User requirement: automatic rolling Garmin publication and one override confirmation — 22 October 2026

**Open feature/workflow requirement:** After the user initially sends the next seven days to Garmin, automatically keep that rolling seven-day window up to date on every app sync. Routine subsequent syncs should not require another manual send or per-workout approval.

For an explicit override of previously published workouts, replace the repetitive activity-by-activity review with one “Are you sure?” confirmation. That confirmation should concisely explain the actual consequences for the affected Garmin workouts and calendar entries, then apply the whole requested override after confirmation. Do not follow it with separate approvals for every activity.

Implementation and QC should verify:

- Initial seven-day publication enables the recurring behavior; each subsequent sync reconciles the current upcoming seven-day window, including newly entering days and changed app-managed workouts.
- Unchanged workouts are not duplicated or unnecessarily rewritten. Repeated syncs and retries remain safe, and partial failures are reported accurately.
- One override confirmation covers the requested batch and explains what will be updated, replaced or removed, based on the actual operation. Preserve unrelated Garmin activities and workouts.
- Keep routine automatic reconciliation separate from an explicitly requested override, so a normal sync does not unexpectedly trigger a destructive replacement.
- Publication status makes success, pending changes, unsupported workouts and failures visible without requiring individual review of every successfully handled workout.

Recorded as requested behavior only. Automatic Garmin publishing and the simplified override flow have not been implemented or enabled by this note; no Garmin changes were made.

## User requirement: completion indicators and planning from actual training benefit — 22 October 2026

**Open feature/workflow requirement:** When a completed activity is synced for the same local calendar day and activity type as a planned session, reconcile it with that session and visibly mark the session/day as done (for example, a checkmark). When multiple same-sport sessions exist on a day, use available timing and workout evidence to identify the match rather than marking every session done. Repeated syncs must not duplicate completion or count the same activity against several sessions.

The upcoming seven-day plan should account for the actual training benefit achieved, rather than assuming that completing a planned workout delivered its intended stimulus. User example: if a planned sprint session primarily delivered a base/endurance benefit, consider scheduling another sprint session **later in the same week**. The user explicitly corrected “during the next week” to “later in the week”. “Spring” is interpreted as “sprint” from context.

User clarification: this rule applies to **any intended training stimulus**, including anaerobic, threshold, sprint and other training benefits. Sprint is only an example. Compare intended versus achieved benefit for every session and consider addressing a missed stimulus later in the same week when appropriate.

Implementation and QC should verify:

- Completion indicators update from synced activity evidence with correct local dates and normalized sport types, including indoor cycling. Completed sessions remain visibly completed after refresh and subsequent syncs.
- Keep completion and achieved stimulus distinct: a matched ride can be done even if its benefit differs from the intended sprint stimulus.
- Compare intended stimulus with available recorded training-effect/primary-benefit evidence and actual session details. Make missing or ambiguous benefit evidence explicit rather than inventing a classification.
- Reassess remaining sessions in the rolling seven-day plan, considering an opportunity to address the missed training stimulus later in the same week. Account for the load already performed, recovery, spacing between hard sessions, availability and fixed commitments; do not automatically add another hard session solely because a benefit label differs.
- Explain any proposed or applied schedule change in terms of intended versus achieved benefit. If no suitable slot remains in the week, state that rather than forcing an extra session.
- Integrate resulting changes with the requested automatic Garmin sync/update workflow while preserving completed activity records.

Recorded as requirements only; completion matching, adaptive scheduling and Garmin behavior were not changed by this note.

## User requirement: trainer suggestions cover cycling training benefits — 22 October 2026

**Open requirement:** Ensure the trainer can suggest distinct **sprint, anaerobic, threshold and base rides**, both when explicitly requested in chat and when appropriate in plan generation or adaptation.

QC should verify each category produces a suitable workout structure, effort targets, work/recovery durations and an explanation of its intended benefit, rather than returning the same generic endurance suggestion under different names. Suggestions should account for the user's fitness, recent load, recovery and available time, and explain when a requested stimulus is unsuitable. Keep intended benefit distinct from the benefit actually achieved after the ride.

Recorded as a requirement only; suggestion behavior was not changed or verified by this note.

## User requirement: multiple researched workout variants per category — 22 October 2026

**Open requirement:** Each cycling category (sprint, anaerobic, threshold and base) must offer multiple meaningful workout variants with different effort intensities, work-block durations, repetitions, recovery durations and total session durations. A single fixed template per category is insufficient. Variations must retain the intended stimulus rather than arbitrarily increasing every parameter together.

**User clarification: fitness and plan goals govern selection.** All categories, variants and subsequent adaptations must contribute to improving the user's fitness and progressing toward the active plan's goal. Choose the stimulus, dose and progression based on the goal, current training phase, demonstrated ability, completed training and recovery. Explain how the selected workout supports that progression. Variety is a means to effective training, not an objective by itself; do not force every category into each week or continually increase intensity/duration when recovery, consolidation or tapering better serves the goal. QC should verify that individual suggestions and the combined weekly schedule form a coherent progression toward the saved goal.

**Further user clarification: goal specificity must not completely neglect an aspect of fitness.** Maintain coverage of base endurance, threshold, anaerobic capacity and sprint ability across the training cycle, with emphasis and maintenance doses appropriate to the goal and phase. This does not require equal emphasis or every category every week. Track intended and achieved stimulus over time so repeated adaptations do not silently eliminate a category; temporary omissions for recovery or tapering should be explained and reconsidered as training resumes. QC should assess both goal progression and balanced coverage over multiple weeks, rather than judging isolated workouts alone.

**User clarification on frequency:** A training aspect may recur once a week, once every two weeks or once every three weeks, according to the appropriate training plan, goal, phase and recovery needs. Select and explain a suitable cadence per aspect rather than enforcing a universal weekly quota. Track coverage beyond the visible seven-day window so longer recurrence intervals are deliberately planned and do not become indefinite omissions. QC should verify that rolling-week updates preserve those multiweek intentions while accounting for the stimulus actually achieved.

**User clarification on adaptation and follow-through:** Those recurrence intervals are examples, not fixed schedules; frequency can change as the plan adapts. The requirement is that every aspect actually receives training over time. Track the last achieved stimulus and the next intended opportunity for each aspect; when a session is missed, delivers a different benefit or is deferred, reassess and retain a suitable future opportunity rather than silently dropping it. QC must verify follow-through across successive plan updates and completed activities, not merely the presence of a category in a generated plan. Recovery or other constraints may justify deferral, but the trainer must explain and revisit it.

Online references reviewed on 22 October 2026:

| Category | Reference examples and implications for the workout library |
| --- | --- |
| Sprint | [TrainerRoad sprint examples](https://www.trainerroad.com/blog/how-to-improve-your-maximum-sprint-power/) include short 10–12-second technique/torque efforts and 20-second repetitions with substantial recovery, as well as mixed sprint/sustained-effort formats. Distinguish pure sprint quality from mixed workouts; individualize targets using available sprint-power evidence rather than assuming one FTP multiplier suits everyone. |
| Anaerobic | [TrainerRoad anaerobic examples](https://www.trainerroad.com/blog/anaerobic-intervals-for-cyclists-how-they-make-you-faster/) include 30-second efforts at 130% FTP and 15-second microbursts at 140% FTP. These illustrate different interval durations and intensities; recovery density and set count also matter. |
| Threshold | [TrainerRoad threshold examples](https://www.trainerroad.com/blog/threshold-intervals-for-cyclists-benefits-examples-and-tips-for-success/) distinguish sustained work, hard starts, over-unders and mixed intervals. Build variants with different sustained-block lengths and recoveries; do not treat sweet spot or VO2max as interchangeable threshold labels. |
| Base | [TrainerRoad power-zone guidance](https://support.trainerroad.com/hc/trainerroad-support/articles/115005942786-understanding-power-zones) places endurance at 55–75% FTP and describes progression through longer riding. Proposed app variants can vary continuous endurance duration and target within the endurance range; retain this user's single-block preference without separate warm-up/cool-down blocks. |

These sources inform a proposed library; their examples are not personalized prescriptions or guarantees of a particular Garmin training-effect label. Final templates need appropriate progression and calibration to the rider.

QC acceptance: request alternatives in every category and verify genuinely different block structures/targets and suitable total durations, with complete recovery instructions and rationale. Check easier and harder options without changing the requested training purpose, and ensure chat, planning, workout display and Garmin export retain the chosen variant. Selection must use fitness, recent training, recovery, available time and indoor/outdoor constraints. Keep source provenance with the implemented templates.

Recorded and researched only; no workout library or trainer implementation was changed.

## User observation: tomorrow's readiness forecast stays anchored to a poor recent week — 23 October 2026

**Open:** After approximately six days of poor resting heart rate and sleep, the user reports that tomorrow's readiness forecast continues to assume similarly poor measurements, producing a forecast below today's improved actual readiness. Review whether the forecast overweights a short adverse period and responds inadequately to current improvement. The reported personal comparison has not yet been independently reproduced.

Code inspection of `backend/app/readiness_forecast.py` confirms short-window input projections: up to seven observations within fourteen calendar days, with a three-observation mean for projected nightly HRV and medians for sleep and RHR. Today's provisional RHR is excluded from forecast training inputs. The implementation also uses personal readiness baselines and evaluates a regression correction against historical examples over a 100-day lookback, so the whole forecast is not based exclusively on seven days.

Investigate longer personal reference windows for HRV and heart-rate measures (particularly RHR), alongside sleep, and compare approaches that combine a longer baseline with recent trends and the latest reliable measurements. A longer window is an option to evaluate, not an agreed algorithm change; it can also slow response to real changes. Keep confirmed measurements, provisional readings and projected values distinguishable.

QC should include a sustained adverse spell followed by improved measurements, stable periods, and genuine deterioration. Compare short-window, longer-window and blended forecasts using past-only evaluation, forecast error and uncertainty coverage. Explain which assumptions make tomorrow differ from today. A lower tomorrow forecast is not inherently wrong and must not be artificially floored at today's score; the issue is whether its assumptions and calibration reasonably reflect the available evidence.

Recorded as an investigation item only; no forecast parameters or behavior were changed.

## User observation: post-ride follow-up loses context and substitutes lap statistics for a climb — 23 October 2026

**Open:** During a trainer conversation about today's completed ride, the user reports that the trainer lost context and did not resolve a follow-up asking for the duration and average power of an uphill section. Preserve this conversation as a regression scenario; context loss is user-reported, and the underlying retrieval/analysis failure still needs tracing.

Reported context: the trainer assessed the 23 October “Base” ride (30.2 km, 320 m climbing, Garmin primary benefit Tempo, aerobic TE 3.8, anaerobic TE 1.1, average power 155 W and normalized power 180 W). The activity was subsequently listed as mountain biking.

User follow-up:

> there is a chunk of up hill what was the avg power there and how long was it?

Reported answer identified the 15–20 km lap as the main climbing section and returned average power 182 W over 1,248 seconds (20 minutes 48 seconds), ascent 169 m and normalized power 205 W. It explicitly acknowledged that the lap included 45 m descent and that exact climb boundaries had not been isolated. This caveat was appropriate, but the climb-specific question remained unanswered.

Visible tool evidence: an initial `list activities` query for 23 October returned zero matches, a subsequent query returned one mountain-biking activity, and `get activity stream` was invoked. Investigate activity identity/context retention, sport filtering and stream analysis rather than assuming the initial empty result proves the activity was absent.

Expected behavior and QC:

- Retain the referenced activity ID across ride-assessment follow-ups, including colloquial references such as “there” and “the uphill”; do not unnecessarily rediscover the ride with a narrower or incompatible sport filter.
- Use the available elevation/distance/time/power stream to identify the prominent sustained climb and calculate duration and time-weighted average power over the same boundaries. Handle pauses, missing power samples and elevation noise explicitly; distinguish moving time from elapsed time where relevant.
- Give a concise answer in minutes/seconds and watts, with the climb's approximate location/boundaries and any material uncertainty. If several climbs are plausible, identify the candidates or ask a focused question while retaining the ride context.
- Lap statistics may support a clearly labeled approximation when stream data is unavailable, but must not substitute for climb-only statistics when the stream can resolve them. Do not claim precise climb results without analysis.
- Verify the exact follow-up after an assessment of a mountain-bike ride, including the empty-query recovery path and consistent activity identity across all tool calls.

Recorded as a QC finding only; no trainer or activity-analysis behavior was changed.

**User clarification: general section-level activity analysis.** This capability must cover different sections requested conversationally, not only uphill detection. Resolve explicit time ranges (for example, minutes 10–20), distance ranges (kilometers 15–20), laps, intervals/repetitions, climbs, descents, flat stretches, sprints/short accelerations and descriptions such as “the last hard effort” against the referenced activity. Explicit user examples include flats and sprints. Identify these from available terrain and effort evidence rather than requiring a matching lap label. Support follow-up comparisons between sections while retaining the activity and selected section context.

For each request, identify defensible boundaries from available streams/lap data and compute the requested metrics over those boundaries, such as duration, average power, heart rate, cadence, speed or elevation change. Keep units and elapsed-versus-moving-time semantics clear, use appropriate weighting and disclose missing data or approximate segmentation. Ask a focused clarification when the requested section cannot be uniquely identified; do not silently substitute an entire lap or activity. QC should cover explicit ranges, terrain-based sections, repeated efforts, comparisons, ambiguous references and unavailable streams, with numerical checks against the selected samples. Recorded as a requirement; not implemented or verified by this note.

## User addition: use Garmin load-focus ranges and cycling ability in seven-day planning — 23 October 2026

**Open requirement, extending the earlier planning notes:** When suggesting or adapting the next seven days, consider Garmin's anaerobic, high-aerobic and low-aerobic load totals and their personalized target ranges, together with available cycling-ability data. Use these to inform workout emphasis and dose alongside the active goal, training phase, actual achieved benefits, multiweek coverage, recent load and recovery.

Terminology verified against Garmin documentation: [Training Load Focus](https://support.garmin.com/en-SG/?faq=SEkNpdGyhR917js0qQL3Q6) provides the three load categories and their optimal ranges. [Cycling Ability](https://support.garmin.com/en-CA/?faq=cavgBOyn1j7t8Y1L56RvA6) is a related but separate assessment of aerobic endurance, aerobic capacity and anaerobic capacity, using power records, VO2max and load distributions. Preserve this distinction rather than treating load totals as ability scores.

Implementation and QC should:

- Investigate which actual Garmin fields the connection exposes for category totals, lower/upper target bounds, ability scores and timestamps. Preserve source, units, reporting window and freshness. Do not invent unavailable ranges or assume a multisport load-focus total is cycling-only.
- Consider below-range, within-range and above-range categories when choosing remaining sessions; explain material decisions in plain language. Avoid forcing extra intensity merely to fill a Garmin shortage or treating an above-range category as an unconditional ban.
- Combine these signals with the user's flexible multiweek coverage requirement, rather than requiring every category to reach its range within each visible seven-day window.
- Reassess after synced completed activities, incorporating the benefit actually recorded. Do not equate a proposed workout name with a guaranteed contribution to a Garmin load category or double-count completed training.
- Handle absent, stale or insufficient Garmin data explicitly and continue planning from available evidence. Verify that changing category ranges/ability evidence can appropriately change recommendations while recovery constraints and plan goals remain respected.

Recorded as a requirement with documentation research; Garmin data availability and integration have not been verified or implemented by this note.

## User requirement: trainer can answer questions about all app data — 23 October 2026

**Open:** Audit and provide trainer query access to every user-facing dataset available in the app, including Garmin-derived data, extended imported history and locally entered records. The user must be able to ask questions about any of it, not only the fields currently bundled into a trainer summary. Include activities/sections, health and recovery, load/ability/ranges, plans/goals/preferences/feedback, nutrition, equipment and other datasets identified by the audit.

Use bounded read tools with dates, units, provenance and freshness; do not expose secrets or inject the whole database into prompts. Record a dataset-to-tool coverage matrix and test representative questions for each dataset, including cross-domain follow-ups. Distinguish missing data from unavailable tool support and do not claim complete coverage before auditing it. Apply the same access and context behavior to browser and the planned Telegram channel.

See the detailed [Telegram nutrition/trainer integration plan](../../planning/telegram-coach-integration-plan.md) for the data-access foundation, block diagram, phone text/photo/voice workflows and local-to-server architecture. Planning only; data access has not been expanded by this note.

## Recovery-time availability investigation — 24 October 2026

User requested checking recent Garmin recovery time as a possible readiness input. Read-only database inspection found `firstbeatData.results.recoveryTimeMins` in eight historical activities, most recently 24 December 2025; this is historical activity evidence, not a current remaining-recovery estimate. Preserved originals for the 22 and 23 October 2026 rides decoded successfully but contained no recovery-named fields. Authenticated live activity-detail reads likewise returned no recovery fields for those two rides. Garmin training-readiness queries for 23 and 24 October returned empty lists; the 24 October training-status response contained no recovery fields. Thus these checked sources do not currently supply recent recovery time for this account. This is not proof that no Garmin device or other endpoint can provide it.

The installed client exposes recovery-time fields on training-readiness responses, but support in a client schema does not establish account data availability. If added to app readiness later, verify source, units, observation time and current availability, and evaluate overlap with existing workload/HRV/sleep inputs. Do not substitute old activity recovery values or treat missing recovery time as zero. No readiness formula changes or Garmin writes were made.

Follow-up: [last-five-ride investigation and normalization](../2026-10-24-recovery-time.md) found no recovery-time evidence in their originals/live details or date-specific readiness responses. Supplementary endpoint collection already existed; normalization into a dedicated metric has now been added and tested for future available readings. This corrects the earlier implication that the endpoint itself was not collected. Readiness scoring remains unchanged.

### Requested readiness redesign — 24 October 2026

User wants last-night sleep and remaining recovery demand to carry high emphasis; HRV status, recent sleep history and stress history medium emphasis; longer training-load context lower emphasis. Treat this as the requested app model direction, not verified Garmin percentage weights. [Garmin's manual](https://www8.garmin.com/manuals/webhelp/GUID-0221611A-992D-495E-8DED-1DD448F7A066/EN-GB/GUID-C21BE0C8-A08E-4DA1-B6C6-2E0E2DDDB372.html) confirms six factors (sleep score, recovery time, HRV status, acute load, three-night sleep history and three-day stress history), without specifying this weighting scheme. A 14-day HRV reference is a user proposal to evaluate against existing longer personal references, not a confirmed Garmin baseline definition.

Local data checked: sleep duration/score, nightly HRV, RHR and average-stress readings exist through 24 October; recent supplementary payloads include stress endpoints. Activity exercise-load scores are available. Availability does not establish complete valid windows: verify awake stress coverage, sleep debt/history and sufficient HRV/load reference history before scoring.

Current v4 uses HRV/RHR, sleep and decaying workout load only; it does not yet implement the requested separate stress-history/recovery model. Recovery-time import support has no current Garmin values for this account. An app-derived recovery-demand estimate is possible, but the supplied fixed peak-EPOC-to-hours table is unvalidated for this rider and imported exercise-load units are not verified as raw peak EPOC in mL/kg. Do not apply its thresholds directly or present estimated hours as Garmin measurements. Evaluate a calibrated load/time/personal-history estimate with uncertainty, avoiding duplicate penalties for the same load, sleep or stress evidence. Recovery denotes preparation for another hard session, not a blanket prohibition on easy activity. No new scoring weights or recovery-hour formula were implemented for this note.

### Proposed load-based recovery estimate with individual-session protection — 24 October 2026

User proposes a four-week history and time-to-load-ratio threshold, plus separate handling of a hard workout after a long rest. The supplied screenshot is explanatory reference, not a validated calculation. Clarify that 1.5 refers to acute/chronic load ratio (ATL/CTL), not CTL itself. Twenty-eight days is a suitable starting reference aligned with [Garmin's chronic-load definition](https://support.garmin.com/en-SG/?faq=SEkNpdGyhR917js0qQL3Q6); use additional preceding history where needed to initialize an app model and test sensitivity to other reference windows rather than changing the baseline arbitrarily.

Evaluate two overlapping signals:

1. **Accumulated-load trajectory:** project acute and chronic load under an explicitly labeled no-further-training scenario and estimate when their ratio returns to or below 1.5. Use recorded Garmin values when available as observations; any future trajectory is an app model with defined/calibrated decay, not Garmin's unpublished algorithm. Evolve both acute and chronic load rather than holding CTL constant. A ratio already below 1.5 means no ratio-based delay, not full physiological recovery. Low/zero chronic load, incomplete history and prolonged inactivity require an insufficient-baseline state rather than arbitrary division floors and precise hours.
2. **Individual-session demand:** retain a recovery-demand estimate for recent hard/long/unusual sessions even when the accumulated ratio is low. The user's earlier recovery table can inform provisional range hypotheses only after resolving its input-unit/calibration limitations. Account for elapsed time and subsequent training; do not sum all session recovery ranges or assume a long rest erases a new hard session's recovery demand.

A candidate combination is the later of the two estimated recovery windows, followed by the separate readiness context, rather than adding overlapping recovery hours. This is a proposed heuristic to validate, not a physiological identity. Replace/rework the existing load penalty when integrating it so workload is not counted again as an independent full penalty. Keep sleep and stress effects explicit to avoid counting them in both an adjusted timer and separate score terms without calibration.

QC scenarios: low ratio after a single hard session; accumulated high load; no training and steady decline; multiple sessions close together; long inactivity and a tiny chronic baseline; missing days; an upcoming planned workout; ratio below 1.5 despite poor sleep/HRV. Show estimated ranges and assumptions, distinguish time to ratio threshold from recovery for another hard session, and calibrate against available historical recovery observations and user outcomes. The screenshot's injury-risk/sweet-spot claims must not become universal safety thresholds: [research identifies important limitations of ACWR for individual injury predictions](https://pubmed.ncbi.nlm.nih.gov/32502973/).

Recorded as the requested design direction and evaluation plan. No estimator or readiness score changes were implemented by this note.

**Accepted tuning choice — 24 October 2026:** The user accepted **1.3** as the provisional soft acute/chronic load threshold, with a **28-day chronic baseline**. This supersedes the earlier proposed 1.5 threshold for the app estimator. Label the projected interval “estimated time until load settles”, not “hours until fully recovered”. Retain the separate recent hard-session demand estimate even below 1.3, including after long rest. Validate/calibrate this heuristic against actual recovery experience before giving it substantial readiness weight. Acceptance records the design choice; the estimator and scoring changes remain unimplemented.

**Required elapsed-time countdown — 24 October 2026:** The activity-based recovery estimate must decrease with actual time elapsed since the activity ended: `remaining_hours = max(0, assigned_recovery_hours - elapsed_hours_since_activity_end)`. For example, a 48-hour assignment has 24 hours remaining after 24 hours and zero after 48 hours, absent a separately explained reassessment. Store the activity end timestamp and assigned duration (or equivalent recovery-until timestamp), and derive remaining time from the current clock; do not restart the timer on sync, refresh, midnight or app restart. Use timezone-aware instants so offline periods and daylight-saving changes count correctly. Recompute readiness from the current remaining estimate rather than reusing the original assigned duration. New activities or other explicit model reassessments can change the estimate, but must retain timestamps and explain the adjustment; do not simply add overlapping timers. Keep the load-ratio trajectory separate from this activity-based countdown and do not subtract elapsed time twice. QC must verify the 48→24→0 example, the zero floor, restart/offline behavior, repeated sync and subsequent activity handling. Requirement recorded; implementation remains pending.

### Sleep adjustment to estimated recovery — research and proposed method, 24 October 2026

User requested a method for good sleep to shorten and poor sleep to lengthen estimated recovery. [Garmin confirms this direction](https://www.garmin.com/en-US/garmin-technology/running-science/physiological-measurements/recovery-time/) but does not publish a sleep-score-to-hours formula on that page. The [2021 athlete-sleep consensus](https://bjsm.bmj.com/content/55/7/356) emphasizes individual needs, sleep history, measurement limitations and mixed evidence for acute sleep changes; a [systematic review of sleep extension](https://pubmed.ncbi.nlm.nih.gov/33352457/) reports potentially beneficial performance effects with limited/variable evidence. None of these sources supplies a validated universal conversion from sleep score or extra sleep minutes to recovery hours. Do not present a prototype conversion as an established physiological effect.

**Proposed implementation to evaluate, not an accepted/calibrated coefficient:**

- Continue normal wall-clock countdown first. At the end of a completed, sufficiently reliable post-activity sleep episode, evaluate duration against a configured personal sleep need, sleep quality and recent three-night shortfall. A historically short sleeper's low median alone must not define adequate sleep. Do not promise unlimited benefit for longer sleep, or give a strong bonus for one excellent night while recent debt remains unresolved. Avoid relying on noisy REM/deep-stage percentages as precise recovery multipliers.
- Produce one bounded sleep-quality adjustment `q` in `[-1,1]`: positive for clearly restorative sleep, negative for clearly inadequate sleep and zero for neutral/insufficient evidence. Define and validate the input-to-q mapping before rollout; no score cutoffs are agreed by this note.
- For a small experimental first version, evaluate `delta_hours = -q * min(2, 0.10 * remaining_at_wake)`. The 10% and two-hour cap are engineering trial parameters, not research-derived values or approved final settings. With 24 hours remaining, the extreme illustrative cases become 22 after excellent sleep and 26 after very poor sleep. A neutral/missing night leaves 24. Evaluate alternatives and sensitivity before adoption; avoid decimal precision in presentation.
- Apply this correction to the activity-demand estimate only, not to Garmin's observed load history or the ratio-threshold projection. Then use the later of the load-settling and activity-demand estimates. Good sleep must not make an accumulated-load warning disappear by altering its data. The timer estimates preparation for hard training, not all aspects of readiness.
- Apply each sleep episode once, anchored to its actual end time and only to relevant pre-existing activity demand. Store episode ID, input revision, pre-adjustment remaining time, model version and correction. Repeated sync/refresh must not compound percentages. Recompute from a stable activity/sleep event timeline when sleep data is corrected or arrives late; do not apply last night's correction to a workout performed after waking. Exclude future sleep evidence from historical calculations.
- After the correction, the countdown resumes at one hour per elapsed hour. For example, a correction from 24 to 22 at waking becomes 18 four hours later. An exhausted timer stays zero; poor sleep may still lower overall readiness but must not resurrect old workout debt. Missing sleep does not mean poor sleep.
- Keep Garmin-provided recovery snapshots separate: they may already incorporate sleep/stress, so never apply this extra correction to them. Prevent full duplicate sleep penalties in both the estimated timer and overall readiness; compare an explicitly sleep-aware timer model against a baseline with sleep only in readiness, and document contribution/interactions when combining them.

Validation should compare countdown-only and sleep-adjusted models using past-only input availability, perceived recovery, session RPE and ability to complete the next hard workout; historical Garmin recovery values can provide secondary comparisons, not physiological ground truth. Check excellent/poor/neutral/missing sleep, recent debt, repeated sync, corrected records, late arrival, a workout after waking, overlapping sessions, zero remaining time, offline periods and daylight-saving transitions. Select final parameters based on calibration and user experience rather than implying the research supports a specific number of hours. Implementation and coefficient approval remain pending.


### Later frontend QC — Trainer versus Assistant clarity (24 October 2026)
The user confused Trainer and Assistant despite building the app. Open finding: review whether the two experiences should be separated and how to make their roles obvious. **Remind the user at the next frontend touchups.** Detailed discussion and acceptance examples are in the frontend-touchups checkpoint of [the application plan](../../planning/health-training-app-plan.md). Working direction: separate coaching/planning and data/activity analysis contexts while sharing app data; review navigation, wording, examples and Telegram routing before implementation.
