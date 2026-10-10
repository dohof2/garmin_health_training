# Health & Training App — Tasks and Your Input

Status: Proposed execution backlog for review. No application implementation is authorized by this document alone or has started.

Based on the [reviewed application plan](health-training-app-plan.md). All development is local and uses free software/services. GitHub publication remains deferred.

## 1. What is needed from you

**You do not need to decide technical details or complete a personal-health questionnaire before development.** I can build the foundation, interface, parsers, calculations, and tests independently. Your archive and Garmin sign-in are needed to verify that the integration works with your actual data.

**U1 status: complete.** The original Garmin ZIP is available locally, excluded
from Git, and passed integrity, archive-safety, schema, count, and date-coverage
inspection on 6 October 2026. See
[`../status/garmin-export-inventory.md`](../status/garmin-export-inventory.md).

| ID | Your input or action | When needed | What it blocks if unavailable |
|---|---|---|---|
| U1 | Provide a full Garmin account export, preferably as the original ZIP/parts. | ✅ Complete | The ignored local archive is now the source for importer implementation and validation |
| U2 | Sign in to Garmin through the local connection flow and complete any verification/MFA yourself. Do not send passwords or codes in chat. | Live synchronization test | Actual account synchronization; manual import, dashboard, and offline analysis can continue |
| U3 | Removed: Garmin Connect is the sole source. No device or sensor details are required for ingestion. | No input needed | Nothing |
| U4 | Deferred: decide whether background operation is wanted in a later edition. The first edition has none and no automatic startup. | Future iteration only | Nothing in the first edition |
| U5 | Try the first working dashboard and report anything confusing or missing. | First usable version | Your acceptance of the user experience; technical validation does not depend on a response |
| U6 | Answer training questions in the app when asking for personalized advice: available time, equipment, experience, and relevant limitations. Goals remain optional. | First personalized training request | Personalized recommendations requiring those details; historical analysis remains available |
| U7 | Select and publish a previewed test workout; check it in Garmin Connect and, where applicable, on your device. | Workout integration validation, one test per supported sport | Verified external publication and device compatibility for that sport |
| U8 | Enter inputs needed for nutrition targets in the app, and review initial targets. Supply known portions/labels for a few meals if you want validation against your own food. | Nutrition feature use and personal validation | Personalized targets; food logging and synthetic meal tests can continue |
| U9 | If the chosen free food API requires a personal key, create it and enter it locally. I will first evaluate whether a free downloadable database avoids this step. | Only if the API route is selected | Online food lookup only; cached/manual food entry still works |
| U10 | Sign in to GitHub when you want the prepared project published. | Whenever you resume GitHub setup | GitHub publication only, not local development |
| U11 | Describe maintenance/replacements in chat when they happen, including the item, action, and date. Optional costs/part details can be added. | During app use, not before development | Only entries with missing essentials need clarification; no equipment inventory or new account required |

**Optional corrections, not blockers:** “Weekly calories” currently means Garmin calories burned; in-app status/local reminders are sufficient initially. Correct either interpretation if needed. Week start, units, and timezone will be editable settings. I can inspect this computer's hardware during feasibility; you only need to specify hardware if the app will run on a different computer.

## 2. What I will handle without asking you to choose

- Project structure, free libraries, database design, migrations, import parsers, and API design.
- Local model selection based on measured speed and memory; OpenAI remains an explicit manual choice, never an automatic paid fallback.
- Dashboard components and the ability to add more graphs later.
- Reliable synchronization, deduplication, retries, and error reporting.
- Provider-neutral application tools, evidence-backed calculations, safe separation of queries from actions, and an optional MCP adapter for external clients.
- Automated tests, local packaging, documentation, and backup/restore validation.

Existing decisions remain settled: computer first, bulk import first, account-wide Garmin sync afterward, optional goals, saved training answers, a complete local no-fee path, optional manually selected OpenAI access, and acceptance of evaluating the community Garmin integration. I will not ask you to approve these again. Environment permission prompts may still be necessary for specific downloads or access outside the project.

