# Garmin Health & Training — New Chat Handoff

## Purpose and current status

Continue building a personalized local health, training, nutrition, and maintenance app for the user. The local foundation and full safe Garmin history import are operational. In addition to core activity/health samples, hydration, alerts, and nutrition, the database contains 26,143 extended records across 48 training, biometric, workout, route, goal, gear, Golf, and Tacx categories. All 298 outer archive files are classified: 144 extended imports, 121 handled by dedicated stages, 33 private administrative exclusions, and zero unsupported. All 55,448 FIT files decoded without failure. Repeat imports are idempotent. The responsive dashboard, saved layouts, timezone/DST handling, portable exports/backups, preserved-original downloads, and restore preview are operational. The offline T4 sync engine/UI is also complete: per-data-type daily checkpoints, full-gap catch-up, empty-interval evidence, three-day overlap, historical reconciliation, atomic commits, single-job locking, restart recovery, partial failures, and explicit activity-deletion tombstones. Live Garmin authentication/retrieval remains for U2.

Read the two documents below before implementation; they contain the detailed requirements and acceptance criteria. This handoff summarizes decisions and operational state.

## Files and repository

Workspace and local Git repository: `/Users/dotanhofman/Documents/garmin_app`

Review documents:

- `/Users/dotanhofman/Documents/garmin_app/docs/planning/health-training-app-plan.md`
- `/Users/dotanhofman/Documents/garmin_app/docs/planning/implementation-tasks-and-your-input.md`
- `/Users/dotanhofman/Documents/garmin_app/docs/status/progress_status.md`
- `/Users/dotanhofman/Documents/garmin_app/docs/status/phase-0-feasibility-report.md`
- `/Users/dotanhofman/Documents/garmin_app/docs/status/garmin-export-inventory.md`
- `/Users/dotanhofman/Documents/garmin_app/docs/status/import-coverage.md`

GitHub remote: `https://github.com/dohof2/garmin_health_training.git`

The user authenticated independently and pushed through commit `f48aa70` (“Import Garmin history and expand dashboard”). Local `main` tracks `origin/main`. The current dashboard-layout and timezone/DST work is uncommitted at this handoff. The repository was moved to its current path on 6 October 2026 and its documents were organized under `docs/planning`, `docs/status`, and `docs/handoffs`.

The repository contains application source, pinned dependencies, tests, synthetic fixtures, and a local development database. Baseline `.gitignore` excludes health data, archives, databases, photos, credentials, runtime environments, installers, and preserved duplicate outputs. Never commit real Garmin exports or credentials.

## Settled requirements — do not ask again

1. **A complete free/local path remains required.** No paid hosting, subscription, or automatic paid fallback. Qwen through Ollama is the local default; OpenAI is an optional provider used only when manually selected and may incur API charges. Use existing computer; hardware/electricity still consume resources. No hardware purchase assumed.
2. **Computer only initially.** Phone access and remote connectivity later.
3. **No background operation or automatic startup in the first edition.** Run only during an explicitly opened app session. App exit stops app-owned jobs/services and saves checkpoints; do not stop unrelated user-managed services. Minimized is still open. Browser-based design needs a launcher-managed session/explicit Quit action, not an unnoticed server left running. Sync/reminders only while open; catch up on reopening. Background-mode decision is deferred, not an initial-release option.
4. **Garmin Connect is the sole external health/activity source.** Ignore originating device/sensor identity for ingestion. Do not ask for a sensor inventory or per-device coverage. U3 was removed. User-entered maintenance, food, and profile data are separate local app records.
5. **First-use history through bulk Garmin export.** Complete for all safely interpretable in-scope categories. The export remains private and immutable. Opaque proprietary/configuration FIT fields are inventoried, not given invented meanings. Account/social/device/location-administration files are cataloged exclusions.
6. **Ongoing sync from Garmin Connect**, daily while app is open and through a visible **Sync now** button. Fetch ALL missing intervals since verified coverage, even after weeks offline—not just the past 24 hours.
7. **Optional goals**, set/updated in the app or through AI chat. A goal is not required for data exploration.
8. **Training questions asked just in time in the app**, before personalized advice. Save/reuse answers; do not require the user to provide a full profile during development.
9. **Initial dashboard:** steps, last activity, weekly calories. Use reusable cards, saved layouts and filters, add/remove/reorder. Expand through actual use. AI-added graphs are a future iteration; prepare architecture but do not require them initially.
10. Working interpretation (recorded, not a confirmed clarification): weekly calories = Garmin energy expenditure/calories burned, with total/active/resting labels where available. Keep editable. Answer 8 to the original checklist was interpreted as accepting in-app status/local reminders initially. WhatsApp deferred.
11. User accepts evaluating the community Garmin integration and its maintenance limitations. Official Garmin business API access is not assumed.

