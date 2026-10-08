# Garmin Health & Training App — Progress Status

Last updated: 8 October 2026
Overall status: **The local data foundation, first dashboard, private Garmin connection, live catch-up, and open-session daily synchronization are operational.**
Current position: The ignored original Garmin ZIP remains immutable. All safely interpretable health/training history has been imported: core activities/metrics/samples, hydration, alerts, nutrition, and 26,143 extended training/biometric records across 48 categories. Every one of 298 outer files is classified (144 extended imports, 121 handled by dedicated stages, 33 private administrative exclusions, zero unsupported), and all 55,448 FIT files decoded without failure. The dashboard, portable export/backup, and restore preview are operational. Private Garmin authentication stores owner-only session tokens locally. The first live catch-up completed without failures through 8 October 2026. Daily synchronization is enabled only while the app is open, uses a durable due-check, catches every missing day, and rechecks the latest three days. Live activity sync now downloads original FIT details only when samples are missing: a focused October 2–8 reconciliation imported 6,568 sensor samples for the latest three activities, restoring heart rate for all three and power where Garmin recorded it. Live/archive fingerprints prevent duplicate FIT-only records; the one detected duplicate was merged into its 3,195-sample archive record. SQLite quick-check and foreign keys pass. Real-world token expiry observation and AI features remain.

This is the quick status reference. Detailed requirements and acceptance criteria remain in [`../planning/health-training-app-plan.md`](../planning/health-training-app-plan.md) and [`../planning/implementation-tasks-and-your-input.md`](../planning/implementation-tasks-and-your-input.md).

## Status legend

| Status | Meaning |
|---|---|
| ✅ Complete | Work and its current verification are finished |
| 🟡 Partial | Useful work is complete, but a stated validation item remains |
| ⏳ Waiting for user input | Requires an identified user-only input or action |
| ⬜ Not started | No implementation work has begun |
| 🔒 Deferred | Explicitly outside the current release or postponed |

## Milestone summary

| Milestone | Scope | Status | Current note |
|---|---|---|---|
| M0 — Feasibility evidence | T1 | 🟡 Partial | Hardware, runtime, archive, Garmin login, and live read-only query checks complete; normal-session Ollama benchmark remains |
| M1 — Local data foundation | T2–T4 | 🟡 Partial | Import/export, private authentication, verified live catch-up, and open-session daily scheduling are complete; natural session-expiry observation and broader Garmin data types remain |
| M2 — First dashboard | T5 | 🟡 Partial | Technical implementation and timezone/DST verification are complete; gradual U5 usability feedback remains |
| M3 — Historical AI assistant | T6 | ⬜ Not started | Provider-neutral design planned; no AI integration implemented |
| M3A — Maintenance history | T11 | ⬜ Not started | SQLite-authoritative design with CSV portability is planned |
| M4 — Training | T7–T8 | ⬜ Not started | Personalized planning and Garmin publishing remain future implementation |
| M5 — Food and nutrition | T9 | ⬜ Not started | Manual logging precedes photo estimation |
| M6 — Daily-use release | T10 | ⬜ Not started | Explicit launch/quit and open-session-only jobs remain required |

## Task and subtask tracker

### T1 — Confirm feasibility

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T1.1 | Inspect OS, processor, memory, storage, and runtimes | ✅ Complete | M5 MacBook Air, 16 GiB memory, adequate storage; Python 3.13.15, Node.js 24.21.0 LTS, npm 11.19.0, SQLite, Git, and developer tools verified |
| T1.2 | Inventory the real Garmin export | ✅ Complete | Original ZIP integrity and archive safety verified; 1,054 activities, 3,050 daily summaries, 2,908 sleep records, and 55,448 nested FIT files inventoried in `garmin-export-inventory.md` |
| T1.3 | Define Garmin Connect coverage by data type/date | 🟡 Partial | Live activities and 11 daily-summary metric types are confirmed for the account through 8 October 2026; broader data types remain future coverage work |
| T1.4 | Test Garmin login and a small read-only query | ✅ Complete | Private local login succeeded; the saved-token session passed a live read-only check with 91 daily-summary fields and zero activities for the current day |
| T1.5 | Benchmark free local text/tool and vision models | 🟡 Partial | Ollama 0.34.2 verified; official Qwen 3.5 2B/4B models downloaded, but normal-session inference benchmark remains because the Codex sandbox cannot create a Metal command queue |
| T1.6 | Inspect running, cycling, and strength workout support | ✅ Complete | Library surface and sample payload capabilities inspected without publishing; real external validation remains T8/U7 |
| T1.7 | Produce feasibility report and record scope risks | ✅ Complete | `phase-0-feasibility-report.md` created and synchronized |

