# Garmin Live Data Coverage

Last verified: 10 October 2026

This document distinguishes records refreshed from Garmin Connect from records that
currently remain archive-only. It describes the integration implemented by this app;
it is not a claim that Garmin exposes every account field through a supported public
consumer API.

## Live, checkpointed data

Each live data type has its own durable checkpoint. A normal synchronization catches
every unchecked date, then rechecks the latest three days. Successfully queried empty
days are recorded separately from unchecked dates.

| Data type | Live fields | Detail and limits | Verified through |
|---|---|---|---|
| Activities | Type, name, start time, timezone, duration, distance, calories, elevation | Full vendor summaries and decoded FIT session summaries are retained; explicit training load/effect and power/HR summary fields are normalized. FIT is downloaded when summary recovery is needed or the source changes; GPS, elevation, heart rate, cadence, power, and speed samples are retained | 10 October 2026 |
| Daily summary | Steps, distance, total/active/resting calories, resting/minimum/maximum heart rate, moderate/vigorous intensity minutes, stress, SpO₂, waking respiration, Body Battery, floors, daily goals, and active/highly-active/sedentary duration | Missing fields remain absent rather than becoming zero; full queried responses are retained locally | 10 October 2026 |
| Sleep | Total/deep/light/REM/awake/unmeasurable duration, score, stress, respiration, resting heart rate, average overnight HRV, and Body Battery change | Scalar nightly summaries are normalized; full queried responses, including available epoch arrays, are retained locally | 10 October 2026 |
| HRV | Last-night average, last-night five-minute high, and seven-day average | 1,434 nightly averages from 25 August 2022 through 10 October 2026. Historical range responses retain summaries/baselines; recent daily queries also retain detailed readings locally, without normalizing them into additional nights | 10 October 2026 |
| Weight/body composition | Weight, BMI, body fat, body water, bone mass, and muscle mass when recorded | Empty query days are tracked; the account currently has one live-range weight record, dated 29 September 2026 | 10 October 2026 |

The 10 October sync repair recovered omitted FIT session summaries and historical HRV. All five streams then completed a normal sync through 10 October without failures. See `sync-recovery-verification.md`. The earlier 28 September–8 October historical reconciliation completed without failures.
It removed all archive/live duplicate daily metrics created by the earlier identifier
scheme. Database integrity and foreign-key checks pass.

## Available from the imported archive

The imported archive remains the historical source for records not refreshed by the
current live pipeline. These include hydration events, abnormal-heart-rate alerts,
nutrition summaries, detailed monitoring FIT history, VO₂ max history, acute training
load, training history, fitness age, race predictions, cycling ability, heat/altitude
acclimation, workouts, routes/courses, gear, goals, and other classified account data.

Archive-only does not mean the data is unavailable to the historical assistant. It
means newer changes in that category will not appear until a parser is connected to a
corresponding live endpoint or a newer account export is imported.

## Deliberate exclusions and limitations

- Account administration, social data, device registration, and location-management
  records are excluded from normalized storage.
- Garmin Connect does not expose a reliable general `updated-since` query through the
  library used here. Recent overlap plus user-selectable historical reconciliation is
  used instead.
- Deletion is applied only when Garmin explicitly reports it; an empty or failed
  response is never treated as deletion.
- Detailed sleep, HRV, Body Battery, respiration, and SpO₂ epoch arrays are not yet
  normalized by live sync. Their daily/nightly scalar summaries are supported.
- Workout publication is a separate, deliberate write workflow planned for T8 and is
  not part of this read-only synchronization coverage.