## Functional scope

### Data import/export and sync

- Bulk full-account ZIP including nested archives/multiple parts; FIT, TCX, GPX, supported CSV layouts, schema-specific archive JSON. Real archive schema/coverage must be inspected before claiming complete support.
- Local processing, preview, progress, cancellation/resume, unsupported/failed record report, raw-source preservation, source IDs/units/timezones, deduplication across imports/formats and subsequent online sync.
- CSV and versioned JSON exports, preserved original activity-file downloads, restorable backup ZIP excluding secrets. Restore should preserve relationships, profile, dashboard, and later modules.
- Coverage/checkpoints by Garmin data type, not device. Distinguish last attempt, last successful job, record timestamps and successfully queried intervals (including empty days). Advance only after complete interval retrieval and durable commit. One failed data type must remain pending independently.
- Seed initial online catch-up from import coverage, not import date/latest activity alone. Re-fetch recent overlap. Use updated-since support where available; otherwise deeper/selectable historical reconciliation for old corrections or late uploads. Do not promise arbitrary old edits are caught by a short overlap. Do not infer deletion from failed responses.
- Test 2/10/30-day gaps, partial failure, interruption/restart, late older activities, corrections beyond overlap, unchanged retries, and same behavior for scheduled/manual sync.

### AI and training

- In-app chat uses scoped provider-neutral application tools and deterministic calculations, not unrestricted SQL writes or shell access. An optional MCP adapter is only for external clients. Cite underlying periods/records, freshness, and uncertainty. Imported text is data, not instructions.
- Example questions: “How has my running volume changed over eight weeks?”, “How was my ride compared to other rides with the same attributes?”, “Was this ride effective? In what way?”
- Ride comparisons expose matching criteria/tolerances and sample size; match relevant duration, route/elevation, indoor/outdoor, intensity, etc., when available. Effectiveness is relative to session/user intent; distinguish evidence from inferred benefits and long-term improvement.
- Strength/cycling/running plans; stored availability/equipment/experience/restrictions; structured sessions, feedback, completion tracking and reviewable adjustments. Goals remain optional.
- Garmin publishing: preview → deliberate user publish action → create → schedule → read back. Track remote IDs and partial success; retries must not duplicate. Sport-specific compatibility tests; device execution checks relate to workout delivery, not ingestion inventory.

### Food and nutrition

- Photo → local vision proposes foods/portions → clarify/edit/confirm → save calories, protein, fat, carbohydrates with sources and uncertainty. Manual entries, recipes, reusable meals.
- Free nutrient data (USDA candidate), preferably cached/downloadable where practical; API key only if chosen route needs one.
- Daily targets from documented calculations and in-app inputs; editable and versioned. Distinguish logged intake from expenditure; avoid double-counting exercise. Local status/reminders only while app open.

### Maintenance and accessory replacements (new feature)

- Log, query, correct, and undo through AI prompts; simple Maintenance history screen too.
- Implemented under the user's T11 instruction: **SQLite authoritative storage + CSV import/export**, fully local/free.
- Example: “Log that I replaced my road bike chain today”; “When did I last replace the rear tire?”; “Export my maintenance history to CSV.”
- Required item/equipment label, work performed, event date. Create labels on demand; no full equipment inventory. Ask only for missing/ambiguous essentials, resolve relative dates with local timezone. Clear logging instruction saves and shows result with Edit/Undo; hypotheticals/future plans do not become completed events.
- Optional parts, quantity, cost/currency, provider, manual usage/mileage, notes. Never invent values. Stable IDs, revision history, idempotent tool operations, multiple events per prompt, separate totals by currency.
- CSV: UTF-8, ISO dates, quoting, spreadsheet-safe text, documented columns, mapping/preview on import, dedupe and conflict handling. CSV is a snapshot, not live external-file sync. Backups retain revisions; current-record CSV need not. Automatic service reminders and Garmin-derived equipment mileage are deferred.

