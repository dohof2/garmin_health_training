# Independent QC / QA report — 11 October 2026

## User follow-ups — 14 October 2026 (implemented; browser verification pending)

Current fixes and verification are recorded in [15 October general QC](../2026-10-15-general/REPORT.md). The bullets below preserve the original requests; their original pending wording is historical.

- **Explore the details — date range through today.** Verify that the available/default date-range end extends through the current date in the user's browser timezone, including when the latest stored activity is older. Check that it advances as the date changes and that today's records can be included.
- **Garmin sync — update existing activities without duplicates.** Verify that a previously synced activity whose Garmin name (or other metadata) changes updates the same local activity using its stable Garmin activity identifier. Confirm the new name appears, the local activity identity and associated details remain intact, and repeated syncs do not increase the activity count for that identifier. The user has not checked whether duplication currently occurs.
- **Today's readiness card — very slow and intermittently fails to load (user follow-up, 15 October 2026).** The user reports that today's readiness is extremely slow and does not always finish loading. Investigate both latency and intermittent loading failures, including initial dashboard load, refresh and returning to the app. Measure request/calculation/render time, inspect failed or stalled requests and refresh races, and verify that loading always resolves to data, an explicit missing-data state or a recoverable error with retry. Preserve calculation correctness and freshness. These symptoms are user-reported; their cause and frequency have not yet been independently verified. Keep this item open until both speed and loading reliability are checked.
- **VO₂ max card — add a trend button and adjustable range.** Add a button on the VO₂ max card that opens the VO₂ max trend, showing the last four weeks by default. Allow the user to change the displayed date range. Verify the default period, range changes, and handling of missing data.
- **Assistant — answer general questions without unnecessary record checks.** General educational questions unrelated to a particular activity, such as “What is power?” or “What is TSS?”, should be answered directly without automatically starting tools to check personal records. An activity may be used as an optional helpful example, but the explanation must not depend on an activity or be restricted to recorded data. Verify that tools are used when the question actually needs personal activity evidence.
- **Assistant — more natural answers and less repetitive Garmin attribution.** Make answers sound more human and conversational. Avoid repeatedly framing explanations as “Garmin is…” or reiterating that Garmin supplies the data when the user already knows this. Mention the source when it meaningfully clarifies a metric, limitation, or distinction, while keeping the answer focused on the user's question. Review both general explanations and activity-specific answers.

> **Current status after authorized fixes:** read [FIXES.md](FIXES.md) for the completed remediation, passing checks, outstanding verification and next-session instructions. The findings and FAIL verdict below are the preserved **original audit**, before repairs. They are not the current implementation verdict.

**Acceptance verdict: FAIL for the requested requirements.** The existing regression suite passes, but independent tests expose data contamination, incomplete ingestion and incorrect assistant plot interpretation. No product fixes were made.

## Scope and method

Tested the working checkout at HEAD `91feb7b`, including its pre-existing uncommitted changes. This is a snapshot assessment, not a review of a clean release tag. Production data was read through an independent SQLite backup; UI mutations were made against a disposable copy on backend port 8001 and frontend port 5174. Fresh databases were used for import and fault-injection tests. Garmin credentials were not copied. The original Garmin archive was read without modification. New files are confined to this QA report/evidence directory.

Evidence levels are distinguished below: **reproduced** means an executed test or observed UI behavior; **inspection** means a source-level gap; **unverified** means an external dependency or browser delivery prevented an end-to-end result. A successful HTTP response alone is not proof of semantic correctness.

## Executed checks

| Check | Result |
|---|---|
| Existing backend unittest suite | **261 passed** |
| Frontend TypeScript / Vite build | **Passed** |
| Independent acceptance tests | **2 controls passed; 6 failed** |
| General API cases, including expected invalid-input responses | 34 returned expected statuses |
| Catalog plot execution | 54 metrics/fields × 4 configurations = **216 successful queries**; semantic defects remain |
| Assistant routing scenarios | 16 deterministic probes; live model separately tested in the UI |
| VO₂ reference thresholds | Both reference populations, all 12 age cohorts match; **96 boundary checks passed** |
| Database integrity / foreign keys | `ok`; zero foreign-key violations |
| Fresh import through the UI's backend endpoint | Completed response, but substantial datasets absent — **failed completeness** |
| Real archive primary/wellness/extended previews | Ready; no reported parsing failures in these stages |
| Five dataset CSV exports / JSON export | HTTP 200; browser chart download delivery remains unverified |
| Responsive UI | All 10 pages checked at 390 × 844; no document-wide overflow |

The regression suite and the independent failures are both valid results: the existing tests do not establish the user's broader acceptance criteria.

## Findings

