# QC remediation and next-session handoff — 11 October 2026

Current FIT follow-up: [FIT-INTERVAL-QC.md](FIT-INTERVAL-QC.md) supersedes the earlier unresolved lap/time-series finding. Four new scoped tools, numeric FIT-field plots and sprint detection are implemented; 1,044 activities/7,401 laps recovered without errors, 333 backend tests pass, and eight live FIT questions were checked with targeted retests. The original limitations below are historical checkpoints; 18 activities without a recovered inventory remain explicit gaps.

## Latest assistant follow-up

Latest user preference: general comparisons default to all recorded rides; matching requires an explicit request. Days/weeks/months/years and short period replies are supported. 298 backend tests pass and the exact “my ride … kast 3 months” request was verified in the app.

See [ASSISTANT-QC.md](ASSISTANT-QC.md) and [the 133-question bank](ASSISTANT-QUESTIONS.md) for the latest completed assistant repairs and final verification. This supersedes the older browser-comparison pending notes below; both scope choices and answer scrolling have now been exercised in the app. Prior checkpoints below remain historical.

## Latest continuation instructions

After the usage reset, prioritize assistant robustness: create at least 100 ordinary-language questions with paraphrases, ambiguous cases and multi-turn follow-ups, then QC through the live assistant. Cover general/GPS ride comparisons and period handling, health investigation, wider plotting and transformations, training constraints, missing data, provider failures and synthetic exclusion. For each case record expected interpretation/data, actual response, numerical accuracy and pass/fail. Keep answers concise: answer first, key numbers next, only material caveats, one focused clarification when needed, more detail on request. This bank has not yet been created or run.

Latest completed verification: **276 backend tests passed in 10.313 s**, including the user's exact “in the last year” wording. Browser verification remains pending. The user subsequently authorized commit and push of the current work. Earlier “uncommitted” descriptions below refer to the state before this authorization. Detailed JSON evidence is kept locally and excluded from Git because it can contain personal records/account IDs; report links to these files require this local checkout.

The user authorized product fixes after the independent audit, then requested that all QC findings be addressed. All 14 numbered findings now have implementation changes and verification described below. This does **not** certify every button, provider, account date or accessibility scenario: the remaining checks are explicit. Work stopped for the user's usage cutoff; the latest check showed **11% remaining in the five-hour allowance** (89% consumed). The latest instruction is to stop at **5% remaining**, superseding older handoff cutoffs.

All changes remain uncommitted in `/Users/dotanhofman/Documents/garmin_app`, alongside pre-existing changes. No commit, push, deployment or Garmin workout publication was performed. Preserve this entire working checkout; do not reset it. The original audit is [REPORT.md](REPORT.md), with its original evidence retained separately from the new results. The app-owned temporary QA backend (port 8001) and frontend (port 5174) were stopped at session end; user-managed services were left alone.

## Completed findings

| Finding | What changed | Verification / status |
|---|---|---|
| QA-01 Synthetic data | Excluded `synthetic_fixture` from user history, plot/catalog queries, assistant summaries, readiness and training workload. Fixture rows remain stored; they were not deleted. | Regression and independent acceptance tests pass; plot and assistant probes exclude fixtures. |
| QA-02 Incomplete fresh import | Confirmed import orchestrates primary summaries, activity FIT, activity XML, health FIT, wellness and extended data. Every stage is reported; partial failures produce an attention/error state rather than false completion. | Actual fresh import completed all stages; see counts below and `fresh-import-fixed.json`. |
| QA-03 Incomplete live sync | Added supplementary collection for daily/range/static data, paginated collections and discovered child records. JSON is retained even when unused. Coverage test accounts for all 112 installed SDK `get_*` methods across primary and supplementary paths. Endpoint failures/unsupported/unavailable results are explicit. | Real read-only Garmin run completed in 43.33 s with 124 successful endpoint/detail responses, no failures and no unsupported methods. This was a selected-period probe, not a full-history production sync. |
| QA-04 Malformed sync payload | Invalid daily/sleep/weight payload shapes fail validation. Failed intervals do not advance successful coverage; partial supplementary payloads are retained. | Fault-injection acceptance and regression tests pass. Latest diagnostic test verifies persisted success/failure details. |
| QA-05 Removed activities | Applied removed-record filtering consistently to activity plots and statistics. | Independent acceptance passes. |
| QA-06 Separate date periods | Shared plot splitting preserves an AND separator after a completed date range. Individual plot periods survive normalization. | Independent acceptance passes. |
| QA-07 Transformations | Implemented daily/weekly/monthly mean, median and sum, plus trailing calendar-window means; schemas and assistant requests carry the transformations. Ambiguous combined aggregation/rolling requests ask for separate plots. | Numeric regression checks and real-data weekly-median/seven-day-rolling probes pass. |
| QA-08 Dropped comparison metric | Ambiguous Body Battery requests ask which measurement is intended. Comparisons cannot silently drop a requested metric. | Independent acceptance passes. |
| QA-09 Wider exploration | Added hydration, acute training load, cycling cadence, numeric retained archive fields and same-local-date health/activity comparisons, retaining each activity in either axis direction. | Actual-data assistant probes pass; catalog grew from 54 to 149 entries in the tested snapshot. Numeric archive discovery excludes array-index/identifier/timestamp fields. |
| QA-10 Assistant timezone error | Normalized model-added root timezone arguments for tools whose schemas do not accept them; supported tools retain timezone context. | Tool regression passes; hydration request works in the UI. Local coaching/data investigation also exercised. |
| QA-11 Answer scrolling | Scroll to the start of the completed answer; removed competing delayed plot scrolling. | Long coaching answer and subsequent answer starts observed inside the visible chat area. |
| QA-12 Startup isolation | Garmin status failure gets an unavailable state while other app functions can load; startup errors are specific. Canonical data-directory resolution fixes the reproduced symlink trigger. | Regression/build and UI checks pass for exercised flows. |
| QA-13 VO₂ reference/gauge | Gauge uses a numeric scale with actual threshold boundaries and a moving pointer. Legends expose numerical ranges and the five-category Garmin/Cooper reference. Historical readings use age on the measurement date. | 96 threshold boundary checks plus moving-pointer, birthday, historical-age and outlier checks pass. Male 40–49 Excellent starts at **46.4**; 44.7 is Good. The supplied seven-category Garmin blog uses a different scheme. |
| QA-14 Original live FIT retention | Preserve full downloaded FIT/ZIP bytes in hash-addressed `sync-originals` files with source-file tracking. Originals are included in inventory/export and backup paths, retaining unused lap/event/developer content. | Actual Garmin download: 560,172 bytes retained byte-for-byte, matching hash, 18,657 decoded samples, zero decode errors, 33 message families and one exportable original. |