## Proposed stack

- **TypeScript + React:** interface, graphs, forms, chat.
- **Python + FastAPI:** backend, Garmin integration, parsers, calculations, planning, maintenance.
- **SQLite / SQL:** local persistence.
- **AI providers:** manually selectable OpenAI Responses API or Qwen through Ollama; local Qwen remains the no-fee default.
- App backend calls narrow provider-neutral application tools directly. MCP is an optional adapter for external clients.
- Candidate Garmin library: `python-garminconnect`. Verify actual authentication/features; not guaranteed or official. The full plan includes research links.

## Execution backlog and user inputs

Detailed tasks/subtasks and completion gates are in [`../planning/implementation-tasks-and-your-input.md`](../planning/implementation-tasks-and-your-input.md):

- T1 feasibility; T2 local foundation; T3 import/export; T4 sync; T5 expandable dashboard; T6 AI/history/profile; T7 training; T8 Garmin publishing; T9 food/nutrition; T10 daily-use lifecycle/recovery; T11 maintenance; T12 transparent daily training readiness.
- T11 retains its number but executes alongside/after T6, not necessarily last. First useful release includes data, dashboard, historical AI and maintenance; full scope later includes training/nutrition.
- User inputs: U1 export complete and locally inventoried, U2 Garmin login/MFA privately in local flow, U3 removed, U4 background decision deferred, U5 usability feedback, U6 in-app training answers, U7 deliberate workout publication/testing, U8 in-app nutrition inputs, U9 free food API key only if required, U10 GitHub sign-in deferred, U11 maintenance details during use.
- We can inspect this computer's hardware ourselves. Only ask if a different computer is the target.
- T6.3 is complete: OpenAI and Qwen share a grounded NDJSON streaming chat flow over `get_health_summary`, `list_activities`, and `compare_periods`; the interface exposes periods, freshness, missing data, record counts, and activity links. Relative periods are application-resolved, Qwen is live-verified, and OpenAI remains mocked until a key is supplied.
- T6.4 is complete: `find_similar_rides` uses a real reference ride plus adjustable type/duration/distance/elevation filters, reports candidate and match counts, preserves unavailable criteria, includes comparison sensor metrics, and displays links for the reference and returned matches. `find_same_course_rides` additionally processes GPS tracks locally, matches bidirectional route coverage plus endpoints/distance/direction, exposes no raw coordinates to the model or UI, and calculates earliest-to-latest performance changes across all matched attempts. A real 6 October 2026 Sprint reference produced 47 same-course matches, including reverse-direction rides and 48 total attempts dating to 8 May 2024. The local Qwen flow was verified end to end with a grounded deterministic course summary.
- T6.5–T6.7 are complete (10 October 2026): `assess_ride` uses actual volume/sensors, active goals only as context, explicit session intent, optional duration targets, and conditional interpretations for unknown intent. `running_volume_trend` calculates bounded weekly running totals and changes. Chat settings tools create validated previews; explicit Save change applies atomic, idempotent, stale-protected updates through the same Settings functions. Goal create/correct/archive revisions persist in SQLite and backups. Local Qwen passed assessment, weekly volume, goal creation/correction, and profile updates; browser checks verified review/save and immediate Settings refresh. All 97 backend tests, TypeScript checks, and production build pass. Live OpenAI remains pending without an API key; its tool/stream/action contracts are mocked and tested. Training preferences and structured plan targets remain T7.
- T11 is complete (10 October 2026): validated atomic maintenance services, operation-ID retries, targeted chat clarification, local dates, cost corrections/Undo, history filters/edit/revisions/remove/restore, spreadsheet-safe CSV export and reviewed mapping/dedupe/conflict import, JSON and backup restoration. Common English commands run locally regardless of selected provider; model-generated writes are blocked. 120 backend tests, TypeScript and build pass. Browser verification used isolated synthetic storage; real data remained 1,065 activities and 52,514 metrics. See `docs/status/t11-verification.md` and `docs/maintenance-csv.md`.
- Recommended next work: T9 nutrition, then T10 daily-use validation. T8 Garmin workout publishing comes last. T7 foundation planning is implemented; see `docs/status/t7-verification.md`. T12 advisory readiness prototype is implemented; see `docs/status/t12-verification.md`. MCP is not a prerequisite. Live OpenAI verification remains pending; see `docs/status/t6-verification.md`.
- T12 research has begun: `docs/planning/readiness-algorithm.md` compares HRV-guided evidence, sleep/load definitions and limitations, audits real input coverage and proposes three bounded groups (autonomic, sleep, recent workload). The numerical weights/thresholds are engineering hypotheses, not validated scientific coefficients. The initial ingestion gaps were repaired on 10 October: 1,434 nightly HRV averages and all four October activity loads are now available. Source timing, incomplete older workload coverage, and readiness implementation remain; see `docs/status/sync-recovery-verification.md`. The versioned readiness prototype now computes scores or partial ranges, with past-only references, completed-sleep timing and previous-day RHR context. Calibration is provisional.
- The user does not need to choose libraries/schema/etc. Continue independent work when input is pending. Do not start implementation just because this handoff was loaded; respond to the new chat's actual instruction.

