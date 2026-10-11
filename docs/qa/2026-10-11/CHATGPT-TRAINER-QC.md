# ChatGPT trainer follow-up — 11 October 2026

Current FIT follow-up: [FIT-INTERVAL-QC.md](FIT-INTERVAL-QC.md) supersedes the earlier unresolved lap/time-series finding. Four new scoped tools, numeric FIT-field plots and sprint detection are implemented; 1,044 activities/7,401 laps recovered without errors, 333 backend tests pass, and eight live FIT questions were checked with targeted retests. The original limitations below are historical checkpoints; 18 activities without a recovered inventory remain explicit gaps.

Status: trainer changes implemented; full isolated live question-bank retest completed. FIT lap/time-series access remains unresolved.

## Change

The selected ChatGPT provider now uses a separate trainer prompt and a bounded tool conversation. It bypasses the earlier Qwen keyword routing, forced tool selection, schema narrowing, argument rewriting, canned answers and generic no-evidence replacement. Other providers retain their compatibility path. Application calculations, data-source filtering, tool argument validation, review-before-save and explicit GPS-matching authorization remain.

Added a direct general latest-ride comparison tool. Ride assessment now includes recorded activity metrics and Garmin primary benefit, which were previously omitted from that tool. The coach can answer follow-ups using fresh evidence instead of declaring stored power/benefit absent. Personal information remains local Garmin/app context; OpenAI account personal data is not supplied.

Live streams revealed that the completion event can contain no output even though prior events contain valid function calls/text. The parser now retains those streamed output items and text, and still requires terminal success. No paid fallback is used.

## Test method

`scripts/run_chatgpt_trainer_qc.py` invokes the real selected Sol Light model with invented records in a temporary isolated database: 53 rides and 365 days of health observations. Authentication is used from the connected backend account, but no real Garmin records, personal app profile or prior personal chat messages are sent in these tests. The production database and plots do not contain the invented records.

The existing 134-question bank is rerun, with additional trainer, follow-up, account-privacy and goal-proposal cases. Automated checks cover completion, tools, period bounds, requested plot fields/transforms and excessive length. Tool-choice alternatives and clarification wording require human-style review; passing a completion check alone does not certify answer quality. Detailed responses are local JSON evidence ignored by Git.

## Findings repaired

- Empty answers from metadata-only terminal stream events: fixed and regression-tested.
- Follow-up assessment omitting available power and source training benefit: fixed and verified live.
- One-day drift in trailing-year plot bounds: added a deterministic calendar anchor to the trainer prompt; affected cases passed live retests.
- Proposal schema accidentally restricted to profile changes by the old Qwen helper: raw application schemas now allow reviewed goal proposals; live proposal correctly stated that nothing was saved.
- Initial plotting request error: retry passed. An error remains visible to the user rather than silently changing provider.

## Verification checkpoint

320 backend tests pass, including trainer routing, streamed-item parsing, model-written answers, raw proposal schema and retained source fields. Frontend production build passes. Nine unique trainer cases completed live after targeted fixes, including the reviewed goal proposal. All 32 plot cases completed their checks after targeted retests. Training/investigation bank checks completed without runtime errors; two tool-selection flags were manually accepted: an initial general-fitness discussion appropriately asked for preferred activities, and weight change used a period comparison rather than a single summary.

Final live coverage: **143 unique cases (134 bank questions + 9 trainer cases)**. After targeted retests, every case completed with an answer and no runtime error. The final main 80-case batch completed with zero errors. Two short general-comparison replies initially caused unnecessary clarification or a 41-row inventory; conversational instructions were corrected and both retests produced concise general comparisons. The short GPS reply was also retested and correctly reported absent route data.

Eight automated expected-tool flags remain as reviewed alternatives: general-fitness advice used training context before requesting preferences; weight change used a period-comparison tool; four explicit GPS cases encountered a fixture with no GPS reference and correctly withheld matching; two benefit questions used `assess_ride`, returning the recorded primary benefit and scores. These are not runtime failures. The GPS error path does not emit a successful evidence event, so the runner records no successful matching tool. Some original GPS responses unnecessarily requested a reference date after reporting no stored GPS; this remains a conversational polish limitation. Clearly disclosed rolling/median defaults were accepted rather than requiring a clarification for every possible chart choice.

Evidence: `chatgpt-trainer-live-03.json`, `chatgpt-trainer-live-04.json`, `chatgpt-trainer-bank-01.json` through `-04.json`, `chatgpt-trainer-bank-retest-01.json`, and `chatgpt-trainer-followup-retest.json`. Earlier failed attempts are retained as historical evidence, not counted as passing. These JSON files are local and ignored by Git. The backend was restarted to load the tested trainer path. Actual personal-data answer quality, mobile use and full original general QC remain separate from this isolated model test; these results are not a claim that every assistant question will succeed.

## Newly confirmed FIT access gaps

Read-only production inventory found 2,937,459 normalized activity samples across 1,057 activities, with 1,048 activities containing FIT session summaries. No activity contains a saved `fit_laps` collection. These counts were inspected locally; no production sample values were sent to the live QC model.

`preserve_fit_summary` retains session messages but not lap messages. Both archive import and sync call this function, so lap summaries are not exposed in the normalized database. Original FIT files must be decoded to establish available laps before recovery; absence from the database does not establish absence from the source file.

A read-only decode of one preserved original activity FIT file confirmed 11 lap messages and 1,786 record messages with zero decoder errors. This establishes actual lap loss from the accessible database for that checked source, not merely a hypothetical FIT capability. No reimport or production changes were performed during this check.

Assistant activity tools currently expose sample aggregates, not a general time-series/lap investigation tool. Continuous data exists but a coach cannot reliably inspect within-ride intervals, pacing or steadiness using these aggregate tools. This is an unresolved data-access defect, separate from model quality. A follow-up should preserve lap messages and arbitrary FIT fields, recover available originals without duplication, and add bounded lap/time-series tools with meaningful tests. Do not claim complete FIT-field coverage or certify interval coaching yet.

### User reproduction: repeated short sprints

The user asked to find all rides with repeated 10–15-second intervals and plot interval-average power against ride date to investigate sprint improvement. The visible assistant called only the chart catalog, correctly explained that whole-ride average power cannot answer this question, and reported that its tools cannot access laps or second-by-second power. It then unnecessarily asked the user to upload FIT files despite originals and continuous samples already being stored locally.

Acceptance case for the data-access fix: use existing stored records/originals first; find repeated efforts using recorded lap/workout markers where available and a clearly disclosed detection method otherwise; calculate each effort's average power in the backend, respecting timestamps, sampling gaps and missing power; distinguish 10-second and 15-second efforts; plot dated effort/ride summaries with counts and source links. Do not treat every overlapping high-power window as a separate sprint or claim improvement from incompatible durations and conditions. Ask only for genuinely missing essential information; do not request another upload merely because the current tools omit stored data. This reproduction is not covered by the prior 143-case completion result.