P1 indicates incorrect/missing data or a central requested capability failing. P2 indicates an important usability, reliability or capability gap. Priorities are tester recommendations, not automatic instructions to fix.

### QA-01 — P1 — Synthetic data contributes to real plots and assistant summaries [reproduced]

The production snapshot contains **3 synthetic activities, 14 synthetic metric readings and 4 synthetic activity samples**. Source `synthetic_fixture` appears in steps, active calories, activity distance, duration, calories and elevation plots. Counts of visible fixture points are lower bounds because large plots thin their displayed points.

The assistant's steps summary for a seven-day fixture period uses **14 records across seven dates**, explicitly listing both `garmin_export` and `synthetic_fixture`. This changes calculated totals, not just visual appearance.

**Reproduce:** query steps/activity duration including the fixture dates, or ask for the steps summary for that period. **Expected:** synthetic fixtures excluded from user plots, statistics and assistant evidence. **Actual:** fixture records included. No fixture data was deleted. Evidence: [synthetic-audit.json](synthetic-audit.json), acceptance tests.

### QA-02 — P1 — Fresh UI import reports completion before all data families are imported [reproduced]

Using a new empty database and the real archive, the UI import endpoint reports `completed` and imports **1,054 activities and 52,086 metric readings**. It leaves **activity samples, health samples, hydration events, abnormal-heart-rate events and extended archive records at zero**. These are not merely absent archive categories: separate read-only preview stages find wellness/extended data in this archive.

The UI calls the primary importer without orchestrating the other ingestion stages. The already-populated database hides this problem during an ordinary repeat-import test.

**Reproduce:** preview and confirm the Garmin archive through the UI endpoint in a fresh database. **Expected:** completion accounts for every applicable ingestion stage and explicitly reports any omissions. **Actual:** summary import succeeds while additional datasets remain unimported. Evidence: [fresh-import-results.json](fresh-import-results.json), [archive-preview.json](archive-preview.json).

### QA-03 — P1 — Live sync does not fetch every supported Garmin data family [inspection]

The sync implementation has six streams: activities, daily, sleep, HRV, weight and VO₂. The installed Garmin client exposes additional endpoints for hydration, stress, respiration, SpO₂, Body Battery, training status and other records that this integration does not call.

This establishes an integration coverage gap; it does **not** establish which endpoints return data for this account today. The requirement to fetch all available data, including currently unused data, cannot pass with this endpoint selection. Actual Garmin responses, MFA and full authenticated sync were not tested because the disposable environment had no saved session.

### QA-04 — P1 — Unexpected sync payload is treated as a successfully fetched empty day [reproduced fault injection]

A fake daily provider returning `['unexpected payload']` produces `completed`, zero imported records, no failures and advanced coverage. An invalid provider response is therefore indistinguishable from a valid empty result and can conceal a fetch failure.

**Expected:** validation failure, visible error and no successful coverage advancement. Evidence: [malformed-sync.json](malformed-sync.json), acceptance tests. This is a simulated provider fault, not an observed Garmin outage.

### QA-05 — P1 — Removed activities still contribute to plots and statistics [reproduced]

Soft-removing an activity excludes it from the ordinary activity list but leaves it in chart results and their counts. In the snapshot probe the count remained **1,065 before and after removal** and the removed identifier remained plotted. A fresh-database acceptance test isolates the same failure.

**Expected:** consistent removed-record filtering across lists, plots and calculations. Evidence: [supplementary-results.json](supplementary-results.json), acceptance tests. The snapshot activity was restored after the probe.

### QA-06 — P1 — Assistant silently drops separate date ranges [reproduced]

“Plot weight from 2026-01-01 to 2026-02-01 and steps from 2026-03-01 to 2026-04-01” returns both plots with neither requested date range. It uses all-history results: **925 weight observations and 2,997 steps observations**.

A separate fixture test reproduces this with two short January periods. Some explicitly separated/semicolon forms work, so the failure is phrasing-dependent.

**Expected:** both periods preserved, or a clarification/error; never silent substitution of all history. Evidence: [independent-results.json](independent-results.json), acceptance tests.

### QA-07 — P1 — Requested transformations silently become raw history [reproduced]

Weekly median and seven-day rolling-average requests return raw observations without applying the requested transformation or clearly saying it is unsupported. The independent fixture probe requested aggregation and received all 28 raw observations.

**Expected:** correct transformation or an explicit limitation/clarification. A syntactically valid plot does not satisfy this request. Evidence: assistant probes and acceptance tests.

### QA-08 — P1 — A requested comparison silently loses one metric [reproduced]

“Plot body battery versus sleep score for the last three months” returns a single sleep-score line with 90 observations. Body Battery and the comparison are discarded without an error. The isolated acceptance test also receives `line` instead of a comparison.