Additional usability changes: Activities now supports **Load more**, verified from 50 to 100 records; import progress identifies all stages; sync details disclose retained extra data and named failures/unavailable/unsupported endpoints. Mobile health legends fit at 390 × 844 without document overflow.

## Verification completed

- **274 backend tests passed** in 10.037 s: [backend-fixed-results.txt](backend-fixed-results.txt).
- **All eight independent acceptance tests passed**, compared with six failures before repairs: [acceptance-fixed-results.txt](acceptance-fixed-results.txt).
- **13 remediation tests passed after the final sync-diagnostics change**. This final focused result was observed in the terminal; it is not a separate saved log. The full 274-test run preceded that last change and has not been repeated since.
- Latest frontend TypeScript/Vite production build passed after the diagnostic display and partial-import styling changes. `git diff --check` passed after all edits.
- VO₂ checks: [vo2-fixed-results.txt](vo2-fixed-results.txt), executable [vo2_fix_checks.mjs](vo2_fix_checks.mjs). Original `vo2_audit.mjs` describes the old implementation; use the new executable for current validation.
- Actual-data assistant results: [assistant-fixed-results.json](assistant-fixed-results.json). Hydration, acute load, cycling cadence, same-date power/sleep, weekly median weight and seven-day rolling plots all completed without errors.
- Actual fresh archive import: [fresh-import-fixed.json](fresh-import-fixed.json), 240.79 s, 1,058 activities, 52,086 metric readings, **2,912,230 activity samples**, **3,706,008 health samples**, 891 hydration events, 49 abnormal-HR events and 26,143 extended records. Wellness also imported 291 nutrition records. All reported stages completed without failed/unmatched files.
- Real Garmin read-only retrieval: [live-readonly-sync-results.json](live-readonly-sync-results.json); actual downloaded FIT preservation: [live-fit-results.json](live-fit-results.json). Non-phased training plans are reported as unavailable for the phased-details endpoint rather than a failed download; their parent plan records are retained.

The real archive was read without alteration. Import/mutation tests used disposable databases. The live Garmin tests read the existing authenticated session and fetched data without writing to Garmin or running a full production database sync. Zero normalized records in the supplementary live probe does not mean nothing was fetched: successful raw responses are listed separately and retention is regression-tested.

## Next session: remaining checks and limits

### Subsequent assistant ride-comparison fix

Further user reproduction used **“how was my last ride compared to the rides in the last year?”**, which bypassed the original narrowly worded handler and produced a false model claim that no rides existed. Extended the clarification/comparison path to “the last year,” “past year,” and last/past 12 months. These mean a trailing 365-day interval, while plain “last year” means the previous calendar year; dates are displayed explicitly. Both clarification choices preserve those bounds. Added an exact-phrase regression for the user's wording and its “general records” follow-up. Browser delivery remains to be confirmed in the next session; do not call this fully UI-verified.

