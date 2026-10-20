# Training app QC — 18 October 2026

## Resolved by refresh: temporary trainer loading state

User requested inspection of the currently open Training tab and a QC note. Read the existing page without refreshing, submitting, changing settings or modifying a plan.

Observed in the in-app browser at `http://127.0.0.1:5173/#training`:

- The trainer composer contains the user's detailed sixteen-week FTP/endurance and strength request, including cycling/strength days, weekday60–90minute limits, Friday up to5hours and equipment.
- **Send is disabled**, so the entered request cannot be submitted from this state.
- Header reports **Checking local backend…**. The trainer reports **Qwen / Ollama — Setup needed**.
- The active-plan section displays its no-plan message, and plan history says no saved plans. These may be unloaded/default states; inspection does not establish that stored plans were lost.
- No warning/error entries were returned by the browser console inspection. This does not establish successful backend connectivity.

User subsequently confirmed that refreshing the page solved the issue and that it was not serious. No investigation or repair is requested. The observations above describe the temporary pre-refresh state only; they do not establish a persistent backend, provider, questionnaire or deletion defect.

Status: resolved by refresh, per user confirmation; no open QC issue. QC recording only. No repair, tests, builds, provider changes, chat submission or live plan changes performed.

## Open: trainer stalls after strength clarification

User reports the trainer gets stuck after requesting a plan. Inspected the existing Training tab without refreshing, submitting, stopping the request or modifying preferences/plans.

Observed conversation:

1. User requests sixteen weeks focused on FTP/endurance plus cycling-support bodyweight/core strength; cycling Mon/Wed/Fri/Sun, strength possible Tue/Thu/Sat, weekday rides60–90minutes and Friday up to5hours, with a power meter/trainer and pull-up/dip bars.
2. Assistant gives a block outline and asks for FTP/test date, strength time and comfortable pull-up/dip counts.
3. User replies: “for strengh 30 minutes / pull ups I do 5 / dips I do 5 / i am a begginer in strength”.
4. Assistant remains at **“Checking your records…”**. Composer is disabled, **Stop** is available, and helper text says **“Still working—local models can take longer.”** The selected provider visibly reports **ChatGPT account — Ready**, while the backend header reports connected. The local-model helper text is therefore misleading for the selected provider.

Status: user-reported stall with matching in-progress UI directly observed; elapsed request duration and root cause not established. Investigate request/tool/stream completion, timeouts and error recovery, preserving the supplied strength facts and draft conversation. Avoid repeating questions already answered. Separately review the FTP wording: the first answer asks for a tested FTP/date despite knowing the stored reference, rather than simply offering authorization to use the dated reference as previously requested. No new FTP measurement should be invented.

QC note only: no repair, tests, refresh, Stop action, provider change or live plan mutation performed. This is distinct from the earlier temporary loading issue that the user resolved by refreshing.


## Repair and focused acceptance — 18 October 2026

Scope: Training section, trainer routing/context/tool contracts, preview/approval, active program and today suggestions. Existing workspace changes preserved. User explicitly requested QC in this turn and confirmed Tuesday/Thursday strength, 30 minutes, Saturday rest.

### Implemented

- Fixed questionnaire syntax error that prevented module import.
- Bounded semantic extraction requests to 15 seconds, with deterministic parsing fallback. Training chat releases its composer after a 90-second overall request timeout and explains retry; provider-neutral slow-request wording.
- Retain reversed capacity wording (`pull ups I do 5`, `dips I do 5`), common strength/beginner misspellings and sport-specific durations.
- Aligned today tool description with independent/plan modes; changing input clears stale displayed recommendations.
- Agent preview now reads retained candidate answers and accepts candidate preferences/session edits in its schema. Avoids previewing only older saved settings.
- Preserve selected sports and ask for missing sport slots instead of silently omitting them.
- Removed redundant Save coaching brief control, which saved direction while silently dropping unsaved schedule edits. Chat setup save and reviewed activation remain the explicit save paths.
- Editing a later program week no longer fails first-week-only activation validation. Activation preserves original program start/end rather than restarting its duration.
- Retire the accepted pending questionnaire after approval; archive its provenance in the saved plan, avoiding stale-candidate reloads.
- With no recorded strength sessions, use the provisional starter allowance rather than a zero-history floor below the supported minimum. Avoid placing cycling quality immediately before an agreed strength day.
- Distinguish initial plan loading from a verified absence of a saved plan.