## 3. Milestones and dependencies

| Milestone | Tasks | Reviewable result |
|---|---|---|
| M0 — Feasibility evidence | T1 | Hardware/model measurements and a Garmin import/integration capability report |
| M1 — Local data foundation | T2–T4 | History import, manual exports, backup/restore, and live/manual sync |
| M2 — First dashboard | T5 | Steps, last activity, weekly calories, and editable saved layout |
| M3 — Historical AI assistant | T6 | Questions about actual history, similar-ride comparisons, optional goal/profile editing |
| M3A — Maintenance history | T11 | AI-based maintenance/replacement logging, review/edit/undo, CSV portability |
| M4 — Local training | T7, T12 | Daily readiness, stored training context, reviewable local plans and feedback |
| M5 — Food and nutrition | T9 | Photo-assisted logging, editable estimates, daily targets and totals |
| M6 — Daily-use release | T10 | Explicit launch/quit, recovery and catch-up after reopening, reminders only during open app sessions |
| M7 — Garmin workout publishing, last | T8 | Verified publication only after the rest of the local app works |

**First useful release: M1–M3A**, after relevant feasibility checks. M4–M6 complete the local application; M7 adds Garmin workout publishing last. Background operation/automatic startup, phone access, WhatsApp, and AI-added dashboard graphs are later work. T11 is numbered separately to preserve existing task references, but executes alongside/after T6, before the daily-use release.

Dependency sequence: data foundation → import/sync → dashboard and historical analysis → local training and nutrition → daily-use validation → Garmin workout publishing (T8), last. U1 is complete, so the importer can now be developed and verified against the real archive. Live Garmin synchronization still waits for U2. Food logging can be developed independently once storage is ready. This describes task dependencies, not authorization to launch parallel agents.

Feasibility has separate gates: imports need a representative archive, live sync needs login, and local AI needs hardware benchmarking. A blocked gate must not stop unrelated work. An unavailable automatic integration remains an unmet requirement even when file import works; report the limitation and review options rather than declaring it complete.

## 4. Tasks and subtasks

Every item below is **not started** unless explicitly marked otherwise. The existing repository, README, and source plan are already prepared locally; this backlog adds no application code.

### T1 — Confirm feasibility

| Subtask | Work | Your involvement |
|---|---|---|
| T1.1 | Inspect OS, processor, memory, available disk, and local runtimes; record practical limits. | None on this computer; identify a different target computer if applicable |
| T1.2 | Inventory Garmin archive contents, formats, date ranges, and health/activity records. | U1 |
| T1.3 | Define Garmin Connect coverage by data type/date: available, absent from Garmin Connect, or unsupported by the integration. Device/sensor origin is irrelevant to ingestion. | None |
| T1.4 | Test Garmin login and a small read-only health/activity query. Record authentication and retry behavior. | U2 |
| T1.5 | Benchmark free local text/tool and vision models; document download size, memory, speed, and failure cases. | None; no paid or cloud substitution |
| T1.6 | Inspect workout support for running, cycling, and strength. Prepare sample payloads without publishing. | None; external validation is T8/U7 |
| T1.7 | Produce a short feasibility report and identify anything that changes the agreed scope. | Review only if a real scope tradeoff is necessary |

Done when each major dependency has evidence or an explicit unresolved limitation. Do not postpone Garmin Connect data-format or integration limitations until the finished UI.

### T2 — Build the local foundation

| Subtask | Work | Your involvement |
|---|---|---|
| T2.1 | Set up backend/frontend, repeatable local commands, pinned dependencies, and synthetic fixtures. | None |
| T2.2 | Create schema/migrations for metrics, activities/samples, provenance, jobs, profile/goals, dashboard settings, plans, and nutrition. | None |
| T2.3 | Implement shared date/time/unit handling, validation, and source-aware calculations. | None; settings editable later |
| T2.4 | Add local file storage, credential-store integration, log redaction, and localhost-only access. | None for code; credentials entered by you during connection |
| T2.5 | Build basic navigation, empty/error states, and settings with optional goals and profile fields. | None |

