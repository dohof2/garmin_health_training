# Garmin publication and readiness verification — 21 October 2026

## Delivered

- Send to Garmin from a selected active session, the next seven days, or an independent today's suggestion. Calendar scheduling is optional; preview displays account, dates/timezone, instructions and exact targets before approval.
- Pure cycling/running conversion using the pinned garminconnect 0.3.17 models. Timed steps, repetitions, rests and total duration are checked. Only prescribed watts/bpm become numeric targets. Effort-based steps retain effort in notes, with an explicit open-target warning. Strength and other unverified sport mappings are blocked with reasons.
- Durable publication jobs, immutable approved snapshots and account/revision checks. Create and schedule are tracked separately. Duplicate approvals and overlapping jobs cannot duplicate a workout. Uncertain create/schedule timeouts require read-back reconciliation, never blind repeats. Remote edits produce a conflict. Backup receipts are retained; restored pending jobs never resume writes automatically.
- Managed published workouts can be adjusted locally by the trainer or moved using the schedule control. They show Garmin update needed until a reviewed update/reschedule/unschedule is verified. Skipping a workout can remove its app-owned calendar entry while retaining the Garmin library workout. Plan deletion does not delete Garmin resources.
- Fixed an actual active-plan loading failure: fractional history-derived duration ceilings are floored to whole minutes within the limit before template validation.
- Fixed readiness calculation failures during concurrent plan review/sync. Existing audit-cache rows are read without a writer lock. If the database writer is occupied, a fresh valid result is returned and the optional cache save is deferred; later reads can persist it. Scores and data sufficiency rules are unchanged.

## Live browser pilot

The existing saved steady cycling workout for **21 October 2026**, duration **60 minutes**, was selected and previewed. One explicit browser approval created it in Garmin Connect and scheduled it for that date in Asia/Jerusalem. Backend read-back matched the approved steps, targets and calendar workout/date. The UI showed **published / verified**, and a durable receipt survived navigation.

Only this one workout was sent in the live pilot. No remote cleanup/deletion or batch send was performed. Device delivery and execution need a compatible-device sync/check by the user. Running publication, remote updates and calendar removals were tested with an isolated provider, not on the real account.

![Verified publication](garmin-verified.png)

## Readiness browser check

Dashboard refresh completed and displayed the measured-data status separately from tomorrow's forecast. The current stored data lacks a completed sleep record/score and enough current HRV evidence for a measured readiness score. The display correctly says insufficient data; it does not substitute the forecast or invent a number. The previous database-lock error no longer prevents returning the result.

## Automated checks

Passed focused suites:

- `test_garmin_publication.py`: 18 methods, including all cycling kinds, running, target/duration rejection, preview immutability, duplicate approval, overlapping jobs, account/expiry/staleness, ambiguous create and schedule, definite rate-limit retry, same-ID updates, interrupted read-back after update, remote conflicts, rescheduling, unscheduling, standalone workouts, crash recovery and backup behavior.
- `test_readiness.py`: 31 methods, including an actual held SQLite writer lock, deferred persistence, stable existing cache IDs, late corrections and missing-data behavior.
- `test_training_adjustments.py`: 8 methods, including the 50 casual chat requests and actual saves in disposable databases.
- `test_trainer_section_qc.py`: 10 methods; `test_advanced_cycling.py`: 4; `test_exports.py`: 5.
- Frontend TypeScript/production build and `git diff --check` passed.

These are focused checks, not a claim that every historical repository suite passes. No commit or push was performed for this work.

## Remaining validation

Strength exercise mappings; actual device compatibility/delivery; live running and update/reschedule pilots; official-partner adapter and native remote training plans. Unknown outcomes that cannot be matched by ownership and payload remain unresolved for manual Garmin review. Restored pending jobs are intentionally held for reconciliation rather than resumed automatically.