### T2 — Build the local foundation

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T2.1 | Set up backend/frontend, commands, pinned dependencies, and synthetic fixtures | ✅ Complete | React/TypeScript, FastAPI, pinned lock files, commands, and an idempotent fixture with 3 activities, 4 samples, and 14 metrics are tested |
| T2.2 | Create schema and migrations | ✅ Complete | Eight repeatable migrations create 28 tables, including dedicated and extended import records, file checkpoints, and full archive classification |
| T2.3 | Add shared date/time/unit handling, validation, and calculations | 🟡 Partial | Importer validates timestamps/numbers and converts activity milliseconds, centimeters, and kilojoules; shared IANA-timezone calendar conversion and Monday–Sunday boundaries are tested across DST, while broader unit rules remain |
| T2.4 | Add local files, credential-store integration, redacted logs, and localhost-only access | ✅ Complete | Database and Garmin session tokens use ignored local `data/`; tokens are owner-only, passwords are not persisted, authentication errors are sanitized, and both servers bind to `127.0.0.1` |
| T2.5 | Build navigation, empty/error states, and optional profile/goal settings | 🟡 Partial | Initial responsive application shell and backend-offline state exist; navigation and settings remain |

### T3 — Implement bulk import and manual export

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T3.1 | File selection, archive inventory, nested ZIPs, and extraction limits | 🟡 Partial | Local ZIP discovery, nested inspection, CRC, path/symlink/encryption, count, size, ratio, and depth limits are implemented; general file chooser remains |
| T3.2 | FIT, TCX, GPX, supported CSV, and schema-specific Garmin JSON parsers | ✅ Complete | All present in-scope FIT/TCX/GPX/JSON categories are parsed; the supplied archive contains no CSV files; opaque proprietary/configuration FIT fields remain inventoried rather than misrepresented |
| T3.3 | Normalize records, preserve provenance/originals, and deduplicate | 🟡 Partial | Implemented formats retain provenance, normalize units/times, and upsert idempotently; 13 cross-file hydration duplicates, XML matches, and duplicate FIT paths are reconciled; future sync reconciliation remains |
| T3.4 | Preview, progress, cancel/resume, partial failures, and coverage report | 🟡 Partial | All import stages have previews/checkpoints and a ten-category coverage/failure UI plus 298-file audit; background progress and user cancellation remain |
| T3.5 | CSV/JSON exports, original-file downloads, full backup, and restore preview | ✅ Complete | Date-filtered spreadsheet-safe CSV and streaming versioned JSON are available; backups use consistent SQLite snapshots, always exclude secrets, optionally include private originals, and pass checksum/schema/integrity/relationship preview; 1,051 preserved FIT/TCX/GPX files are downloadable without regeneration |
| T3.6 | Test repeated imports, corrupt files, large archives, and ambiguous matches | 🟡 Partial | Fifty-one automated tests cover idempotency, unsafe paths, conversion, matching, compact timestamps, coordinates, live/FIT deduplication and detail samples, identity sanitization, catalog accounting, migrations, dashboard/history behavior, backup/restore, synchronization recovery/scheduling, private token handling, MFA, read-only probing, and provider normalization; more corrupt/oversized fixtures remain |
| T3.7 | Import and sample-check the user's full Garmin history | ✅ Complete | All in-scope categories imported; every outer file classified; repeated runs write zero rows; identity-key scan, SQLite integrity, and foreign keys pass; detailed evidence is in `import-coverage.md` |

### T4 — Implement Garmin synchronization

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T4.1 | Account connection, renewal, sign-out, and reconnect prompts | 🟡 Partial | Private sign-in and saved-session reuse work against the live account; owner-only token storage, MFA, sign-out, and reconnect paths exist, while renewal/expiry behavior still needs a real lifecycle test |
| T4.2 | Retrieve supported account-wide health/activity data | 🟡 Partial | Live catch-up retrieves activity summaries, 11 daily-metric types, and original FIT sensor streams on demand; 6,568 samples restored heart rate for all three newest activities and power for the two power-recorded rides; broader Garmin data-type coverage remains |
| T4.3 | Add Sync now, progress, counts, errors, and retry | ✅ Complete | Sync now/status UI, durable progress/results, last-success/error state, and retry-safe execution are operational; successful sync immediately refreshes dashboard values, activity rows, checkpoints, and plan |
| T4.4 | Per-data-type checkpoints, full-gap catch-up, overlap, locking, and recovery | ✅ Complete | Independent daily checkpoints, atomic interval commits, configurable overlap/request pacing, single-job locking, and interrupted-job recovery are tested |
| T4.5 | Open-session-only scheduling and catch-up after reopening | ✅ Complete | Daily sync is enabled only while the app is open; startup and 15-minute due checks skip an already-current day, run the shared catch-up pipeline for any missing date, and remain inactive while the app is closed |
| T4.6 | Test duplicates, late data, corrections/deletions, expiry, and partial failures | 🟡 Partial | Tests cover all listed cases, FIT/live fingerprint reconciliation, token reuse, simulated expiry, sign-out/reconnect, and explicit deletion tombstones; natural Garmin token-expiry behavior remains to observe during use |
| T4.7 | Seed catch-up from import coverage and track empty versus unchecked intervals | ✅ Complete | Real checkpoints seed from activity/daily-metric import bounds; successful empty daily intervals are stored explicitly and failed intervals remain pending |
| T4.8 | Updated-since support or historical reconciliation | ✅ Complete | Three-day overlap plus selectable historical reconciliation is implemented; UI/API disclose that older corrections require recheck when updated-since is unavailable |
| T4.9 | Test 2/10/30-day gaps, restarts, late records, old corrections, and retries | ✅ Complete | Automated tests cover 2/10/30-day gaps, mid-job restart, independent failures, late older uploads, corrections outside overlap, unchanged retries, deletion, and the shared scheduled/manual path |