### Tools and context reviewed

| Tool | Contract |
| --- | --- |
| get_training_context | Read preferences, missing details and history-derived planning limits. Availability is a ceiling; optional weekly caps are separate. |
| preview_training_plan | Read retained candidate, preview sessions/blocks; cannot activate. |
| propose_training_setup | Reviewable preference/calibration proposal; Save setup does not activate. |
| get_active_training_plan | Read accepted direction, planned sessions and latest review. |
| propose_training_adjustment | Reviewable schedule/feedback changes; requires save and revision checks. |
| propose_training_event | Event proposal for current active program; explicit save adapts surrounding sessions. |
| suggest_today_workout | Independent ignores active direction/calendar; plan mode follows assigned sessions/rest. Both retain personal restrictions/history/recovery; neither saves. |
| get_recent_training_mix | Recorded benefit-label evidence; missing labels do not prove physiological deficits. |

Natural language remains supported through semantic extraction plus local parsing and contextual short replies. No provider model/access settings were changed. Actual provider generation/timeout recovery was not tested against a deliberately stalled remote connection; timeout contract and fallback were tested with a mocked provider.

### Executed verification

`test_trainer_section_qc.py`: **5 tests passed**, including three sport subcases. Isolated migrated databases cover cycling FTP, running endurance and strength plans; explicit activation; rolling next-seven-day continuation; independent and plan suggestions with no writes; later-week edit/approval preserving program dates; rescheduling; pause/resume; event add/remove; cancellation and deletion. Additional cases check missing selected-sport slots, mixed cycling/strength generation, the reported capacity reply and extraction timeout fallback.

Frontend typecheck and production build passed. Live browser: independent cycling suggestion returned warm-up/main/cooldown; running suggestion returned HTTP 200; candidate review displayed sessions and blocks; active plan expanded its controls; strength detail expanded and collapsed correctly. Destructive controls were exercised through their backend operations on isolated databases, not clicked on the personal plan. Manual preferences/save feedback UI were source-reviewed, not exhaustively clicked.

### Personal plan outcome

Activated the retained 16-week FTP plan, 19 October 2026–7 February 2027. Confirmed active status in the live Training tab and verified the visible 18–24 October window: Sunday rest, Monday cycling 60 minutes, Tuesday strength 30 minutes, Wednesday cycling 60 minutes, Thursday strength 30 minutes, Friday cycling 36 minutes, Saturday rest. User availability remains a ceiling rather than an obligation to fill. See `active-plan.png`.

### Remaining QC limitations — not an all-green claim

The existing `test_training*.py` suite ran 82 tests and reported **15 failures and 25 errors**. Many assert superseded clock-time/mandatory weekly-total/default-duration behavior or fixed workout-volume assumptions; these tests have not been migrated to the current contract. The separately executed legacy active/remediation suites also had failures. Historical suites are therefore not green, and this report does not classify every failure as obsolete or claim every button was browser-tested. The focused current-contract acceptance tests pass. Further test migration and failure triage remain necessary before declaring comprehensive Training QC complete.


## Weekly-volume correction — 18 October 2026

User requested using multiple recent weeks for weekly budget. The previous policy used the median of only the latest three observed completed rolling weeks, despite displaying four. It did not literally use one week; this distinction was explained to the user.

Changed to a shared mean of the last four completed seven-day periods in both `training_volume.estimates` and `training_prescriptions.cycling_dose`. Today is excluded. Unknown uncovered weeks are not counted as zero; covered weeks without activity count as zero. Limited evidence remains provisional. Recovery/load reductions, optional user caps and availability limits still apply separately. Exposed baseline method and contributing weeks in the volume-estimate details.

Personal data verification: 181.3 + 395.9 + 186.0 + 293.1 minutes across 20 September–17 October → baseline 264.075 → current estimate/planning ceiling 264 minutes. Previous baseline was 186. This verification is read-only; existing accepted sessions, including Friday's 36-minute session, were not rewritten. Prioritizing Friday and redistributing an accepted week remain separate from this calculation change.

Executed focused QC: seven tests pass, including agreement between both calculation paths, use of all four weeks, exclusion of today's activity and missing-versus-covered-zero handling. Frontend typecheck passes. The earlier legacy-suite failures remain recorded above; no comprehensive all-green claim.


