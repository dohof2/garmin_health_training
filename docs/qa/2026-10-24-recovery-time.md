# Recovery-time import and last-five-ride investigation — 24 October 2026

## Result

Authenticated read-only Garmin queries and preserved FIT decoding found no recovery-time fields for the last five activities: 23 October mountain biking, 22 October virtual ride, two mountain-bike rides on 14 October, and 11 October indoor cycling. Both `get_activity` and `get_activity_details` were checked for every ride. Training-readiness responses for all four distinct ride dates were empty; daily training status contained no recovery fields. Fourteen stored supplementary daily payloads likewise yielded no recovery snapshots. No remote Garmin data was changed.

This does not establish that the user's device has no recovery estimate; these checked Connect responses do not expose one. Historic activity `firstbeatData.results.recoveryTimeMins` values remain separate from current recovery snapshots.

## Implementation

The supplementary sync already calls and preserves training-readiness endpoints. Correcting an earlier conversation statement: endpoint collection was already present; normalization into a dedicated metric was missing.

Added normalization of the latest dated Garmin readiness recovery snapshot into `metric_readings` as `recovery_time`, unit `min`. Preserve observation timestamp, source endpoint, source recovery minutes and change phrase. Honor the installed client's documented `REACHED_ZERO` handling even when Garmin retains an old numeric assignment. Require valid dated/timezone-aware evidence, reject invalid values and never turn an empty result into zero. Full readiness snapshots take precedence over morning-only fallback. Subsequent snapshots replace the same day's normalized reading without duplicates; the original response remains in supplementary payload storage.

Normal application sync will use this normalization after the backend restarts. There are currently no account snapshots to backfill. No live countdown, frontend readiness input or formula/weight change was added. Missing current data prevents using this as a reliable readiness component today.

## Verification

27 tests passed: six recovery-time normalization/persistence tests plus existing sync-recovery and VO2 suites. Coverage includes latest snapshot selection, minutes, retained source evidence, explicit zero, missing data, malformed/undated/wrong-day inputs, morning fallback and idempotent daily updates. `git diff --check` passed. Personal FIT originals and credentials remain in ignored local storage.
