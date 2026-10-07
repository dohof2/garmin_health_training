# Garmin Export Inventory

Inspection date: 6 October 2026
Source: `data/imports/Garmin data.zip`
Handling: read-only inspection; the archive was not extracted or modified

## Integrity and safety

| Check | Result |
|---|---|
| Archive size | 200,606,293 bytes (about 191 MiB) |
| SHA-256 | `123d1083c5f783c2d0d0a821d7ee807f448aebbddb08a2eecb724e30e4fd393c` |
| Outer archive entries | 325 total: 298 files and 27 directories |
| Outer expanded size | 291,092,029 bytes |
| Outer compression ratio | 1.45x |
| CRC test | Passed; no compressed-data errors |
| Unsafe absolute or parent paths | 0 |
| Symbolic links | 0 |
| JSON parsing | 285 of 285 files parsed successfully |
| Git protection | Covered by the repository's `data/` ignore rule |

The export contains eight nested ZIP archives. Their combined expanded size is
368,862,840 bytes, their highest observed compression ratio is 9.70x, and none
contains an unsafe path or symbolic link.

## Data inventory

| Data category | Observed records or files | Observed coverage |
|---|---:|---|
| Summarized activities | 1,054 unique activities | 30 January 2012 to 29 September 2026 UTC |
| Daily summaries | 3,050 unique dates | 1 January 2006 to 30 September 2026 |
| Sleep | 2,908 unique dates | 20 July 2018 to 30 September 2026 |
| Hydration | 904 records | 11 April 2012 to 29 September 2026 |
| Abnormal-heart-rate events | 49 records | 29 December 2022 to 21 September 2026 |
| Nutrition | 291 records | 1 December 2025 to 30 September 2026 |
| FIT files in nested archives | 55,448 files | Date coverage must be read from FIT metadata during import |
| GPX files in nested archives | 6 files | Date coverage must be read during import |
| TCX files in nested archives | 1 file | Date coverage must be read during import |

The export also contains training status/load, VO2 max, race predictions,
cycling ability, heat/altitude acclimation, routes, workouts, training plans,
gear, devices, LiveTrack, Tacx, social, profile, and account-related material.
Account/profile material is private source data and must not be written to logs
or committed to Git.

## Activity summary

The largest activity groups are cycling (490), mountain biking (330), walking
(76), running (72), and strength training (27). The summarized activity IDs are
all unique within the export.

## Import implications

- Keep the original ZIP immutable and use its SHA-256 value as source provenance.
- Inventory nested archives before extraction and enforce path, file-count,
  expanded-size, per-file-size, recursion-depth, and compression-ratio limits.
- Start normalization with summarized activities and daily summaries because
  they provide compact, directly parseable historical coverage.
- Parse FIT files incrementally rather than loading all 55,448 files into memory.
- Reconcile summarized activities with FIT/GPX/TCX detail using stable Garmin
  activity IDs where present and explicit fallback matching rules otherwise.
- Treat missing dates as missing data, not zero values.
- Exclude profile, account, device, location, and consent payloads from routine
  application logs and AI context.

Importer update, 7 October 2026: the ignored local SQLite database contains
1,058 Garmin activities, 29,888 daily metrics, 22,198 sleep metrics, 2,912,230
unique activity-detail samples, and 3,706,008 compact health samples. Garmin's
official Python FIT SDK decoded all 55,448 FIT files with zero failures. The
import reconciled 1,045 physical activity FIT files (including one duplicate
copy and four valid FIT-only activities), all six GPX files and the one TCX
file. It also identified and tracked 20,696 FIT files containing validated
heart-rate, stress, or respiration values. Stored health coverage spans 20 July
2018 through 2 October 2026 UTC: 3,068,901 heart-rate, 2,382,042 stress, and
2,329,261 respiration values across the timestamped rows. Repeat runs write
zero rows. A subsequent wellness JSON stage normalized 891 unique hydration
events from 904 source rows (13 repeated across overlapping files) and all 49
abnormal-heart-rate events. Its 40 source files are checkpointed with zero
failures, and private profile/device identifiers are not copied into normalized
tables. SQLite integrity and foreign-key checks pass. The supplied export has
no CSV files; remaining in-scope JSON categories are covered by the final stage below.
The Garmin nutrition file was also imported into a separate daily-summary table:
291 dates from 1 December 2025 through 30 September 2026, with calorie values on
22 days and goals on 290 days. The source contains no meal or macronutrient
detail, so these rows remain distinct from future user-entered meals.

Final import update, 7 October 2026: the extended stage imported 26,143 unique
records across 48 training, biometric, workout, route, gear, goal, Golf, and
Tacx categories. Its 144 files completed without failure. Combined with 121
files handled by dedicated importers and 33 explicitly excluded private
administrative files, all 298 outer files are classified and none are
unsupported. See `import-coverage.md` for the full accounting and exclusions.