## Friday allocation and separate sport budgets — 19 October 2026

Resolved the previously pending Friday allocation issue. Generation reserves the uniquely longest primary cycling slot before allocating shorter weekday rides; an FTP interval selection cannot overwrite that reserved long ride. Equal-duration slots retain chronological allocation. Existing history/load/recovery and shared daily limits still apply.

Added a regression exercising a mixed cycling/strength plan with Friday as the long slot, validating preview, approval and active review retain the longest Friday ride within the cycling budget. The same fixture is previewed without strength to assert identical cycling allowance and total cycling minutes: strength's 60 minutes are additional, never deducted from the weekly cycling allowance.

Eight focused tests pass. Updated the personal active program using the current reviewed replacement contract, preserving original 19 October–7 February program dates. Verified the saved week and its subsequent active review: Mon cycling60, Tue strength30, Wed cycling60, Thu strength30, Fri cycling123, Sat rest, Sun cycling21. Cycling total264; strength total60; combined324 minutes. Friday is the longest ride. Confirmed the live Training tab and Friday details show Long endurance,23October,2h3m; screenshot `friday-rebalanced.png`. Restarted the local backend with the updated planner. Earlier legacy-suite limitations still apply; no unrelated suite was rerun.


## Conditional cycling progression ceiling — 19 October 2026

User requested adding up to20% on most non-recovery weeks. Implemented a maximum20% addition to the completed four-week cycling baseline, rather than compounding20% on prior prescribed volume. The ceiling requires at least two observed weeks, at least two completed cycling sessions with tolerable saved effort/soreness, normal fresh load, no rising-load signal and no adverse feedback/pain. Missing feedback is not invented as confirmed tolerance. Strength remains independent. Running progression is unchanged.

Recovery/taper/race/post-event weeks receive no added cycling progression; preview uses its actual reviewed week to select the block, rather than today's block. Existing reduced-week session handling remains. Planner/review guidance reports the canonical volume ceiling instead of the older secondary helper's weekly cap.

Nine focused tests pass, including20% ceiling and zero-increase cases for recovery, inadequate history/feedback, adverse feedback, rising/elevated/missing load. Current264-minute reference would permit at most317minutes with qualifying evidence; personal saved sessions were not changed because tolerance feedback does not yet qualify. This is a product planning heuristic, not evidence that20% guarantees improvement or is appropriate every week. Source consulted: Australian Institute of Sport, Training load in relation to loading and unloading phases of training, https://www.ausport.gov.au/ais/position_statements/training-load-in-relation-to-loading-and-unloading-phases-of-training .


## Purposeful ride lengths and quality mix — 19 October 2026

User rejected21-minute endurance filler and requested normal rides around one hour, recovery around30minutes. Identified that leftover-only allocation prevented Sunday from reaching the45-minute quality template minimum; Mon/Wed were also excluded from intensity because strength followed them, and Friday was reserved for the long ride.

Added a whole-week cycling allocation: fund meaningful regular sessions (aim60minutes, bounded by explicit shorter availability/history), then allocate remaining time to the long slot. If the budget cannot support all available days, omit a slot with an explanatory warning rather than prescribe a tiny residual. Actual shared daily ceilings, fixed/completed work, history limits and recovery constraints still apply. Reduced weeks cap generated cycling at30minutes. This is a planning preference, not a claim that short rides have no training value.

Quality sessions rotate threshold, tempo, VO2 and controlled short efforts across productive weeks; every fourth recovery week is excluded from that rotation, so short efforts are no longer made unreachable by matching the recovery-week index. Existing recovery/history/experience and fixed-demanding-session gates remain. Controlled short efforts are not represented as all-out sprint training or a verified anaerobic adaptation.

Ten focused tests pass. Coverage includes264-minute allocation →60/60/84/60; low-budget omission without leftover filler; Friday priority; separate strength budget; quality rotation; recovery weeks with no quality and cycling at most30minutes. Saved the user's reviewed replacement week, preserving program dates and active status: Mon60base, Tue30strength, Wed60base, Thu30strength, Fri84long endurance, Satrest, Sun60threshold. Cycling264; strength60. The subsequent active review preserves Sunday's threshold prescription and all hour-length regular rides. Verified in live Training and expanded Sunday interval details. Screenshot: `hour-quality-session.png`. Backend restarted. Earlier comprehensive legacy-QC limitations remain unchanged.