### T5 — Build the expandable dashboard

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T5.1 | Steps, last activity, and weekly calories-burned cards | ✅ Complete | Real Garmin cards are displayed; weekly total/active/resting calories use the latest Monday–Sunday interval and label partial coverage instead of filling missing days with zero |
| T5.2 | Date filters, units, tooltips, gaps, source/freshness, and activity details | ✅ Complete | Reusable inclusive 30/90/all date controls filter activities; cards and rows show units/source/freshness; tooltips explain gaps; expandable details label absent fields as “Not recorded” |
| T5.3 | Card/chart registry and saved add/remove/reorder layout | ✅ Complete | A validated backend/frontend registry drives all three cards; users can add, hide, and reorder them, and the complete layout persists atomically in SQLite across reloads |
| T5.4 | Verify totals, week boundaries, and timezone behavior | ✅ Complete | Real total/active/resting sums and Monday–Sunday boundaries are tested; aware activity timestamps use the browser's valid IANA timezone across DST, while date-only health metrics remain unchanged; proprietary Garmin timezone labels safely fall back to the browser timezone |
| T5.5 | Present first dashboard and collect usability feedback | ⏳ Waiting for user input | A usable desktop/mobile version exists; U5 feedback can now be collected gradually |

### T6 — Add the historical AI assistant and MCP

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T6.1 | Connect a local model with load/unavailable/slow states | ⬜ Not started | Final model selection waits for normal-session Ollama benchmark |
| T6.2 | Scoped MCP query tools and deterministic calculations | ⬜ Not started | Model must not receive unrestricted SQL or shell access |
| T6.3 | Streaming chat, evidence links, freshness, and uncertainty | ⬜ Not started | No invented missing values |
| T6.4 | Similar-ride matching with visible criteria and tolerances | ⬜ Not started | Must show sample size and linked rides |
| T6.5 | Conditional ride-effectiveness assessment | ⬜ Not started | Requires session intent or clearly stated assumptions |
| T6.6 | Validated optional goal/profile updates through chat | ⬜ Not started | Must share storage with forms and support correction |
| T6.7 | Test example questions, numeric accuracy, prompt injection, and persistence | ⬜ Not started | Imported text is data, not instructions |

### T7 — Build personalized training planning

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T7.1 | Context-aware questionnaire with saved answers | ⬜ Not started | U6 is collected during actual personalized use |
| T7.2 | Structured strength, cycling, and running workout models | ⬜ Not started | No user input needed for base models |
| T7.3 | Testable progression, recovery, and constraint rules | ⬜ Not started | Must respect restrictions and avoid diagnosis |
| T7.4 | Reviewable weekly plans, editing, and substitutions | ⬜ Not started | Personalized output uses U6 when requested |
| T7.5 | Completion, effort, soreness, missed-session, and revision tracking | ⬜ Not started | No silent plan rewrites |
| T7.6 | Test conflicts, equipment, missing goals, stale data, and restrictions | ⬜ Not started | Goals remain optional |

### T8 — Publish and schedule Garmin workouts

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T8.1 | Map sport sessions to supported Garmin fields | ⬜ Not started | Unsupported representations must be visible |
| T8.2 | Preview, publish, schedule, and read-back verification | ⬜ Not started | External write requires deliberate user action |
| T8.3 | Remote IDs, retry safety, edits, rescheduling, and removal | ⬜ Not started | Retries must not create duplicates |
| T8.4 | Validate one workout per supported sport in Garmin/device | ⏳ Waiting for user input | Requires U7 and U2 if disconnected |