Done when the app starts locally, saves/reloads synthetic data, and requires no Garmin account or goal to open.

### T3 — Implement bulk import and manual export

| Subtask | Work | Your involvement |
|---|---|---|
| T3.1 | Implement file selection, archive inventory, nested ZIP handling, and extraction limits. | None |
| T3.2 | Implement FIT, TCX, GPX, supported CSV, and schema-specific Garmin JSON parsers. | U1 for real schema verification |
| T3.3 | Normalize records, preserve originals/provenance, and reconcile duplicates across formats. | None |
| T3.4 | Add preview, progress, cancel/resume, partial failure handling, and import coverage report. | None |
| T3.5 | Add date-filtered CSV, versioned JSON, original-file downloads, full backup, and restore preview. | None |
| T3.6 | Validate repeated imports, corrupt files, large archives, ambiguous matches, and preservation of richer samples/user edits. | None for automated tests |
| T3.7 | Import your full history and compare sampled counts, dates, and values against source records. | U1; optional help resolving ambiguous source records |

Done when reimport creates no duplicates, unsupported records are visible, and backup restoration preserves relationships and settings. Test later-added training/nutrition records again when those modules exist.

### T4 — Implement Garmin synchronization

| Subtask | Work | Your involvement |
|---|---|---|
| T4.1 | Build account connection, token renewal, sign-out, and clear reconnect prompts. | U2 for live login |
| T4.2 | Retrieve supported health/activity data across the account; reconcile with imported history. | None once connected |
| T4.3 | Add **Sync now**, progress, last success, new/updated counts, failure details, and retry. | None |
| T4.4 | Implement per-Garmin-data-type coverage checkpoints, full-gap catch-up beyond 24 hours, overlap refresh, rate limits, single-job locking, and interrupted-job recovery. | None |
| T4.5 | Schedule sync only during open app sessions; catch up after reopening, sleep, or offline periods. Persist checkpoints and stop jobs on app exit. No closed-app execution or automatic startup. | None |
| T4.6 | Test duplicate prevention, delayed arrival of records in Garmin Connect, changed/deleted activities, expired sessions, and failures affecting individual data types. | U2 only if login renewal is required |
| T4.7 | Seed catch-up from the import coverage report; track successfully queried empty intervals separately from unchecked gaps. Commit each interval before advancing its checkpoint; leave failed intervals pending. | None |
| T4.8 | Detect source modifications using available updated-since support; otherwise combine recent overlap with resumable historical reconciliation and selectable recheck dates. Show coverage limits and do not claim all old edits are detected automatically. | None |
| T4.9 | Test 2-, 10-, and 30-day gaps, restart mid-catch-up, independent source failures, late older uploads, corrections outside overlap, and unchanged repeat runs. Exercise the same logic through scheduled sync and Sync now. | None for automated tests |

Done when synchronization covers the entire outstanding gap rather than a fixed previous-24-hour window, updates imported records without duplicates, and resumes uncompleted intervals after failure. Checkpoints must reflect verified fetch coverage, not simply the newest activity or the time a job started. Failures must not corrupt or erase stored data; deeper reconciliation must detect historical changes within the range it checks.

### T5 — Build the expandable dashboard

| Subtask | Work | Your involvement |
|---|---|---|
| T5.1 | Build cards for steps, last activity, and weekly calories burned. | None unless you correct the calorie interpretation |
| T5.2 | Add date filters, units, tooltips, missing-data gaps, source/freshness labels, and activity detail views. | None |
| T5.3 | Implement card/chart registry and saved add/remove/reorder settings. | None |
| T5.4 | Verify totals against source data, including week boundaries and timezone changes. | None |
| T5.5 | Present a usable version and record your requested dashboard improvements. | U5; preference feedback can come gradually |