## GitHub authentication history — important

The user chose to configure Git authentication themselves and confirmed that commit `f48aa70` was pushed successfully to `https://github.com/dohof2/garmin_health_training.git`. Do not expose or request tokens. A request to implement work does not by itself authorize committing or pushing it; only commit/push when the user explicitly asks. Check current Git state first and preserve unrelated local changes.

## Working style

User wants reviewable planning files and clear division of what needs their input. Keep responses concise; perform authorized document edits without repeated confirmation. Keep planning, progress, and implementation consistent. No proactive agents unless the user/applicable instructions ask for them. No further sign-in, cloud deployment, paid fallback, or background startup unless explicitly requested.

## Latest sync repair — 10 October 2026

Live summary payloads, FIT session metadata, and historical HRV are now preserved and normalized where explicit fields exist. Migrations 013/014 add activity metrics, source responses, FIT recovery versioning, and resumable HRV backfill. Real recovery preserved 1,065 activities and 2,937,459 samples; metrics increased to 56,843 after backfill/current sync. All five checkpoints are synced through 10 October. 135 backend tests, TypeScript, and build pass. New work is uncommitted. Historical HRV gaps where Garmin returned no value remain missing; archive-only categories remain as listed in live-data-coverage.md.

## T12 readiness prototype — 10 October 2026

Migration 015, `backend/app/readiness.py`, API/settings, dashboard card/trend, immutable calculation revisions, portability, and advisory assistant tool are implemented. 157 backend tests plus TypeScript/build pass; synthetic browser and local Qwen checks pass. Real derived values remain private in the ignored database. See `docs/status/t12-verification.md`. Source references are past-only; historical estimates use current corrected observations, not historical availability. New work is uncommitted; T7 foundation planning is now implemented.

## T7 foundation planning — 10 October 2026

Migration 016, validated planning services/APIs, Training UI, saved just-in-time preferences, structured endurance/strength templates, draft/accept/edit/feedback, explicit progression proposals and portability are implemented. 177 backend tests, TypeScript and build pass; isolated synthetic browser workflow verified. See `docs/status/t7-verification.md` and `docs/planning/training-rules.md` for scope and provisional numeric defaults. Actual training preferences/plans remain empty; U6 is supplied during use. Date rescheduling/advanced periodization are extensions; T8 publication is deferred until after T9/T10 and local normal-use validation. Current sync/T12/T7 changes remain uncommitted; do not commit/push without a new explicit request.

User instructed this T7 run to stop when usage remaining reaches 8%; check both account windows between stages and stop at or below 8%. Do not start T8 automatically. API-test isolation was corrected to patch `app.database.database_path`; exact synthetic data and unintended readiness changes were removed from the local database, real Garmin counts unchanged. Temporary test services are stopped when this run ends.

## Roadmap ordering decision — 10 October 2026

The user wants Garmin workout export/publication last because it is the most problematic integration. Next: T9 nutrition → T10 launch/quit, recovery, backup and normal-use checks → T8 Garmin workout publishing. Make the local app work without publication first. Preserve existing Garmin ingestion/sync and local data exports. Do not start T8 before those gates are met.