### T9 — Add food logging and nutrition status

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T9.1 | Manual foods, recipes, reusable meals, sources, and totals | ⬜ Not started | Implement before photo estimation |
| T9.2 | Photo analysis with editable foods, portions, and uncertainty | ⬜ Not started | Requires successful local vision-model validation |
| T9.3 | Free nutrient lookup and caching | ⬜ Not started | U9 only if the chosen free API requires a personal key |
| T9.4 | Documented targets, overrides, history, and exercise handling | ⬜ Not started | Personalized values require U8 during use |
| T9.5 | Target/logged/remaining calories and macros | ⬜ Not started | Estimated and measured values must remain distinct |
| T9.6 | Validate portions, recipe scaling, edits, dates, and totals | ⬜ Not started | Automated fixtures first; optional U8 samples later |

### T10 — Prepare for everyday local use

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T10.1 | Launcher/start-stop guidance, errors, and migration recovery | ⬜ Not started | No automatic startup |
| T10.2 | Re-measure resources and optimize models/jobs | ⬜ Not started | Requires representative data and working AI integration |
| T10.3 | Explicit launch/quit and owned-process shutdown | ⬜ Not started | Must save checkpoints and leave unrelated services alone |
| T10.4 | Optional reminders only while the app is open | ⬜ Not started | Disabled unless selected |
| T10.5 | Export/delete controls, secret exclusion, and full restore | ⬜ Not started | Revalidate across all completed modules |
| T10.6 | Normal-use trial: sleep/wake, offline, expiry, interruption, settings | ⬜ Not started | Later usability feedback requested |

### T11 — Maintenance and accessory replacement log

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T11.1 | Equipment labels, events, optional details, IDs, and revisions | ⬜ Not started | Depends on T2 storage |
| T11.2 | Prompt extraction, local dates, and targeted clarification | ⬜ Not started | U11 occurs during normal use |
| T11.3 | Validated log/list/update/undo/export tools with operation IDs | ⬜ Not started | AI writes through application services, not CSV text |
| T11.4 | Maintenance history screen with filters and recoverable deletion | ⬜ Not started | Simple non-chat review/edit route required |
| T11.5 | History questions, multiple entries, and currency-separated totals | ⬜ Not started | Never invent optional values |
| T11.6 | UTF-8 CSV import/export, mapping, safety, dedupe, and conflicts | ⬜ Not started | CSV remains a snapshot, not live storage |
| T11.7 | Include records/revisions in JSON and backup/restore | ⬜ Not started | Current-record CSV need not include revisions |
| T11.8 | Test ambiguity, dates, revisions, retries, CSV, and restoration | ⬜ Not started | Automated fixtures first |

## User-input tracker

| ID | User input or action | Status | When it is needed |
|---|---|---|---|
| U1 | Full Garmin account export local path | ✅ Complete | Original ZIP is in the ignored local import directory and passed integrity/safety inspection |
| U2 | Private Garmin login/MFA through the local app | ✅ Complete | Login was entered only in the local app; a reusable private token session and live read-only query were verified |
| U3 | Device/sensor inventory | ✅ Removed | Garmin Connect is the sole external data source; no inventory required |
| U4 | Background-operation decision | 🔒 Deferred | Later edition only; first edition has none |
| U5 | Dashboard usability feedback | ⏳ Ready when convenient | The first working desktop/mobile dashboard is available; feedback can be provided gradually |
| U6 | Training availability/equipment/experience/restrictions | ⏳ Not needed yet | Asked just in time during personalized use |
| U7 | Deliberate test-workout publication and device check | ⏳ Not needed yet | T8 validation, one test per supported sport |
| U8 | Nutrition inputs and optional known-portion meals | ⏳ Not needed yet | Personalized target and food validation |
| U9 | Free food-API key, only if required | ⏳ Not needed yet | Only if a downloadable database is unsuitable |
| U10 | GitHub sign-in/publication | ✅ Complete | User authenticated independently and published the repository at `dohof2/garmin_health_training` |
| U11 | Maintenance details during use | ⏳ Not needed yet | Only when recording actual events |

## Deferred backlog

| ID | Assignment | Status |
|---|---|---|
| F1 | More health/training/nutrition graphs based on actual use | 🔒 Deferred |
| F2 | AI-created dashboard charts using validated configurations | 🔒 Deferred |
| F3 | Phone connectivity and remote access | 🔒 Deferred |
| F4 | WhatsApp or other messaging | 🔒 Deferred |
| F5 | Publish the local project to GitHub | ✅ Complete |
| F6 | Background operation and automatic startup decision | 🔒 Deferred |

## Immediate next action

Begin the historical AI assistant while observing saved-session renewal/expiry during normal Garmin use; if Garmin rejects a stored token, verify the existing reconnect prompt and private reauthentication path against that real event.
