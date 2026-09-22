# Garmin Health & Training App — Progress Status

Last updated: 22 September 2026
Overall status: **Phase 0 feasibility remains in progress; application foundation implementation has started.**
Current position: The local foundation now loads an idempotent synthetic history with activities, samples, and daily metrics. The frontend reads it through tested local API routes and labels it clearly as non-Garmin data. Real Garmin import, synchronization, and AI features have not started.

This is the quick status reference. Detailed requirements and acceptance criteria remain in `health-training-app-plan.md` and `implementation-tasks-and-your-input.md`.

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
| M0 — Feasibility evidence | T1 | 🟡 Partial | Hardware and runtime checks complete; Garmin archive/login and normal-session Ollama benchmark remain |
| M1 — Local data foundation | T2–T4 | 🟡 Partial | Local frontend, backend, and SQLite schema are running; import and synchronization remain |
| M2 — First dashboard | T5 | 🟡 Partial | Synthetic steps and last-activity preview is visible; weekly calories, date rules, and real data remain |
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
| T1.2 | Inventory the real Garmin export | ⏳ Waiting for user input | U1 export is already requested and awaiting Garmin delivery; inspect locally when its path is provided |
| T1.3 | Define Garmin Connect coverage by data type/date | 🟡 Partial | Candidate library coverage researched; account-specific availability and historical behavior require U2 read-only validation |
| T1.4 | Test Garmin login and a small read-only query | ⏳ Waiting for user input | Requires U2 private local login/MFA; no credentials should be sent in chat |
| T1.5 | Benchmark free local text/tool and vision models | 🟡 Partial | Ollama 0.34.2 verified; official Qwen 3.5 2B/4B models downloaded, but normal-session inference benchmark remains because the Codex sandbox cannot create a Metal command queue |
| T1.6 | Inspect running, cycling, and strength workout support | ✅ Complete | Library surface and sample payload capabilities inspected without publishing; real external validation remains T8/U7 |
| T1.7 | Produce feasibility report and record scope risks | ✅ Complete | `phase-0-feasibility-report.md` created and synchronized |

### T2 — Build the local foundation

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T2.1 | Set up backend/frontend, commands, pinned dependencies, and synthetic fixtures | ✅ Complete | React/TypeScript, FastAPI, pinned lock files, commands, and an idempotent fixture with 3 activities, 4 samples, and 14 metrics are tested |
| T2.2 | Create schema and migrations | ✅ Complete | Repeatable initial migration creates 17 tables covering metrics, activities/samples, provenance, jobs, profile/goals, dashboard, plans, nutrition, and maintenance |
| T2.3 | Add shared date/time/unit handling, validation, and calculations | ⬜ Not started | No user input needed |
| T2.4 | Add local files, credential-store integration, redacted logs, and localhost-only access | 🟡 Partial | Database uses the ignored local `data/` directory and both servers bind to `127.0.0.1`; credential storage and log redaction remain |
| T2.5 | Build navigation, empty/error states, and optional profile/goal settings | 🟡 Partial | Initial responsive application shell and backend-offline state exist; navigation and settings remain |

### T3 — Implement bulk import and manual export

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T3.1 | File selection, archive inventory, nested ZIPs, and extraction limits | ⬜ Not started | Can begin with synthetic fixtures |
| T3.2 | FIT, TCX, GPX, supported CSV, and schema-specific Garmin JSON parsers | ⬜ Not started | Real JSON/archive validation waits for U1 |
| T3.3 | Normalize records, preserve provenance/originals, and deduplicate | ⬜ Not started | Must reconcile repeated imports and later online sync |
| T3.4 | Preview, progress, cancel/resume, partial failures, and coverage report | ⬜ Not started | No user input needed for synthetic implementation |
| T3.5 | CSV/JSON exports, original-file downloads, full backup, and restore preview | ⬜ Not started | Secrets must be excluded |
| T3.6 | Test repeated imports, corrupt files, large archives, and ambiguous matches | ⬜ Not started | Automated fixtures first |
| T3.7 | Import and sample-check the user's full Garmin history | ⏳ Waiting for user input | Requires U1 local export path |