Done when the three initial views are accurate and another supported graph can be added without rebuilding the dashboard.

### T6 — Add the historical AI assistant and optional MCP adapter

| Subtask | Work | Your involvement |
|---|---|---|
| T6.1 | Connect both selectable providers: OpenAI Responses API and Qwen through Ollama. Keep switching manual, load the local model on demand, and implement clear unavailable/slow-model states. | OpenAI API key supplied through the backend environment when cloud use is wanted |
| T6.2 | Implement scoped, provider-neutral application query tools and deterministic calculations over requested date ranges. Optionally expose selected tools through a local MCP adapter later. | None |
| T6.3 | Add streaming chat, source links, freshness, uncertainty, and refusal to invent missing values. | None |
| T6.4 | Implement similar-ride selection with visible criteria/tolerances and adjustable filters. | None; user can refine comparisons in the app |
| T6.5 | Assess ride effectiveness against recorded/session goals, with conditional answers when purpose is unknown. | Optional session intent in chat |
| T6.6 | Add optional goal/profile updates through chat using validated writes and the same storage as forms. | Optional goals entered during use |
| T6.7 | Test the plan's example questions, numeric accuracy, missing data, misleading imported text, and persistence of profile changes. | None for tests; optional feedback on answer usefulness |

Done when answers trace to actual records/calculations and goal-free use remains possible. AI creation of dashboard graphs stays deferred.

### T7 — Build personalized training planning

| Subtask | Work | Your involvement |
|---|---|---|
| T7.1 | Implement a short, context-aware questionnaire; save answers and ask only for missing/stale details. | U6 during use, not during development |
| T7.2 | Build structured strength, cycling, and running workout models and reusable templates. | None |
| T7.3 | Implement documented, testable progression/recovery rules and constraint checks. | None for implementation; respect U6 restrictions |
| T7.4 | Generate reviewable weekly plans and session explanations, with editing and substitutions. | U6 for personalized output |
| T7.5 | Track completion, perceived effort, soreness, missed sessions, and proposed revisions without silent schedule changes. | Brief feedback when using the app |
| T7.6 | Test schedule conflicts, unavailable equipment, missing goals, stale profile data, and incompatible restrictions. | None for tests |

Done when plans respect stored constraints, explain their rationale, and do not require repeating the questionnaire.

### T8 — Publish and schedule Garmin workouts

**Deferred to the final implementation stage by user decision (10 October 2026).** Complete T9 nutrition and T10 local lifecycle/recovery and normal-use checks first. The local app must work without workout publication. Existing Garmin data import/sync and local CSV/JSON/backup exports remain in their current scope. T8 retains its requirements and IDs; U7 is needed only when this final stage starts.

| Subtask | Work | Your involvement |
|---|---|---|
| T8.1 | Map each sport's structured sessions into supported Garmin workout fields; flag unsupported representations. | None |
| T8.2 | Build preview, publish, schedule, read-back verification, and separate creation/scheduling statuses. | None for implementation |
| T8.3 | Store remote IDs and handle retry, edits, rescheduling, and explicit removal without duplicates. | None for implementation |
| T8.4 | Validate one representative workout for each supported sport in Garmin Connect and on the relevant device. | U7; U2 if disconnected |

Done per sport only after actual verification. A calendar entry alone does not establish that the device can execute every workout step.

### T9 — Add food logging and nutrition status

| Subtask | Work | Your involvement |
|---|---|---|
| T9.1 | Implement manual food entries, recipes, reusable meals, nutrient sources, and daily totals first. | None |
| T9.2 | Add photo upload, local vision analysis, proposed ingredients/portions, uncertainties, and editable confirmation. | None for implementation; confirm estimates during use |
| T9.3 | Integrate free nutrient lookup and caching; assess API versus downloadable database. | U9 only if needed |
| T9.4 | Add documented target calculations, training/rest-day handling, manual override, and target history without double-counting exercise. | U8 for personalized targets |
| T9.5 | Show target/logged/remaining calories and macros with clear distinction between estimated and measured quantities. | None |
| T9.6 | Validate known-portion meals, recipe scaling, edits, day boundaries, and nutrient totals. | Optional known-portion meals from U8; automated fixtures require no input |