## Shared sprint/anaerobic support and goal-aware cycling mix — 19 October 2026

User explicitly requested implementing dedicated sprint/anaerobic work in all planners, and consulting cycling-plan platforms on goal-based mix rather than omitting types permanently.

Implemented shared prescription kinds `sprint` (4×8seconds,4-minute inter-effort recovery) and `anaerobic` (4×30seconds,4-minute inter-effort recovery), with15-minute warm-up and10-minute cooldown. Totals are exact. Work intervals use explicit effort/technique/repeatability guidance; FTP and HR are not used to invent peak/sprint watts.45-minute minimum for these protocols; shorter requests become correctly named easy endurance with a reason instead of compressing recovery. These are app starter templates, not reproductions of elite-study protocols or guaranteed adaptations.

Shared generation selects goal-aware eligible quality rotations for FTP/sustained power, endurance, short-power races (explicit event demands such as criterium/XC/cyclocross), and general cycling. Primary-strength plans do not acquire hard cycling automatically. Dedicated advanced intensity requires experienced cycling, at least program week5, a build phase, two recently completed tolerable quality sessions, and recovery clearance. Recovery/taper phases, adverse feedback and missing prerequisites defer advanced work with an explicit preview reason. Whole-week quality ceiling remains one added quality session; existing hard events/sessions count. Advanced-intensity weeks hold cycling volume at its recent baseline rather than simultaneously applying the20% volume increase. Strength budget remains separate.

The same kinds are recognized by demanding-session protection, event reconciliation, rescheduling, active review, plan-based today suggestions, interval rendering and card labels. Active review and plan suggestions recheck eligibility. New plans, resumed/rolling active plans and supported goal families use the same generator. The assistant/tool instructions now describe the implemented support.

Goal-aware summaries are visible in plan previews and expanded active controls. They show counts across an eligible quality-session rotation, explicitly not percentages of riding time or a claim that every type belongs in every week. The summaries derive from the accepted goal even for previously saved programs; personal future sprint/anaerobic sessions were not inserted ahead of eligibility.

Guidance consulted: TrainerRoad plan guide https://www.trainerroad.com/blog/training-plan-guide/ ; all plans https://www.trainerroad.com/all-cycling-training-plans ; TrainingPeaks build-phase guidance https://www.trainingpeaks.com/blog/3-key-workouts-for-cyclists-in-the-build-phase/ ; power levels https://trainingpeaks.com/blog/power-training-levels/ . Principles adopted: sustained versus short-power specificity, base/build phases, and retaining aerobic work around targeted quality. Numerical rotation weights are this app's provisional defaults, not these platforms' proprietary algorithms. Primary interval physiology sources consulted: https://pubmed.ncbi.nlm.nih.gov/34122152/ and https://pubmed.ncbi.nlm.nih.gov/7714837/ ; these support distinguishing effort duration/recovery, not the claim that the app's starter doses are validated for this user.

Executed21 training-scoped tests passed: four new acceptance tests, ten trainer-section tests, plus registry and existing prescription tests. New cases exercise distinct lap durations, exact totals, no invented sprint watt targets, short-session fallback, cycling-only capability, goal mix coverage/weights, shared eligibility for new previews/approval/active review/today suggestions, FTP/endurance/general/race goals, early/recovery/experience gates, adverse-feedback downgrade, and holding volume when adding advanced intensity. Frontend production build/typecheck pass. A live load check exposed readiness reads unnecessarily attempting configuration inserts while active review held a write lock; current settings now use a read-only path, with a regression holding an actual SQLite writer lock. Existing broader legacy-suite failures remain outside this focused verification; no all-suite-green claim.


Live verification follow-up: Training loaded successfully after the readiness read fix; active status, program dates and current threshold/base/strength sessions remain intact. Expanded active controls show the sustained-power mix (six eligible quality sessions: threshold2,tempo1,VO2one,sprint1,anaerobic1), prerequisite explanation and TrainerRoad/TrainingPeaks reference links. Screenshot `cycling-mix.png`. No personal sprint/anaerobic session was inserted into this early consistency week.