### T4 — Implement Garmin synchronization

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T4.1 | Account connection, renewal, sign-out, and reconnect prompts | ⬜ Not started | Live verification requires U2 |
| T4.2 | Retrieve supported account-wide health/activity data | ⬜ Not started | Live retrieval follows U2 connection |
| T4.3 | Add Sync now, progress, counts, errors, and retry | ⬜ Not started | Can build with a simulated provider first |
| T4.4 | Per-data-type checkpoints, full-gap catch-up, overlap, locking, and recovery | ⬜ Not started | Core reliability requirement |
| T4.5 | Open-session-only scheduling and catch-up after reopening | ⬜ Not started | No background execution or automatic startup |
| T4.6 | Test duplicates, late data, corrections/deletions, expiry, and partial failures | ⬜ Not started | Some live cases may require U2 |
| T4.7 | Seed catch-up from import coverage and track empty versus unchecked intervals | ⬜ Not started | Depends on T3 coverage model |
| T4.8 | Updated-since support or historical reconciliation | ⬜ Not started | Must disclose Garmin source limitations |
| T4.9 | Test 2/10/30-day gaps, restarts, late records, old corrections, and retries | ⬜ Not started | Scheduled and manual sync must share logic |

### T5 — Build the expandable dashboard

| ID | Assignment | Status | Evidence, dependency, or next action |
|---|---|---|---|
| T5.1 | Steps, last activity, and weekly calories-burned cards | 🟡 Partial | Latest synthetic steps and activity are displayed with source labeling; weekly calories and real Garmin data remain |
| T5.2 | Date filters, units, tooltips, gaps, source/freshness, and activity details | ⬜ Not started | Missing data must not appear as zero |
| T5.3 | Card/chart registry and saved add/remove/reorder layout | ⬜ Not started | Architecture should support later graphs |
| T5.4 | Verify totals, week boundaries, and timezone behavior | ⬜ Not started | Source verification follows data availability |
| T5.5 | Present first dashboard and collect usability feedback | ⏳ Waiting for user input | U5 is needed only after a usable version exists |

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
| U1 | Full Garmin account export local path | ⏳ Waiting for Garmin | Real archive inventory and full-history validation |
| U2 | Private Garmin login/MFA through the local app | ⏳ Not needed yet | Live read-only coverage and later sync testing |
| U3 | Device/sensor inventory | ✅ Removed | Garmin Connect is the sole external data source; no inventory required |
| U4 | Background-operation decision | 🔒 Deferred | Later edition only; first edition has none |
| U5 | Dashboard usability feedback | ⏳ Not needed yet | After first working dashboard |
| U6 | Training availability/equipment/experience/restrictions | ⏳ Not needed yet | Asked just in time during personalized use |
| U7 | Deliberate test-workout publication and device check | ⏳ Not needed yet | T8 validation, one test per supported sport |
| U8 | Nutrition inputs and optional known-portion meals | ⏳ Not needed yet | Personalized target and food validation |
| U9 | Free food-API key, only if required | ⏳ Not needed yet | Only if a downloadable database is unsuitable |
| U10 | GitHub sign-in/publication | 🔒 Deferred | Local development does not depend on it |
| U11 | Maintenance details during use | ⏳ Not needed yet | Only when recording actual events |

## Deferred backlog

| ID | Assignment | Status |
|---|---|---|
| F1 | More health/training/nutrition graphs based on actual use | 🔒 Deferred |
| F2 | AI-created dashboard charts using validated configurations | 🔒 Deferred |
| F3 | Phone connectivity and remote access | 🔒 Deferred |
| F4 | WhatsApp or other messaging | 🔒 Deferred |
| F5 | Publish the local project to GitHub | 🔒 Deferred |
| F6 | Background operation and automatic startup decision | 🔒 Deferred |

## Immediate next action

Implement **T2.3** shared date/time, unit, validation, and calculation rules, then use them for the weekly-calories preview. This work does not need U1 or U2.