Done when estimates can be corrected, totals are reproducible, and targets expose their assumptions. Photo estimates must not be presented as exact measurements.

### T10 — Prepare for everyday local use

| Subtask | Work | Your involvement |
|---|---|---|
| T10.1 | Provide launcher/start-stop instructions, helpful errors, and recovery after shutdown or failed migration. | None |
| T10.2 | Re-measure resource use with representative data and AI; optimize polling, job concurrency, and model unloading. | None |
| T10.3 | Implement explicit launch/quit and session lifecycle: closing the app stops its owned processes and saves checkpoints. Verify no service continues syncing after exit and no login autostart is installed. | None; U4 is deferred |
| T10.4 | Add configurable in-app status and optional reminders only while the app session is open. No reminders after exit. | Choose reminders if wanted; otherwise leave disabled |
| T10.5 | Verify export/delete controls, secret exclusion, and full backup/restore across all completed modules. Document local storage protection. | None; any OS security-setting change is a separate user decision |
| T10.6 | Run a normal-use trial covering sleep/wake, offline access, login expiry, interrupted import/sync, and retained settings. | Your usability feedback; I handle technical validation |

Done when everyday recovery works and no ongoing paid service is needed. Verify that app-owned processes stop on exit, no sync/reminders run while closed, and reopening catches up from durable checkpoints. The browser-based implementation needs a launcher-managed session and explicit Quit action; closing that app session must shut down its services. Do not terminate unrelated user-managed processes. Background operation is excluded from this edition.

### T11 — Maintenance and accessory replacement log

**Complete — 10 October 2026.** T11.1–T11.8 are implemented and verified; see [`../status/t11-verification.md`](../status/t11-verification.md) and the detailed status tracker. User maintenance details are supplied during normal use.

Depends on T2 storage and T3 export/backup services; AI prompt execution depends on T6. It does not depend on the Garmin export, Garmin login, or device/sensor inventory. Include this module in T10's final backup and daily-use checks.

**Execution method:** Store authoritative records in the existing local SQLite database. Common maintenance chat commands resolve locally into structured, validated application services shared by both provider modes; imported/model-generated text cannot authorize writes. An optional MCP adapter can expose selected tools to external AI clients without becoming an in-app dependency. Provide CSV import/export for spreadsheet use and portability. A CSV export is a snapshot. This adds no paid dependency.

| Subtask | Work | Your involvement |
|---|---|---|
| T11.1 | Add equipment labels, maintenance/replacement events, required item/action/date fields, optional details, stable IDs, and revision history. | None; labels created as needed during use |
| T11.2 | Implement structured extraction from prompts; resolve relative dates in local timezone and ask only about missing essentials. Distinguish completed events from questions or future plans. | U11 during use |
| T11.3 | Add validated log/list/update/undo/export tools and operation IDs that prevent duplicate writes on retries. Display the saved result with Edit/Undo. | None |
| T11.4 | Build Maintenance history screen with date/item/category filters, editable records, and recoverable deletion. | None |
| T11.5 | Answer history questions from stored records; support multiple entries per prompt and cost totals separated by currency. | None; clarification only for ambiguous equipment/record references |
| T11.6 | Implement UTF-8 CSV import/export with documented columns, ISO dates, optional units/currency, quoting, spreadsheet-safe text, mapping preview, validation, and duplicate/conflict handling. | None; optional existing CSV if you already keep a log |
| T11.7 | Add maintenance data and revisions to JSON exports and full backup/restore; keep CSV snapshots separate from revision backups. | None |
| T11.8 | Test clear/ambiguous prompts, date boundaries, backdating, multiple entries, corrections/undo, retried requests, similar but distinct events, special text, CSV round trips, and full restoration. | None for automated tests; optional usability feedback |