**Expected:** clarify which Body Battery measurement is meant, then compare both metrics, or explain the unsupported request. Evidence: assistant probes and acceptance tests.

### QA-09 — P2 — Exploration beyond the fixed catalog is limited [reproduced / inspection]

Supported catalog plotting works broadly, including explicit resting-HR versus cycling-VO₂ comparison. However, stored hydration and acute-training-load data are unavailable as plot catalog metrics. Cycling cadence is not exposed as an activity plot field despite sensor data being stored. Cross-family questions such as cycling power versus sleep duration on the same date are not supported by the current plot pairing schema.

These gaps prevent the requested assistant from reliably creating plots outside the apparent preset scope. A response should disclose unsupported metrics/joins/transformations rather than imply the requested analysis was performed.

### QA-10 — P2 — Live assistant produces a tool-argument error [reproduced]

With local Qwen/Ollama showing Ready, “Plot hydration over time” produces: `The grounded assistant could not complete the request: Unexpected tool arguments: timezone`.

Other live requests worked, including today's training readiness, which agreed with the dashboard result. The error demonstrates a particular unsupported-query failure, not total assistant failure. Deterministic tests that intentionally disable model calls are separate evidence and are not counted as live model outages.

### QA-11 — P2 — Completed assistant answer begins outside the visible chat area [reproduced]

Following a long coaching answer, another completed response increases the chat scroll height from **2,195 to 2,464 px**, while scroll position stays at **1,299 px**. The chat viewport ends at approximately **717 px** on screen and the new answer starts at approximately **805 px**, outside its clipped area.

**Expected:** automatically bring the start of the new answer into view after completion, as requested. **Actual:** user must scroll manually. Source inspection also finds no completion-time chat scroll handling. Plot workspace scrolling is a separate behavior.

### QA-12 — P2 — An ancillary startup failure is presented as total backend failure [reproduced under a configuration fault]

When a Garmin connection-status request failed because the client rejected a symlinked data-directory path, the global bootstrap displayed “Backend not running” and disabled assistant use even though `/api/health` returned 200. Using the canonical directory path resolved the environmental trigger.

This is an error-isolation/messaging finding under an explicitly reproduced configuration fault, not a claim that the normal installation cannot start.

### QA-13 — P2 — VO₂ text matches the reference, but the gauge scale is categorical [verified]

