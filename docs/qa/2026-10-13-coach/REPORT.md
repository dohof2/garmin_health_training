# Training coach remediation verification — 13 October 2026

Implemented the authorized remediation plan against the original 12 October findings. Changes are local and uncommitted.

## Evidence

- 413 backend tests pass; frontend typecheck, production build and git diff whitespace check pass.
- 24 dedicated remediation tests exercise the real tool dispatcher, canonical active-plan persistence, atomic setup saves, pause/cancel, changing events and overlapping events, short-term recovery protection, calibrated power/HR/RPE prescriptions, exact lap totals, long-session variety, mixed sport roles, primary strength, actual strength-set feedback and backup/restore.
- Five connected-model cases used invented health/training records in isolated databases. Final responses and tool traces: [live-results.json](live-results.json). Four formerly crashing paths now complete. Confirmed FTP produces numeric timed laps; unknown calibration prompts questions. Strength-primary creates a reviewable setup proposal. A surprise event creates an event proposal and explains that saving reconciles the schedule. No invented successful save.
- Browser QA on an isolated local database verified the agent-led page, timed lap tables, upcoming event editing, canonical scheduled-event updates, pause and resume, and cancellation flow. A cancellation label issue found during QA was repaired with an explicit cancelled database status and covered by automated tests.

## Result by requested capability

| Capability | Implementation and verification |
| --- | --- |
| Long workouts of different lengths/types | Long endurance, climbing endurance and tempo; duration and exact lap-total tests, including over two hours |
| Persistent active plan | Canonical stored program; direction/calibration/events update atomically; rolling seven days and post-event continuation |
| Pause/cancel | Persisted lifecycle guards, idempotent operations, cancelled future workouts |
| Different upcoming events/event plans | Stable event identity, race/distance/elevation, preparation blocks, event-specific scheduling and recovery protection |
| Surprise events/user changes | Reviewed setup/adjustment proposals reconcile existing future workouts and weekly budget; impossible conflicts remain visible |
| Cycling plus strength | Explicit primary/secondary roles and fitness/cycling/strength purpose; equipment and capability clarification |
| Power/HR targets | Accessible meter plus dated FTP; separately confirmed HR zones; effort fallback when calibration is missing/stale |
| Past difficulty/feedback | Sport-specific history, recorded intensity/load/training effect, readiness protection, completed tolerance and actual strength sets |
| Usable workout output | Named timed laps, repetitions, target ranges, rest and strength instructions |

## Practical limits

Training and recovery rules remain provisional engineering heuristics, not validated physiological capacity estimates. Missing biological data is disclosed. Numeric HR targets require confirmed zones; FTP alone never supplies HR. Fixed events can exceed available time and then require user resolution. Conservative recovery changes are not automatically undone when an event moves. Garmin-device publishing is outside this implementation. Connected-model verification is five scenarios, not an exhaustive guarantee of every conversational wording.

## Readiness refresh follow-up

Today and tomorrow were already fetched together. Returning to an app left open did not refresh them. ReadinessCard now refreshes both on focus/visibility return, rejects cached fetches, discards aborted results, and tracks local-day changes including while viewing historical data. Existing sync/manual/settings/morning-cutoff refresh triggers continue to refresh both. Forecast assumptions remain visible: a fresh projection can still differ substantially from today’s measured score.
