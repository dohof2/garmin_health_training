# Garmin Personal API migration plan

Researched 9 November 2026. Planning and public-documentation capture only; no application, dependency, database, credential, or remote Garmin changes.

## Recommendation and scope

Replace the unofficial login/session client with Garmin's official Personal API for inbound data. Preserve the existing application as a separate, reproducible recovery release, outside the migrated runtime. Do not retain a legacy adapter, provider toggle, hidden login fallback, or `garminconnect` dependency in the migrated application.

**This is feasible for core data fetching, but is not a feature-equivalent replacement for this app today.** The inspected Personal Swagger has 26 resource paths, all GET. It documents neither workout/calendar writes nor weight uploads. It also lacks dedicated endpoints for several currently refreshed training metrics. Complete cutover must therefore explicitly accept those limitations or wait for another supported API. This document does not authorize implementation or acceptance of lost functionality.

## Official instructions and captured reference

Use these primary sources, rather than older partner API instructions or unofficial Connect endpoints:

- [Personal authentication guide](https://developer.garmin.com/gc-developer-program/personal/personal-api/): API-key exchange endpoint and key creation instructions.
- [Personal FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/): key expiration/revocation, token lifetime, no refresh tokens, personal-use scope.
- [Personal Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/): resource contracts, parameters, schemas, and endpoint-specific date limits.
- [Official Garmin Python reference](https://github.com/garmin/connect-personal-api-python): client, authenticator, tests, and packaging. Inspect `src/garmin_personal_api/{client,auth,constants}.py` and `pyproject.toml` at the version selected for implementation.
- [Current program overview](https://developer.garmin.com/gc-developer-program): distinguishes Personal pull access from Business APIs, including Training. Business access is a separate integration, not a permission unlocked by the personal key.

The Swagger HTML is a JavaScript viewer; its linked page bundle embeds the OpenAPI JSON. The public schema was extracted without authentication and saved in [the research reference](../reference/garmin-personal-api/README.md). This is a contract snapshot, not evidence of live account behavior. Recheck upstream before implementation and record changes.

## Current application inventory

Reviewed the working tree, including uncommitted changes. HEAD at research time is `2c4609b495db75fe1f31b9ea82d1188cd0ba2191`; HEAD alone does **not** capture the running code. No existing changes were edited.

| Area | Current boundary | Migration work |
| --- | --- | --- |
| Authentication | `backend/app/garmin_connection.py`: password/MFA, private session files, `load_client`, `GarminConnectProvider` | Replace authentication and provider; keep reusable normalization only where schemas actually match |
| Sync engine | `backend/app/sync.py`: seven data types, daily commits, overlap, history preparation, FIT downloads, post-activity load refresh | Preserve reliability; add capability-aware coverage and bounded range preparation |
| Entry points | `backend/app/main.py`: connection/probe, manual and scheduled sync; `sync_repair.py` | Route all reads through the new provider; retire login/MFA/session operations |
| Supplementary reads | `backend/app/supplementary_sync.py`: broad daily/range/static/collection/detail queries | Replace with explicit documented Personal endpoints; do not run the old method crawl |
| Writes | `garmin_training_publish.py`, `rolling_publication.py`, `weight_publish.py`, strength catalog and connected callers | Disable unsupported remote actions and scheduling; preserve local records, remote IDs and publication history |
| UI | `frontend/src/App.tsx`, Garmin publication and sync views | Connection state from Keychain availability; show supported, unavailable and stale data distinctly |
| Secrets | `telegram_bot.py` already reads macOS Keychain via `security find-generic-password` | Reuse the storage pattern, with a separate Garmin service/account |
| Runtime | Python 3.13.15; `garminconnect==0.3.17`, `curl_cffi==0.16.3` | Official reference requires Python >=3.12; verify exact package version and lock dependencies |

The older `docs/status/live-data-coverage.md` is not a complete current inventory: current sync also includes `vo2_metrics` and `supplementary_metrics`, plus a dedicated training-load refresh.

## Data mapping and gaps

Paths below are relative to `https://personal.connectapi.garmin.com`. Exact parameters and schemas are in the captured reference.

| App need | Personal contract | Plan / qualification |
| --- | --- | --- |
| Activities | `/activitylist-service/activities/search/activities`; `/activity-service/activity/{activityId}` | Page the complete result set; merge list and detail with explicit precedence. Retain IDs, parent/child relationships, timezone and original payloads |
| Original recordings | `/download-service/files/activity/{activityId}` | ZIP containing the original recording; reuse safe FIT decoding, session summaries, samples and multisport handling |
| Recorded workout association | `/activity-service/activity/{activityId}/workouts` | Reads workouts performed during an activity. Does not publish, schedule, or enumerate a future workout library |
| Daily metrics | `/usersummary-service/usersummary/daily?calendarDate=...`; `/usersummary-service/v2/dailysummaries?startDate=...&endDate=...` | Single-day summary resembles existing field names. V2 is an object with a `data` array and nested metric groups, requiring a new mapper |
| Sleep | `/sleep-service/sleep/dailySleep?date=...`; `/sleep-service/sleep/dailySleepSummariesByDate` | Personal response is `DailySleepDTO` directly, unlike the old `dailySleepDTO` envelope. Verify score and stage mapping; do not promise old epoch-array or sleep-HRV parity |
| HRV | `/hrv-service/hrv/{calendarDate}`; `/hrv-service/hrv/daily/{fromDate}/{toDate}` | Range summaries for history and daily readings where needed. Documented 204 is no data, not a failed request |
| Weight/body composition | `/weight-service/weight/all/{startDate}/{endDate}` or `/weight-service/weight/range/{startDate}/{endDate}?includeAll=true` | Preserve every weigh-in. Personal `DateWeightDTO.weight` is kilograms; do not reuse the old gram conversion. Verify bone/muscle units against actual responses because descriptions are incomplete |
| Additional supported reads | Steps, stress, hydration, Body Battery, SpO2, heart rate, fitness age, HR zones, profile, nutrition, wellness activities | Explicit optional capabilities. Keep Garmin nutrition distinct from local meals to avoid double counting |
| VO2 | Activity search schema includes `vO2MaxValue` | Potential activity-associated observations, not equivalent to the old dedicated VO2 history. Preserve old provenance and verify semantics before normalizing |
| Exercise load/effect | Activity detail `summaryDTO.activityTrainingLoad` and training-effect fields | Preserve source activity load. This does not establish daily acute/chronic load, load focus, recovery time, or readiness parity |
| Extra activity detail | Summary/split summaries, workout association, original FIT | Compare laps, strength sets, route samples, zones and charts with existing behavior. FIT may cover some gaps; neither weather/gear detail nor all old detail endpoints are documented |
| Training status and wider account data | No matching dedicated Personal contracts for daily training status/load, training readiness, recovery time, FTP history, race predictions, endurance/hill scores, full device/gear/course/plan collections | Retain historical data; mark future refresh unavailable. Check embedded fields individually; do not guess endpoints or substitute estimates for Garmin values |
| Outbound publication | No resource write endpoints | Personal key cannot replace workout create/update/delete, scheduling/unscheduling, rolling publication, device push, or Garmin weight upload. Local planning and local weight entry can continue |

If publishing remains essential, defer complete cutover or separately investigate Business Training API access. Keeping the unofficial writer inside the new app would conflict with the requested external-only legacy backup.

## Authentication and Apple Keychain

Proposed convention for later setup: generic password service **`garmin-app.personal-api`**, account **`api-key`**. No key is needed for this planning task. Add it through Apple's Keychain Access later; the future backend reads it locally. The browser only receives availability/status, never the key or bearer token.

1. POST `https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token` with `Authorization: ApiKey <key>`.
2. The official authenticator reads the response as a **raw token string**, not a JSON token object. Resource GETs use `Authorization: Bearer <token>`.
3. Tokens last 24 hours or until the key expires, whichever is earlier; there is no refresh-token grant. Obtain a new token using the same key. Key expiry choices are 30/90/180 days or one year; deleting the key invalidates associated tokens.
4. Prefer the official data client behind an app-owned token manager with an in-memory token, single-flight refresh, and a one-hour pre-expiry margin. Parse `exp` only to schedule refresh, not to establish trust or identity. Restart can obtain another token. Key rotation invalidates the cached token.
5. The official reference authenticator always uses a plaintext disk cache. If selected instead, explicitly configure an app-private excluded cache, enforce directory/file permissions 0700/0600 even for existing files, and exclude it from backup/export. Do not silently accept its default home-directory cache. Choose and document one approach during implementation.
6. On a resource 401, refresh once and retry the read once; if still rejected, show reconnect/key replacement required. Keychain denial/locked state must be distinguishable from a missing key. No password fallback. Sanitize HTTP errors before logs, database storage, AI tools or UI: the reference errors include response text.

Use a fixed production origin; do not allow a runtime base-URL override to send credentials to an arbitrary host. The schema also lists a China origin, but do not infer the user's account region or switch regions automatically.

## Sync design

- Implement a focused Personal provider against the existing `SyncProvider` boundary. Reuse local SQLite storage, import/export and derived calculations; map the vendor contract into canonical records before committing.
- Replace global assumptions that all seven old streams are supported. Store capability status separately from successful/empty/failed coverage. An unsupported stream must not be marked synced or prevent supported streams from refreshing. Disable the old post-activity training-status fetch.
- Retain the three-day overlap, full-gap recovery, explicit historical reconciliation, durable per-day commits and interrupted-job recovery. Prepare bounded ranges once and distribute them into daily commits; do not refetch an entire range for each day.
- Documented inclusive caps: steps/stress 28 days; sleep summaries/hydration/Body Battery 31 days; V2 daily summaries one year (use conservative <=365-day batches). HRV, weight and other ranges have no numeric maximum in this snapshot: use conservative configurable batches and validate with the account. A request-range cap is not a historical-retention guarantee.
- Activity search defaults to offset 0, limit 99, descending order and `excludeChildren=true`; explicitly choose pagination and multisport policy. Do not filter only cycling/running. Detect repeated pages, deduplicate IDs and reconcile overlap to handle changes during pagination. Date filters use activity-local dates; test Jerusalem DST and midnight boundaries against canonical UTC timestamps.
- HTTP 204 and contract-valid empty arrays/objects mean no data only where the relevant endpoint defines that behavior. Errors, malformed data, missing pages and unsupported capabilities never advance successful coverage. Missing fields remain missing, not zero; absence never implies remote deletion.
- Retry bounded transient/network/5xx failures with jitter. Respect `Retry-After` on 429 and limit concurrency. No verified numerical global rate quota was found in the captured docs; do not invent one. The existing 0.25-second outer delay does not govern requests inside a range/detail fetch.
- Match existing Garmin IDs and canonical metric identities across providers; keep transport provenance separately. Inspect `_upsert_activity`, fingerprint matching, metric keys, payload upserts and checkpoints before choosing schema changes. Never change IDs just because authentication changes. Preserve richer old fields when the new payload omits them, with source/time provenance so stale history is not presented as current.
- Keep old archive importers and original FIT files. Do not replace the historical database with a new partial API download. Validate account continuity before merging data: a rotated key must not silently combine another account's records.

## External legacy recovery release

Create this at implementation time, before changing code; no archive/tag/branch has been created by this research task.

1. Capture the entire reviewed working tree, including intended uncommitted and untracked source. Record a manifest/checksums and lockfiles. A tag at today's HEAD would omit substantial current work. Review excluded files so local configuration and personal data are not accidentally embedded in a source archive.
2. Keep a separate legacy release directory/archive and reproducible Python/frontend environment, launcher, runtime versions and build instructions. Git history can support recovery but is not the only backup. Test launching the frozen release against a disposable database copy.
3. Stop the app before a consistent SQLite backup, or use SQLite's backup API; include referenced originals/uploads and necessary local configuration. Store credentials separately in protected local storage; never in Git or the portable app export. Preserve the legacy session securely if useful, while documenting that expiry may require reauthentication.
4. Use separate `HT_APP_DATA_DIR` values and environments for legacy and migration validation. Never run both against the same database, and never enable two scheduled writers.
5. Rollback: stop the new app and schedulers; snapshot its current data; start the frozen legacy release with its compatible data copy. A pre-migration database restore can discard subsequent local edits, so retain a delta/export and reconcile that data before resuming normal use. Never let older code open a newer schema without proving compatibility.
6. Before resuming remote writes, read back existing Garmin workout/calendar state and reconcile publication IDs. Restoring a database cannot undo remote changes and must not cause duplicate sends. Legacy access remains subject to Garmin availability; a backup is not a guarantee that the private endpoints continue working.

## Execution order and acceptance gates

1. **Freeze recovery release.** Verify code/environment restoration and consistent data backup before implementation changes.
2. **Finalize contract choices.** Recheck Swagger and pin the official client version/commit. Decide in-memory auth vs protected reference cache. Produce a field-level supported/partial/unavailable report for the seven current streams and important consumers.
3. **Build in isolation.** New auth/provider, capability-aware sync, updated connection UI and disabled unsupported write actions; remove the old library and all runtime imports/callers from the migrated application. Keep canonical database records and source archives.
4. **Use synthetic contract tests.** Verify auth raw-token parsing, rotation, denied Keychain, one-refresh limit, response envelopes, units, inclusive chunk boundaries, pagination, duplicates, malformed/empty/error responses, checkpoint resume, FIT and multisport safety.
5. **After the key is added, perform a read-only pilot.** Profile/account continuity, one daily summary, sleep, HRV, all weigh-ins, one cycling/running/strength activity where available, recorded workout association and FIT download. Validate an older date and a representative recent range. Measure request count, rate responses and observed history reach. No Garmin writes are needed.
6. **Compare on a copied database.** Repeat the same sync twice: no duplicate activities/metrics or unnecessary sample reimports. Compare dashboard, sleep, weight, HRV, VO2 provenance, activity charts, training completion and load/readiness inputs. Verify unavailable inputs cause truthful stale/missing states instead of false freshness or readiness confidence.
7. **Exercise failure and restore paths.** Interrupted sync resumes; one endpoint failure does not hide good streams; original data survives; new changes can be recovered without relying on old code understanding a new schema. Run the relevant sync/import/export/connection/consumer tests and frontend type/build checks.
8. **Cut over only after review of actual gaps.** Supported streams must pass parity; any deliberately unavailable behavior must be visible and accepted. Then switch the everyday launcher to the new release and retire legacy from the runtime. Observe several normal sync cycles and retain the external recovery release.

## What remains unverified

No account API calls were made and no secrets were accessed. Live payload completeness, actual history reach, undocumented units, real rate limits, FIT contents and detailed feature parity require the later read-only pilot. The public instructions and endpoint contracts needed to begin implementation have been located; a lossless replacement for every current feature has **not** been established. This is a planning document, not a successful migration report.