The application threshold arrays match the linked [Garmin / Cooper reference](https://www8.garmin.com/manuals/webhelp/GUID-9183E86B-2399-4CFC-AB50-EAFC6D6ED326/EN-US/GUID-1FBCCD9E-19E1-4E4C-BD60-1793B5B97EB3.html). For males aged 40–49, Good begins at 42.4 and Excellent at 46.4; **44.7 is correctly labelled Good**.

The subsequently supplied [Garmin blog](https://www.garmin.com/en-SG/blog/general/whats-a-good-vo2-max-for-me/) uses a different seven-category chart with five-year age bands. For males aged 40–44 it lists Good as 42–46, Very good as 47–51 and Excellent above 51. The app instead follows the five-category Cooper manual table. These two Garmin references are not interchangeable; the reference scheme must be explicit. Under the manual scheme, 46.4 is the start of Excellent, not its midpoint.

The visual uses five equal-width color sections and a pointer fixed at the center of its category. Values **42.4 and 46.3 have exactly the same pointer position**. This does not express distance to the next threshold or the reference's percentile boundaries. Treat it as a categorical indicator; the UI does not explain this convention, which can make it appear mismatched.

The age is calculated at rendering time, even for historical readings. Values near a changed age-band boundary can therefore change label as the user ages without the measurement changing. The UI should make its age convention explicit. This audit did not prove a wrong label for the displayed 44.7 measurement. Evidence: [vo2-audit.json](vo2-audit.json), [vo2_audit.mjs](vo2_audit.mjs).

### QA-14 — P1 completeness risk — Live FIT ingestion does not retain all unused content [inspection; full live reproduction pending]

The sync activity-detail path decodes FIT bytes into selected sample columns and preserves session summaries. It does not persist the original downloaded FIT bytes through `source_files`; no general retention path for all lap/event/developer messages was identified in that sync path. Sanitized JSON sync payload retention is a separate mechanism.

The archive importer retains the original archive, but that does not establish equivalent preservation for live downloads. An authenticated sync using a FIT file containing extra fields/messages is needed to measure the exact loss. Until then, the “all fetched data retained even if unused” requirement remains unverified for live FIT content.

## UI / button and human-usability coverage

These checks used the disposable data copy. “Pass” applies to the listed controls and observed result, not every possible input or hidden state.

| Area | Exercised controls / result |
|---|---|
| Navigation | All 10 main links reached their expected page |
| Dashboard graphs | Add/save, expand/collapse, trend toggle, duplicate, remove, reorder, replace/edit, cancel — passed |
| Dashboard cards | Customize, move, hide, add back, Done — passed |
| Activities | 30-day/90-day/All filters and activity details — passed; All displays the most recent 50, with no pagination |
| Assistant | Ask, explicit weight plot, plot recall, pin-to-dashboard review, seven-day health summary, live readiness, coaching proposal transfer — passed for these requests; unsupported queries fail as above |
| Assistant cancellation | Stop produces “Response stopped” and restores usable input — passed |
| Training | Preferences save, fixed commitment preview, recovery around hard trip, brief save, draft creation/acceptance, feedback save, volume proposal review/dismiss — passed |
| Nutrition | Manual entry/review/confirm, add/remove item, food search, meal edit/clear, remove/restore and recalculated totals — passed |
| Maintenance | Add, edit/save, revisions, remove, include removed, restore, undo — passed |
| Profile / settings | Display name save, goal add/remove/save, dated weight entry, unchanged AI settings save — passed |
| Readiness | Refresh, explanation/method disclosure, historical date and parameter editor opening — passed |
| Data / sync | Unauthenticated check gives a clear not-connected error; Sync Now disabled; missing-archive message handled; separate real archive previews and fresh import tested via API |
| Mobile | 390 × 844 across all pages; wide tables/trends scroll inside their containers |
| Console | No warnings/errors at the sampled browser checkpoint; not a complete session-wide assertion |

Assistant training output respected a hard Wednesday three-hour ride at 08:00, surrounded it with recovery and kept the reviewed weekly plan within the saved time budget. This validates the exercised planning workflow; it does not establish every coaching request or model response as correct.

Additional usability observations: coverage took roughly four seconds and readiness forecast roughly eight seconds in the measured API run; feedback/loading should remain clear. An activity displayed an implausible maximum speed of 221.6 km/h. This is a source-data quality observation, not a proven conversion bug; no value was edited.

## Explicit limits / unverified controls

- Garmin login, MFA, authenticated account endpoint completeness and real incremental sync were not exercised without a session in the isolated environment.
- OpenAI live mode lacked a configured key; local Qwen was exercised. Photo/vision nutrition interpretation was not live-tested.
- Browser chart CSV click did not yield a captured download event. The API exports succeeded; browser delivery is **unverified**, not declared broken.
- Recipe-specific workflows, photo upload, nutrition-target edits, readiness-parameter saving, production-size backup ZIP restore and external workout publishing were not completed end to end. Existing backend tests cover some related logic, but this does not replace UI verification.
- No claim is made that every button in every conditional state works. The executed matrix lists actual coverage; remaining paths are test gaps.
- Full keyboard-only navigation, screen-reader operation and a formal WCAG audit were not performed.

## Data completeness interpretation

The populated snapshot's importer coverage reports 10/10 implemented categories, 21,933 tracked records and no failed/unmatched tracked records. Extended preview accounts for 298 outer selections as 144 imported, 121 handled elsewhere and 33 administrative exclusions, with zero unsupported selections. These figures describe implemented stages; they do not certify complete fresh UI import, live endpoint coverage or normalization of every numeric FIT field.

The original archive contains 55,754 files, including 55,448 FIT files and eight nested archives. Keeping that original is valuable, but the app must separately account for fetched, preserved, normalized and plot-accessible data. Findings QA-02, QA-03 and QA-14 prevent an all-data guarantee.

## Reproduction artifacts

- [Existing regression log](backend-test-results.txt)
- [Independent acceptance log](acceptance-results.txt) / [acceptance probes](acceptance_probes.py)
- [Reusable independent audit](independent_audit.py) / [API and assistant results](independent-results.json)
- [Additional chart/export/deletion results](supplementary-results.json)
- [Synthetic inclusion](synthetic-audit.json)
- [Fresh import](fresh-import-results.json) / [archive previews](archive-preview.json)
- [Malformed sync](malformed-sync.json)
- [VO₂ verification](vo2-audit.json) / [executable VO₂ checks](vo2_audit.mjs)

Run existing tests with `PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests`; build with `npm run build` in `frontend`. Run new acceptance probes from the repository root with `PYTHONPATH=backend .venv/bin/python docs/qa/2026-10-11/acceptance_probes.py`. They intentionally exit unsuccessfully while the six reproduced acceptance defects remain. Run VO₂ checks with `node docs/qa/2026-10-11/vo2_audit.mjs`. The larger snapshot audit requires its documented disposable temporary database; do not point mutation probes at production.

**No debugging changes, synthetic-data removal or product repairs were performed.**
