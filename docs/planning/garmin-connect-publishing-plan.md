# Garmin Connect workout publishing — execution plan

Status: first personal-client release implemented 21 October 2026 following the user's instruction to start execution. The installed client remains `garminconnect==0.3.17`. One saved 60-minute cycling workout was deliberately published and scheduled for 21 October through the browser approval flow; remote workout instructions and calendar entry were read back and verified. Device delivery is unverified. Running conversion, batching, updates, rescheduling and unscheduling have isolated-provider coverage; strength is blocked pending exercise mappings. See [execution verification](../qa/2026-10-21-garmin-publication/REPORT.md). The remaining sections retain the broader rollout plan; official-partner access, native full-plan publication and device-specific validation are not complete.

## Recommended first delivery

For this personal application, propose the already installed private-client connection as the first adapter, with its unofficial status visible. Official enterprise Training API access is a separate approved integration, not a prerequisite we can assume the user has. Do not upgrade the library as part of feasibility work. Keep the provider boundary so an official adapter can replace it later.

Deliver in this order:

1. Inspect the pinned client's actual payload models and validate pure mappings for cycling warm-up, steady base, recovery, tempo/threshold/VO₂, sprint and anaerobic sessions. Preserve interval order, recovery, repetitions, total duration and calibrated targets. Preserve effort-based guidance honestly when exact watt targets are absent. Block a workout if the adapter cannot faithfully represent it.
2. Add durable publication jobs, immutable approved session revisions, Garmin workout/calendar IDs, account binding and recovery from partial success. Test mapping and retries against a fake provider before exposing real writes.
3. Add **Send to Garmin** to the selected active-plan session and today's workout preview. Show the workout and calendar date, then offer **Send workout only** or **Send and schedule**. Rest days are not workouts to upload. A saved active plan is not required for a standalone suggestion; store an immutable publication snapshot.
4. Run one deliberately selected cycling pilot after a publishing instruction. Read the workout back from Connect, verify its steps/targets, and verify the calendar date if selected. Confirm delivery separately on the user's actual compatible cycling computer/watch; obtain the device model before promising support. Never equate a successful API response with successful device execution.
5. Add **Send next 7 days** to the active-plan card once the single-session pilot passes. Preview concrete selected sessions, omit rest/completed/skipped sessions and show unsupported sports individually. Publish the materialized week, not speculative sessions for the entire multiweek roadmap.
6. Integrate conversational adjustments: saving a daily/weekly change updates local sessions and the **Next 7 days** card. If a session was already published, show **Garmin update needed** and offer a reviewed remote update/reschedule/unschedule. Do not label the revised week synced until the remote change is read back. Reuse the existing Garmin identity instead of creating a duplicate. Extend the current published-edit guards only through this explicit workflow; they presently block ordinary edits, including casual adaptations.
7. Add running and then strength after sport-specific contract and device checks. Strength needs exact exercise mapping, sets, reps, rests and load units; never silently convert an unsupported exercise to a different movement.

Completion criteria: exact workout step/duration/target parity; correct local calendar date; retry and double-click without duplicates; created-but-not-scheduled recovery; expired authentication and unknown-timeout handling; stale local/remote revision protection; saved trainer changes reflected in the local seven-day card; separately verified remote updates; clear Connect-versus-device status. The 50 casual-adjustment checks validate local behavior only and are not evidence of Garmin publishing readiness.

## Feasibility and integration choice

Garmin's official [Training API](https://developer.garmin.com/gc-developer-program/training-api/) explicitly supports publishing structured workouts and training plans to the Connect calendar. This is the supported platform route, rather than uploading recorded activities. The [program FAQ](https://developer.garmin.com/gc-developer-program/program-faq/) limits access to business/enterprise applications subject to approval, describes OAuth2 and states no general licensing/maintenance fee. Personal access is not guaranteed. The [official OAuth2 PKCE specification](https://developerportal.garmin.com/sites/default/files/OAuth2PKCE.pdf) describes user consent and checking granted Workout Import permission. Approved API reference documentation is needed before asserting exact remote endpoint schemas, limits, native-plan support or update semantics.