The user reproduced “How was my last ride compared to other rides this year?” being incorrectly answered with zero GPS-route matches. A new deterministic broad comparison now computes the latest ride against other recorded cycling activities from January 1 through today, excluding the reference, removed records and fixtures. It reports per-measurement medians/counts and explicit mixed-ride limitations. Missing values are omitted. The user specifically requested clarification when scope is uncertain: this question now asks **“All rides, or rides on the same GPS route?”**; replies such as “All rides” and “Same route” select the appropriate branch while preserving this year's bounds. Explicit general comparison requests proceed directly. The new regression checks clarification, follow-up, actual numerical results, fixture/deletion/previous-year exclusion and GPS period arguments.

**Latest full suite: 275 tests passed in 9.966 s**, including the final sync-diagnostics changes. This supersedes the earlier 274-test checkpoint/full-suite pending note. Actual local-record comparison output is saved in `latest-ride-comparison-fixed.json`. The final reference-link field alignment followed the suite and is a presentation-only change. Browser verification of both clarification choices remains pending; this is a targeted fix for the latest-ride/this-year wording, not a claim that all comparison phrasing is covered. No frontend code changed for this follow-up.

1. Read this file and the original report before changing code. Run the full backend suite once on the final checkout, then build the frontend. The final sync-diagnostics code has focused coverage but needs the final full-suite checkpoint. Inspect the new diagnostic panel in the running UI; the final panel was build-tested, not browser-tested.
2. Start fresh app services using the project's documented launcher/configuration. Test full authenticated incremental/catch-up sync against a disposable database with explicit date bounds, checking persisted raw payloads, coverage and diagnostic reporting. The 124-response read-only probe proves live endpoint compatibility for the exercised period, not every historical interval/account state. Empty, unauthorized and account-unavailable endpoints must stay distinguishable from successful populated responses.
3. Continue the original report's unverified controls: browser chart CSV delivery; recipe-specific paths, photo upload/interpretation, nutrition-target edits, readiness-parameter saving, production-sized backup/restore, keyboard-only/screen-reader accessibility. OpenAI mode still needs a configured key. Existing unit tests are not substitutes for these UI checks.
4. Exercise assistant phrasing beyond the deterministic examples and verify the final retained numeric archive fields have useful units/labels. Same-date comparisons do not establish causation. Unknown fields remain preserved without invented interpretations.
5. Investigate the observed 221.6 km/h activity maximum as source-data quality before proposing a correction. Forecast/coverage latency observations remain follow-up work; no performance claim or formal WCAG certification is made.
6. Garmin workout publication remains deferred under the established project roadmap. No new external writes, commit or push are authorized by this handoff.

Useful commands from the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests
PYTHONPATH=backend .venv/bin/python docs/qa/2026-10-11/acceptance_probes.py
node docs/qa/2026-10-11/vo2_fix_checks.mjs
```

Run `npm run build` from `frontend`. Do not run mutation probes against production. Disposable large import directories may remain under `/private/tmp/garmin-qa-fresh-fixed` and `/private/tmp/garmin-qa`; they contain QA copies and are not production paths. Clean them only after identifying their ownership and whether they are still needed. Never delete the original Garmin archive or user-managed services.
# ChatGPT account connection checkpoint

Added a separate account-based provider, Settings sign-in/model selection, protected OAuth storage and strict streamed Responses handling. 311 backend tests and the frontend build pass; actual sign-in page reached. User consent and live ChatGPT answers remain pending. See [ASSISTANT-QC.md](ASSISTANT-QC.md) for verified scope, evidence and mobile limitations. No cloud/mobile deployment or paid fallback was enabled.
# ChatGPT trainer checkpoint — 11 October 2026

Current details: [CHATGPT-TRAINER-QC.md](CHATGPT-TRAINER-QC.md). ChatGPT now bypasses Qwen forced routing, canned answers and argument rewrites. Stream parsing and recorded benefit/power access were repaired; 320 backend tests pass. The full isolated live question-bank retest completed: 143 unique cases answered without runtime errors after targeted fixes; reviewed flags are documented.

Outstanding newly confirmed defect: FIT laps are decoded but not retained in normalized activity data, and continuous samples are exposed to the assistant only as aggregates. A checked original FIT file contains 11 laps and 1,786 records. Full source-field preservation, lap recovery and bounded time-series/lap tools still need implementation and QC. Earlier decode-success counts do not certify data accessibility.

## Nutrition layout and shared dashboard theme

Implemented daily totals → meal/food/amount entry → text/photo assistant → per-meal summaries, preserving reviewed saves, recipes, targets and reversible meal history. Text/photo review now uses the selected provider and cannot invent nutrient totals or write meals. Shared dashboard controls/cards/text applied across all ten tabs; header/browser renamed to Dotan's training and health space. 336 tests, frontend typecheck/build, live synthetic food-description review and all-ten-tab navigation passed. See [NUTRITION-THEME-QC.md](NUTRITION-THEME-QC.md) for limits, including real-photo accuracy and finite offline food catalog.
