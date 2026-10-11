# FIT access and interval analysis — 11 October 2026

Status: implemented, recovered locally, tested, and available through the ChatGPT assistant. This supersedes the unresolved lap/time-series access status in earlier checkpoints.

## What changed

- `get_activity_stream` exposes stored lap summaries and timestamped power, heart rate, cadence and speed. Elapsed-time selection and explicit display reduction keep responses bounded. Lap details are capped at 100; `get_fit_activity_data` provides pagination for larger collections.
- `analyze_sprint_intervals` scans all eligible recorded rides, rather than the first 100, for repeated short efforts. The default request searches 10–15 seconds with at least two efforts per ride. Recorded lap boundaries are used where complete continuous power is available; separate continuous above-threshold bursts provide additional candidates. Lap and burst overlaps are deduplicated. Long efforts are not chopped into repeated short windows.
- Default detection threshold is 1.8 times each ride's median positive recorded power. Users can specify watts explicitly. This is a disclosed heuristic for candidate high-power efforts, not proof of sprint workout intent. The mean is timestamp-weighted using zero-order hold between observations at most three seconds apart. Missing power or larger gaps prevent an effort calculation. No duration is invented for a final isolated sample.
- Separate, refreshable plots group efforts by nearest whole-second duration. Each point is the mean of that ride's qualifying effort averages. Counts and plots cover all matching rides; model-facing ride details are explicitly capped to the latest 100. Complete plot data renders locally while calculated summaries are sent to the model to reduce shared-plan consumption.
- `find_fit_fields` discovers recorded message types and fields across the full inventory, including grit, flow, jump messages and developer fields. `get_fit_activity_data` reads preserved originals on demand, reports field units and statistics over all selected-message rows, and paginates raw records. It can inspect arbitrary fields, not a fixed measurement whitelist. Private account/device identifier keys retain the existing source sanitization.
- FIT numeric fields and message counts appear in the chart catalog and can be plotted by ride date. Mean, maximum, minimum, sum and non-null count are available. Recorded jump events are counted; jumps are not inferred from GPS. Unknown/custom units remain unknown. Non-numeric arrays/text remain inspectable but are not fabricated into scalar measurements.
- Future sync/import retains lap/event metadata, non-continuous message payloads and a full field inventory, with FIT detail version 2. Complete continuous FIT fields remain accessible through the preserved original without duplicating millions of raw records into the activity JSON.

## Local recovery

A local SQLite backup was created before recovery at `data/backups/before-fit-lap-recovery-2026-10-11.sqlite3` (ignored by Git). `scripts/recover_activity_laps.py` recovered metadata from existing preserved files without reimporting or duplicating continuous samples.

Result: **1,044 activities recovered, 7,401 lap messages, zero failures**. A second run recovered zero records and made no changes. Inventory discovery identifies grit/flow fields in **707 activities** and jump-related fields in **330 activities**. Presence alone does not establish a non-null recorded value. **18 activities have no recovered FIT inventory**; tools explicitly report this gap.

The original read-only sample and stream counts remain historical observations. No new upload is required for the recovered files. No Garmin network reconciliation was performed for missing originals.

## Verification

- **333 backend tests pass**; frontend production build passes.
- New tests cover timestamp-weighted power, sample gaps/nulls, rejecting long efforts as short sprints, overlap deduplication, duration-separated plots and refresh, explicit thresholds, date filters, more than 100 matching rides, synthetic/deleted record exclusion, arbitrary/custom fields, unit handling, pagination statistics, numeric FIT plots, binary-field preservation, and idempotent recovery without sample duplication.
- **Eight live FIT questions checked on invented isolated data**, including the user's exact sprint question, explicit threshold, laps/continuous data, grit/flow, recorded jump count/height, grit history, jump history and a custom field. Seven completed initially; the grit-plot request encountered OpenAI HTTP 503 and passed its targeted retry. The final sprint question was retested after compacting model evidence. No real Garmin records were sent to the model during QA.
- Local production sprint analysis scanned 848 cycling activities, found 1,252 candidate efforts in 215 qualifying rides, and produced six duration-separated plots in 6.99 seconds without network calls. These are heuristic candidates, not certified sprint classifications; private result data remains in ignored local JSON evidence. The browser session's real health questions were not resubmitted as automated QA.

Evidence: `backend-sprint-intervals.txt`, `fit-lap-recovery.txt`, local ignored `chatgpt-fit-live.json`, `chatgpt-fit-retest.json`, `chatgpt-fit-final-sprint.json`, and `sprint-production-local.json`.

## Limits that remain

Detection is not a validated sprint classifier. Changing recovery, fatigue, equipment, conditions, duration or intent can affect power; a rising chart is not proof of improved fitness. Exact lap averages require enough continuous power coverage under this analysis method; recorded lap fields can still be inspected separately when continuous coverage is insufficient. Source files without a recoverable inventory remain explicit gaps. Unknown FIT/developer semantics are not automatically interpreted. This focused work does not certify every possible FIT question, every app control, mobile use or the earlier full general QC.

Garmin documents separate session/lap/record messages and extensible developer fields in its [activity decoding guide](https://developer.garmin.com/fit/articles/cookbook/decoding_activity_files.html). Units are read from the installed Garmin FIT SDK profile, rather than guessed by the language model.