The app currently uses the unofficial `garminconnect` Python client, installed version 0.3.17, and protected locally persisted Garmin login/session tokens through `backend/app/garmin_connection.py`. Read-only class introspection confirms `upload_workout`, typed cycling/running/strength uploads, `schedule_workout`, `get_workout_by_id`, `get_workouts`, `update_workout`, `delete_workout`, `get_scheduled_workouts`, `get_scheduled_workout_by_id`, `unschedule_workout`, and `push_workout_to_device`. Presence proves a possible personal integration route, not account permission, stability or successful writes. Its [maintainer repository](https://github.com/cyberjunky/python-garminconnect) is the primary source for this unofficial client. No new library upgrade should be assumed.

Recommendation: one provider abstraction with the official approved Training API preferred for a distributable product; optionally implement the existing private-client adapter for this personal app only after explicit route selection. Label private access honestly, pin and contract-test it, isolate it from inbound sync and disable writes on unknown schemas/auth failures. Existing private session tokens cannot be substituted for official partner OAuth credentials.

A FIT workout file and Garmin Connect's website recorded-activity import are different workflows. [Official FIT workout specification](https://developer.garmin.com/fit/articles/file-types/workout.html) describes structured instructions; [Garmin activity import help](https://support.garmin.com/en-CA/?faq=Ht3ZP52Kju075uKvqTqu99) covers completed recordings. Neither establishes arbitrary workout-file import into Connect. This plan publishes through authenticated workout APIs instead.

## User experience and publication scope

1. A generated workout preview offers **Publish to Garmin Connect**. A saved plan offers **Publish workouts…**, initially selecting the next seven days. A batch can choose a supported date range and explicit sessions. Rest days are shown for context, not uploaded as workouts.
2. Preview displays account identity, selected sessions, dates/timezone, sport, repetitions, duration, targets and provenance, notes/strength mappings, and whether each action creates, schedules, updates or leaves a workout unchanged. Unsupported targets/exercises block that session with a reason; no silent stripping.
3. Separate choices: save in workout library only, or also schedule on calendar. Device delivery is a separate optional later capability, not implied by calendar success. State **Published to Connect; device sync pending/unknown** unless independently observed. Garmin's [send-workout guidance](https://support.garmin.com/en-SG/?faq=Oyqt6jUjOF8L1Rnuc9Sms8) distinguishes Connect workouts and compatible-device synchronization.
4. One explicit **Approve publication** submits the reviewed immutable batch. Generating a suggestion, activating/editing the local plan, syncing, or saying conversational yes never publishes. A suggestion can publish without becoming the active plan; keep a durable immutable local publication snapshot first.
5. Show progress and per-session statuses. Retry failed/unconfirmed items only. Reopen the outcome after reload. Cancellation before submission has no external effect; cancelling an in-progress batch only stops unstarted operations and does not pretend to undo completed writes.
6. A multiweek roadmap is phase guidance, not fully prescribed sessions. Publish only concretely generated and reviewed workouts; do not expand a whole roadmap using invented future readiness. Offer rolling reviewed seven-day batches. Native remote training-plan publication is a later adapter capability after official reference verification, not a promise of the private client's read-plan methods.

## Existing foundation and source boundaries

Reuse canonical `planned_workouts`, `training_plans`, active program and revision history. Existing `garmin_workout_id`/`publish_status` and published-edit guards in `training.py` already reserve the T8 publication boundary; consult T8 in the main planning/task documents before implementation. Keep inbound activity IDs separate from outgoing workout and schedule IDs. Remote publication status must not overwrite completion feedback or imply activity completion.

Add focused `garmin_training_publish.py` orchestration and provider adapters; avoid write methods on broad AI tools. Existing assistant can request a preview only. Add one reusable UI review dialog invoked from selected workout, today suggestion, candidate preview and active-plan batch actions. Existing local approvals and remote approval remain separate.

## Proposed local API contracts

These are application endpoints, not claimed Garmin endpoint paths.

- `GET /api/training/publication/capabilities`: adapter, account fingerprint, authorized scope, supported sports/targets/scheduling, unavailable reasons; no remote writes.
- `POST /api/training/publication/preview`: selected local IDs/revisions or immutable validated preview snapshots, scheduling choices and browser timezone. Returns normalized actions, warnings, payload hashes, expected revisions/account binding and expiring preview token. Remote reads may validate existing mappings; preview never writes Garmin.
- `POST /api/training/publication/approve`: preview token, idempotency key and exact approval scope; returns durable job ID. Revalidate revisions/account/capability, then transactionally create receipt/job/outbox before network writes.
- `GET /api/training/publication/jobs/{id}`: batch/item status and recoverable error, safe remote IDs/links.
- `POST /api/training/publication/jobs/{id}/retry`: unresolved items, reconciliation first, same identities.
- Separate reviewed update/reschedule/unschedule/delete previews and approval operations. Never use a generic arbitrary Garmin HTTP proxy.

## Persistence, concurrency and reconciliation

Choose next migration only after inspecting current tree. Add publication jobs/items with account+provider identity, local workout/snapshot identity, local revision, canonical payload hash, approval receipt, remote workout ID, remote calendar/schedule ID, intended local date/timezone, timestamps, retries and sanitized error. Unique constraints prevent duplicate mapping by account/local snapshot/action revision. Extend backups/export/restore; restored jobs must not automatically resume external writes until account rematch and reconciliation.

Remote create and schedule are not one SQLite transaction. Item states: queued → creating → created → scheduling → verified; plus failed/reconciling/conflict. Persist remote create ID before scheduling. A scheduling failure leaves **created, not scheduled**, not generic failure followed by another create. Lock per account/workout; serialize mutation for the same item. Batches use bounded concurrency respecting verified provider limits.

Never blindly retry an ambiguous create timeout. If API supports idempotency, use its documented mechanism; otherwise reconcile using returned IDs or a provider-supported application marker and stored hashes. Never deduplicate by title/date alone. If ownership cannot be established, show **Outcome unknown—review in Garmin** and require reconciliation rather than multiplying workouts. Recover interrupted jobs on startup through read-only reconciliation before any write.

Revisions/account changes after preview invalidate approval. Repeated identical approval returns original job. Reuse of an idempotency key with different payload rejects. Updating local health/FTP after approval does not silently modify remote targets. Editing a published workout previews a delta and checks remote content/version where supported. Preserve user remote edits as a conflict; absent ETags compare fetched canonical content hash. Track library and calendar operations separately.

## Mapping and safety requirements

Map only verified remote schema values: sport; warm-up/work/recovery/cooldown; timed/distance/lap termination; repetitions with ordering and total-duration parity; absolute watts/bpm or documented relative zones; effort guidance as notes/open target only if faithfully explained. Strength requires valid exercise catalog IDs, sets/reps/rest and load units; unmapped exercises block instead of substituting a different movement. Include target calibration provenance in review. Validate limits, finite values, units, allowed names, dates, timezone/DST and overlaps; do not invent device support.

Deletion/unscheduling are separate explicit actions. Delete only app-owned mapped resources and warn if referenced by other schedules. No bulk delete of account workouts and no deleting manually created entries by matching a name. Local cancellation/plan replacement does not automatically delete Garmin entries. Remote disappearance is reconciliation state, not permission to recreate automatically.

Keep official client secrets, tokens, PKCE verifier and private session tokens server-side in existing protected storage or OS secret store. Never send secrets to browser/AI context or logs. Refresh/revocation is adapter-specific. Handle expired credentials/MFA/consent, 401/403, rate limits, validation errors and outages explicitly. No hidden login or credential fallback between providers.

## Execution milestones and acceptance

1. Decide provider route and verify official approval/capabilities or private account write eligibility. Inspect pinned client source and synthetic payload contracts. No live write needed for this stage.
2. Implement pure mapping fixtures plus durable outbox/migrations and backup roundtrip. Test unknown fields/exercises, repetitions, units, target parity and date boundaries.
3. Add read-only preview and UI approval with stale revisions/account switch/cancel tests.
4. Implement fake-provider jobs: create success/schedule failure, timeout with unknown outcome, crash after create, repeated/concurrent approval, retries, remote edit conflict, revoked consent, rate limit and partial batch recovery.
5. Add update/reschedule/unschedule/delete with ownership and fresh approval tests. Preserve completed history and local plan behavior.
6. Full backend tests, frontend build, browser keyboard/mobile/report validation. On explicit user instruction, controlled live pilot: one clearly named disposable workout, read-back verification, optional scheduled date review, then separately approved cleanup. No live pilot authorized by this document.
7. Roll out batch publication after single-workout pilot passes. Native full-plan publishing requires separately verified official API contract. Report Connect library/calendar confirmation separately from actual device synchronization.

## Stopped FIT work state

The superseded FIT task produced no backend files, endpoints or tests. Frontend imports/buttons were removed from `ActiveTrainingPlan.tsx`, `TrainingPanel.tsx`, `TrainingCoachPanel.tsx` and `TodayWorkout.tsx`, preserving existing functionality. The unreferenced `WorkoutDownload.tsx` prototype and inert download CSS were subsequently removed before committing; no unsupported download controls remain. Frontend build and whitespace checks passed after removal. No FIT download, remote publishing, commit or deployment is part of this planning task.
