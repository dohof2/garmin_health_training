# Sync freshness — 21 October 2026

The reported missing night score arrived during the user's manual sync. The existing schedule skipped further automatic reads once every checkpoint covered today's date, even if the watch uploaded overnight data later.

Automatic sync now rechecks all seven supported streams after one hour, with a schedule check every 15 minutes while the app is open. The normal three-day overlap rechecks previously empty days and corrections; existing full-gap catch-up and durable retry behavior remain. A running job prevents another scheduled job. Manual sync always uses the browser's current calendar date and runs every supported stream.

Health cards now depend on sync completion as well as local refresh revisions. The UI follows an already-running sync after a reload, refreshes the data on completion, and explicitly reports partial failures rather than announcing success. Automatic sync remains enabled on the user's installation.

## Live verification

The existing manual job completed at 13:24:56 Asia/Jerusalem with 21/21 intervals, 15 new records, 18 updated, 84 unchanged, and no failures. All seven checkpoints (activities, daily summaries, sleep, HRV, weight, VO₂ and supplementary data) report synced through 2026-10-21 with no errors. No duplicate live sync was started for testing.

Health visibly shows the latest night's sleep score, overnight HRV, and recorded HRV observations. Personal measurements and the browser screenshot are retained only in local QC evidence. [Local browser evidence](sleep-synced.png).

## Checks

- Sync/recovery suite: 29 tests passed, including new regressions for a late same-day sleep score after an empty result, a later correction without duplication, all streams being rechecked, the hourly freshness threshold, and no overlapping scheduled job.
- Sleep-card suite: 7 tests passed.
- Frontend TypeScript/production build and diff whitespace validation passed.

Garmin must receive the watch's data before the app can retrieve it. Synced coverage means the source was checked successfully, not that Garmin supplied every possible measurement. Older corrections outside the recent overlap still require the existing historical reconciliation option. Closed-app background synchronization remains outside this release.