Acceptance examples:

- “Log that I replaced the chain on my road bike today” saves one replacement with the exact local date and no invented cost.
- “Log a tire replacement yesterday” asks which item/equipment if that cannot be resolved, then saves after the answer.
- “I should replace my chain” does not create a completed service record.
- “Change the cost of the last chain replacement to 45 euros” updates the intended record, retaining revision history and undo.
- “When did I last replace my rear tire?” retrieves the matching event or explains that no matching record exists.
- Exporting and reimporting an unchanged maintenance CSV creates no duplicates; a conflicting edit is shown for resolution.

Done when chat can log/query/correct records reliably, users can inspect the history, and CSV/backup round trips preserve the documented data. Automatic maintenance reminders and activity-derived usage are not needed for completion.

### T12 — Daily training readiness

Build an original, transparent readiness metric from locally stored data. Do not claim to reproduce Garmin, Fitbit, or another vendor's proprietary algorithm. During implementation, review current public research and official metric definitions, cite the chosen basis, and keep the calculation inspectable and versioned.

| Subtask | Work | Your involvement |
|---|---|---|
| T12.1 | Define and document a 0–100 readiness model using HRV relative to the user's baseline, sleep score, sleep duration, time since the last training session, recent training load, and resting heart rate relative to baseline. | None; optional feedback on whether the result feels useful |
| T12.2 | Establish personalized rolling baselines, minimum history requirements, component weights, caps, and recovery windows. Keep every assumption configurable and version the formula so historical scores remain explainable. | None |
| T12.3 | Compute one morning score with low/medium/high readiness bands, component contributions, source dates, freshness, and confidence. Degrade confidence visibly when inputs are missing or stale rather than inventing values. | None |
| T12.4 | Add a dashboard card and trend view showing today's score, the main positive/negative contributors, available history, and a plain-language explanation. Recalculate safely after corrected or late Garmin data arrives. | U5 feedback can refine the presentation |
| T12.5 | Make readiness available to the AI assistant and later training planner as advisory evidence. It may support a suggestion to reduce or increase intensity, but must not silently alter a plan or present medical advice. | Optional confirmation before changing a planned session |
| T12.6 | Test normal recovery, poor sleep, suppressed HRV, elevated resting heart rate, heavy recent load, long rest, missing metrics, insufficient baseline, timezone boundaries, late data, and formula-version changes. Compare behavior with recognizable trends without treating a vendor score as ground truth. | None for automated tests; optional real-use feedback |

Done when the morning score is reproducible from displayed inputs, explains why it changed, remains usable with partial data, and is clearly labeled as this app's readiness estimate rather than a Garmin/Fitbit score.

## 5. Deferred backlog

| ID | Later work | Your input when revisited |
|---|---|---|
| F6 | Decide whether to add background operation and automatic startup, then define resource limits if wanted | U4, only in a later iteration |
| F1 | More health/training/nutrition graphs | Which information you find useful after using the basics |
| F2 | Create/edit dashboard charts through AI, using validated chart configurations | Examples of the graph requests you want |
| F3 | Phone connectivity | Home-network only or access away from home |
| F4 | WhatsApp or other messaging | Whether it is still wanted and can satisfy the free-only requirement |
| F5 | Publish the local project to GitHub | U10; no application work depends on this |

## 6. Suggested review

Review the milestone order and the input table first. There is no need to answer the future training or nutrition questions now. **U1, the full Garmin export, is available and its initial inventory is complete.** Garmin login is needed later for live validation. Hardware information can be inspected locally.

After this backlog is accepted and implementation is requested, I can start the foundation and synthetic-data work while the archive is being prepared. I will ask for user-only actions at the point they become necessary, continue independent work when possible, and keep unresolved requirements visible.
