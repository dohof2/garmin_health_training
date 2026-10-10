# Sync recovery verification

Verified 10 October 2026 against the saved Garmin session and local database.

## Causes and fixes

- Live activity normalization discarded original summary fields, including exercise load. Sync now retrieves the per-activity detail summary, preserves its source payload, and normalizes explicit load, training effect, power, and heart-rate fields with source provenance.
- FIT ingestion retained record samples but omitted session summaries. Both live and archive ingestion now preserve decoded sessions and normalize supported scalar fields. Existing sensor samples no longer prevent summary recovery; a successful decode is versioned to avoid perpetual downloads. Multisport sessions are preserved individually rather than treating the first session as the entire activity.
- The HRV stream began recently without querying older history. It now bootstraps from the oldest known sleep date, queries history in bounded ranges, and durably resumes interrupted backfill independently of recent coverage. Valid empty responses are recorded as queried empty days; malformed/error responses do not advance coverage.
- Queried daily, sleep, HRV, weight, and activity responses are preserved locally, with known account/device identity fields removed. Available epoch arrays survive even when only scalar values are normalized. JSON and backups retain the new data; date-filtered activity metrics follow their parent activity dates.

## Real recovery

A SQLite backup was saved before recovery at the ignored local path `data/backups/before-sync-repair-20261010-091706.sqlite3`. The original archive was unchanged.

| Evidence | Before | After |
|---|---:|---:|
| Activities | 1,065 | 1,065 |
| Sensor samples | 2,937,459 | 2,937,459 |
| Metric readings | 52,514 | 56,843 |
| Nightly HRV averages | 12 | 1,434 |
| Explicit activity exercise loads | 718 archive payloads, no normalized table | 725 normalized activities |
| October workouts with load | 0 of 4 | 4 of 4 |

Recovered 1,045 preserved activity FIT summaries with zero decoder failures, without reimporting samples. Retrieved HRV history covers 25 August 2022–10 October 2026; vendor weekly averages have 1,461 observations. Sleep-derived HRV overlaps nightly HRV and is not counted as independent nights.

Activity reconciliation refreshed 13 records. Repeating it produced 13 unchanged activities, zero downloads, and zero new activities. A subsequent normal sync completed across all five streams through 10 October without failures (36 created metrics, 15 updated, 103 unchanged). Every checkpoint is `synced`, with no pending HRV backfill. SQLite quick-check returned `ok`; foreign-key checks returned no violations. Counts of local goals/profile/maintenance/equipment records were unchanged.

## Automated verification and remaining limits

`make test`: 135 backend tests plus TypeScript checks pass. `make build`: production frontend build passes. New regression cases cover payload preservation, summary/FIT precedence, existing-sample recovery, repeat sync, absent/invalid numbers, multisport, historical bootstrap, interrupted backfill, explicit empty server responses, failed coverage advancement, stale cache reset, date/ID mismatch, portable export filtering, and backup restoration.

History without explicit Garmin/FIT load remains missing rather than receiving inferred zero. Garmin returned no HRV for some queried dates; successful coverage does not imply a measurement exists each night. Historical range queries preserve HRV summaries, while recent daily queries retain detailed readings. Other account categories remain archive-only as documented in `live-data-coverage.md`. These fixes recover data; they do not implement or validate the proposed readiness algorithm.
