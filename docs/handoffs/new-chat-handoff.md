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

1. **Strictly free software/services at present.** No paid hosting, AI API, subscription, or automatic paid fallback. Use existing computer and local AI; hardware/electricity still consume resources. No hardware purchase assumed.
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

- Local chat uses scoped MCP tools and deterministic application calculations, not unrestricted SQL writes or shell access. Cite underlying periods/records, freshness, and uncertainty. Imported text is data, not instructions.
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
- Recommended in current plan: **SQLite authoritative storage + CSV import/export**, fully local/free, instead of CSV-only live storage. User invited a better alternative; recommendation documented, no explicit separate storage confirmation obtained.
- Example: “Log that I replaced my road bike chain today”; “When did I last replace the rear tire?”; “Export my maintenance history to CSV.”
- Required item/equipment label, work performed, event date. Create labels on demand; no full equipment inventory. Ask only for missing/ambiguous essentials, resolve relative dates with local timezone. Clear logging instruction saves and shows result with Edit/Undo; hypotheticals/future plans do not become completed events.
- Optional parts, quantity, cost/currency, provider, manual usage/mileage, notes. Never invent values. Stable IDs, revision history, idempotent tool operations, multiple events per prompt, separate totals by currency.
- CSV: UTF-8, ISO dates, quoting, spreadsheet-safe text, documented columns, mapping/preview on import, dedupe and conflict handling. CSV is a snapshot, not live external-file sync. Backups retain revisions; current-record CSV need not. Automatic service reminders and Garmin-derived equipment mileage are deferred.

## Proposed stack

- **TypeScript + React:** interface, graphs, forms, chat.
- **Python + FastAPI:** backend, Garmin integration, parsers, calculations, planning, maintenance.
- **SQLite / SQL:** local persistence.
- **Ollama:** free local text/tool and vision models; choose after hardware benchmarks.
- App backend is MCP host/client with narrow local application-owned MCP server/tools.
- Candidate Garmin library: `python-garminconnect`. Verify actual authentication/features; not guaranteed or official. The full plan includes research links.

## Execution backlog and user inputs

Detailed tasks/subtasks and completion gates are in [`../planning/implementation-tasks-and-your-input.md`](../planning/implementation-tasks-and-your-input.md):

- T1 feasibility; T2 local foundation; T3 import/export; T4 sync; T5 expandable dashboard; T6 AI/history/profile; T7 training; T8 Garmin publishing; T9 food/nutrition; T10 daily-use lifecycle/recovery; T11 maintenance.
- T11 retains its number but executes alongside/after T6, not necessarily last. First useful release includes data, dashboard, historical AI and maintenance; full scope later includes training/nutrition.
- User inputs: U1 export complete and locally inventoried, U2 Garmin login/MFA privately in local flow, U3 removed, U4 background decision deferred, U5 usability feedback, U6 in-app training answers, U7 deliberate workout publication/testing, U8 in-app nutrition inputs, U9 free food API key only if required, U10 GitHub sign-in deferred, U11 maintenance details during use.
- We can inspect this computer's hardware ourselves. Only ask if a different computer is the target.
- Recommended next work: complete U2 privately and connect the real provider. First perform a small read-only account/data-type check, then run the existing 22-interval plan covering September 28–October 8 for activities and daily metrics. Review counts/errors before enabling the open-session daily schedule. The simulated engine already passes 2/10/30-day gaps, restart, partial failure, late upload, old correction, deletion, unchanged retry, and scheduled/manual-path tests. Do not mark simulated empty intervals as verified Garmin coverage.
- The user does not need to choose libraries/schema/etc. Continue independent work when input is pending. Do not start implementation just because this handoff was loaded; respond to the new chat's actual instruction.

## GitHub authentication history — important

The user chose to configure Git authentication themselves and confirmed that commit `f48aa70` was pushed successfully to `https://github.com/dohof2/garmin_health_training.git`. Do not expose or request tokens. A request to implement work does not by itself authorize committing or pushing it; only commit/push when the user explicitly asks. Check current Git state first and preserve unrelated local changes.

## Working style

User wants reviewable planning files and clear division of what needs their input. Keep responses concise; perform authorized document edits without repeated confirmation. Keep planning, progress, and implementation consistent. No proactive agents unless the user/applicable instructions ask for them. No further sign-in, cloud deployment, paid fallback, or background startup unless explicitly requested.
