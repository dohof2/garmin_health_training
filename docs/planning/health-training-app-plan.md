# Personal Health & Training App — Review Plan

Date: 19 September 2026  
Status: Revised with your review decisions. Application implementation has not started.

**Goal:** Build a local application personalized to your health, training, nutrition, schedule, and goals. It should combine Garmin history, useful graphs, an AI assistant, training planning, and food tracking using strictly free software and services for the current version, with no paid subscriptions, servers, or AI APIs.

## 1. Proposed experience

Open the app to see today's health summary, planned workout, and food targets. Explore your history in graphs, ask questions about your data, review proposed training changes, and send selected workouts to Garmin Connect. Add a meal photo, correct the estimated ingredients and portions, and see your updated calorie and macro totals.

On first use, choose **Import Garmin history** to upload your full Garmin account export and build your historical database. Manual import and export remain available afterward. Use a visible **Sync now** button whenever you want fresh Garmin data.

Start with a browser-based app running on your own computer. The first edition runs only during an explicitly opened app session: no background operation, hidden service, or automatic startup. Closing the app ends its managed processes; merely minimizing the app does not close the session. The launcher must provide an explicit Quit action and ensure closing the app session shuts down its services. Your database, photos, and application server stay local by default. Internet access is still required to synchronize with Garmin and use optional external services. A desktop launcher can come later.

## 2. Scope and feasibility

| Your requirement | Planned solution | Dependency or limitation |
|---|---|---|
| Daily Garmin health and activity data | Scheduled synchronization, manual refresh, and historical import | First prove account access and metric availability |
| Manual import and export | First-use Garmin archive import, individual-file imports, and portable data exports | Validate actual archive layouts and report unsupported or incomplete records |
| Maintenance and accessory replacement log | Record, correct, and query equipment history through AI chat; import/export CSV | Recommended storage: local SQLite, with portable CSV exports |
| Graphs of the data you want | Customizable dashboard, date filters, comparisons, activity details | Show the metrics available through Garmin Connect |
| AI questions about current and historical data | Chat connected to verified local data queries through MCP | Model performance depends on your computer |
| Personalized strength, cycling, and running plans | Profile, training calendar, structured sessions, feedback, and adaptive proposals | Requires your goals, availability, experience, and constraints |
| Schedule sessions in Garmin Connect | Preview, publish, schedule, and verify supported workouts | Test each sport and your device; calendar entry does not guarantee device delivery |
| Food logging from pictures | Food recognition, portion estimate, nutrient lookup, editable meal log | Pictures cannot reliably reveal exact portions or hidden ingredients |
| Daily nutrition goals and live status | Daily targets, consumed/remaining totals, optional reminders | Targets are estimates; WhatsApp is an optional integration |
| Free servers and MCP | Local server, SQLite, local model, and a narrow local MCP server | Existing hardware and electricity still have costs; free cloud tiers have limits |

### Garmin decision

Garmin's official Connect Developer Program includes health, activity, and training integrations, but its FAQ says the program is for business use. We must not assume a personal project can obtain access. [Garmin program FAQ](https://developer.garmin.com/gc-developer-program/program-faq/)

The candidate for a personal prototype is the community-maintained `python-garminconnect` library. Its repository and examples expose data retrieval and workout upload/scheduling capabilities. This is an unofficial integration, so authentication, endpoint changes, and sport coverage must be validated before building the full app. Review the applicable service terms during that feasibility step. [Library](https://github.com/cyberjunky/python-garminconnect), [examples](https://github.com/cyberjunky/python-garminconnect/blob/master/demo.py)

Manual import and export are required features, independent of automatic Garmin access. A user must be able to initialize the app from a full Garmin account export without connecting an account. Activity-only exports may not contain daily wellness data; the import report must show what was present and processed. Automatic synchronization remains a separate requirement. Manual workout entry is a fallback if Garmin publishing is unavailable.

## 3. Personalization inside the application

Users can import and explore data without setting a goal or completing a training questionnaire. Goals are optional and can be created, changed, or removed in the app or through AI chat. Both routes update the same persistent profile, show what was saved, and allow corrections.

Before answering a personalized training request, ask concise questions for the missing information needed for that request. Save the answers locally and reuse them in future sessions. Ask again only when details are missing, outdated, or the user wants to change them. Historical-data questions do not require training setup.

The profile can collect progressively:

- Main priority: general health, endurance performance, strength, body composition, an event, or a combination.
- Sports, training history, current weekly workload, and preferred training days and duration.
- Training equipment available for workout planning, such as gym/home equipment or a bike/trainer. No device or sensor inventory is required for data ingestion.
- Relevant limitations, injuries, recovery preferences, and any clinician-provided restrictions.
- Age, height, weight, units, and other inputs needed by the selected nutrition calculations; sensitive inputs remain optional where possible.
- Dietary preferences, allergies, usual foods, and desired weight trend, if any.
- Local timezone, preferred language, dashboard metrics, and notification preferences.

The user can edit this profile, correct imported values, and override proposed goals. Keep a history of target changes so past charts remain interpretable.

## 4. Features

### A. Garmin data and reliability

- Attempt a daily sync only while the app session is open; refresh on demand and catch up when the app is reopened or reconnects. No sync runs after the app is closed.
- Add a prominent **Sync now** button on Today and the data-management screen. Show progress, last successful sync, new/updated record counts, and errors with a retry action. Prevent overlapping sync runs; request login renewal when necessary.
- Initialize history through a bulk Garmin export import, with no 90-day restriction. Afterward, retrieve new and updated Garmin Connect data using the last successful sync and a recent overlap window. Keep import and catch-up jobs resumable and rate limited.
- Garmin Connect is the sole data source, both through its export files and online synchronization. Import the available account data regardless of which device or sensor produced it. Do not require device identification, a sensor inventory, or per-device validation. Check coverage by Garmin data type and date range, deduplicate Garmin records, and report fields the integration cannot retrieve.
- Candidate health metrics: steps, resting heart rate, sleep, HRV, stress, Body Battery, weight, and energy expenditure.
- Candidate training metrics: sport, duration, distance, pace/speed, heart rate, power, elevation, cadence, and available load/recovery metrics.
- Build a list of available Garmin Connect data types instead of promising every metric.
- Preserve source identifiers, units, timestamps, timezone, and available raw records. Normalize data for charting.
- Re-fetch recent days to capture late device syncs. Update existing records without duplicates; support deleted or corrected activities.
- Show last successful sync, partial failures, missing data, and login renewal needs. Never display missing data as zero.

#### Synchronization must cover the entire gap

Synchronization must inspect stored coverage and the last successfully fetched and committed interval for each Garmin Connect data type. Fetch every missing interval through the current time, even when the gap exceeds 24 hours. A daily schedule controls when the job runs, not how much history it retrieves. For example, after ten days offline, the next run must catch up all ten days, plus a configurable overlap for late uploads and corrections.

Keep separate timestamps for the last attempt, last successful job, source record time/update time when available, and verified fetch coverage. The most recent activity timestamp alone is not a safe checkpoint: older days or other data types may still be missing. Advance a coverage checkpoint only after a complete interval has been fetched and saved successfully. Preserve unresolved gaps and resume them after partial failure; successful activity retrieval must not mark failed wellness retrieval as complete.

After the first bulk import, use its per-data-type coverage report to identify the online catch-up range. Do not treat the import date or the newest imported record as proof that all history is complete. Distinguish days successfully queried with no records from days not yet checked.

Where Garmin exposes updated-since queries or modification timestamps, use them to retrieve corrections regardless of activity date. Otherwise, re-fetch a recent overlap and provide resumable historical reconciliation with a selectable date range, plus periodic deeper checks while the app runs. A short overlap cannot guarantee detection of arbitrarily old edits or late uploads; show the historical range last checked and any source limitations. Update matching records without duplication and preserve user corrections. Do not infer deletion from a failed or incomplete response.

Required verification: gaps of 2, 10, and 30 days; interruption halfway through catch-up; one data type failing while another succeeds; a late-uploaded older activity; a corrected record outside the recent overlap; and repeated synchronization with no changes. Manual **Sync now** and scheduled synchronization must use the same catch-up logic.

#### Required manual import and export

Provide an **Import / Export** screen with drag-and-drop or file selection, including multiple files and large historical archives. Process uploads locally; a Garmin login is not required for file import.

Garmin documents a full account export, original FIT activity files within ZIP archives, individual TCX/GPX exports, and CSV exports for activity summaries and reports. These formats contain different levels of detail. [Garmin export instructions](https://support.garmin.com/en-IE/marine/faq/W1TvTPW8JZ6LfJSfK512Q8/)

| Import format | Required processing |
|---|---|
| Garmin full-account ZIP archive, including nested ZIPs | Discover and inventory files, process supported activity and wellness records, and preserve a report of unsupported files; accept multiple archive parts |
| FIT | Read activity summaries, laps, and available samples such as heart rate, power, cadence, and GPS; identify record types before parsing |
| TCX | Read available activity, lap, and trackpoint data |
| GPX | Read available routes/tracks, timestamps, elevation, and recognized sensor extensions; do not invent absent metrics |
| CSV | Parse supported Garmin activity-summary and health/report layouts, with preview, units, date formats, and column mapping when needed |
| JSON records within account exports | Add schema-specific parsers for relevant health/activity history after inspecting representative export files; do not assume all JSON files share one schema |

The full-account archive is the primary first-use path. Phase 0 must inspect a representative export and document coverage of its health and activity records before claiming full-history support. Preserve unrecognized source files for later parser upgrades; disclose unprocessed data rather than silently skipping it.

Import workflow: select files → inspect formats and date coverage → preview counts and issues → import → show imported, updated, duplicate, unsupported, and failed counts. Support progress, cancellation, and resuming large jobs. Validate archive paths and impose extraction-size limits. A corrupt file should be isolated and reported without losing successfully processed records.

Deduplicate across repeated imports, different file formats, and later online sync using source identifiers plus conservative fallback matching. Preserve richer samples and user corrections; flag ambiguous matches instead of merging distinct activities. Keep source-file provenance and import-job history.

Required exports:

- **CSV:** Selected date ranges of health metrics, activity summaries, training logs, and nutrition records for spreadsheet use.
- **JSON:** Structured app data with units, timestamps, identifiers, and schema version for portability.
- **Full backup ZIP:** A restorable app dataset plus original imported files and optionally meal photos; exclude credentials and session tokens. Provide a restore preview and verify round-trip recovery.
- **Original activity files:** Download preserved FIT/TCX/GPX source files individually or in a ZIP. Do not promise a newly generated FIT/TCX/GPX file when the original is unavailable.

CSV/JSON exports are app data exports; they are not a promise that Garmin can reimport every exported record. Garmin workout publishing remains the separate workflow below.

### B. Graphs and dashboard

Provide Today, Health, Activities, Training Calendar, Nutrition, and Ask My Data screens.

Initial dashboard: **steps**, **last activity**, and **weekly calories**. Show today's step count with a recent trend, the latest activity with key available details, and a daily calorie graph with a weekly total. Working interpretation: weekly calories means Garmin-reported energy expenditure, with total/active/resting labels where available, rather than food intake. Keep this definition and week boundary adjustable.

Use reusable cards and chart definitions with saved layout, metric, aggregation, date range, and filters. Users can add, remove, and reorder supported cards. Register new metrics and chart types without redesigning the whole dashboard. Persist settings across restarts and include them in backups.

Add further graphs iteratively based on actual use. Future candidates: sleep and resting-heart-rate trends; HRV where available; weekly volume by sport; pace/power and heart rate within activities; strength progression by exercise; weight trends; and calories/protein/fat/carbohydrates consumed against targets.

Include 7/30/90-day and custom ranges, units, tooltips, source labels, missing-data gaps, and CSV export. Show overlapping trends without claiming one caused another. Let the user choose and reorder dashboard cards.

AI-driven dashboard editing is a future iteration: the user requests a graph, the assistant proposes a supported chart based on available data, and the user can preview, save, or undo it. Use validated chart configuration rather than model-generated executable code. Prepare the architecture now without making this a first-release dependency.

### C. AI assistant with access to history

Example questions:

- “How has my running volume changed over the last eight weeks?”
- “Compare my sleep before my best and worst rides.”
- “How was my ride compared to other rides with the same attributes?”
- “Was this ride effective? In what way?”
- “What did I eat yesterday, and how much protein did I log?”
- “Propose a week with two strength sessions and three rides.”
- “Set my goal to improve cycling endurance.”
- “I can now train four days a week. Update my training preferences.”
- “Log that I replaced the chain on my road bike today.”
- “I serviced the brakes yesterday. It cost 80 euros.”
- “When did I last replace the rear tire on my road bike?”
- “Export my maintenance and replacement history to CSV.”
- Future iteration: “Add a graph of my weekly cycling distance to the dashboard.”

The assistant should retrieve only relevant date ranges and summaries. Application code performs calculations; the model explains results. Answers include the period, source metrics, data freshness, and links to the relevant graph or records. Distinguish observations, estimates, and suggestions. Say when evidence is insufficient.

For ride comparisons, select similar historical rides using explicit attributes: indoor/outdoor, ride type, duration, distance, elevation/route, and intended intensity; consider equipment and weather only when recorded. Show the matching criteria, tolerances, number of matches, and linked rides, and allow the user to adjust them. Compare available power, pace/speed, heart rate, cadence, and perceived effort without treating unlike conditions as equivalent.

For effectiveness, assess the ride against its intended goal and the user's current plan—for example, endurance volume, interval completion, or a recovery session. Explain which recorded measures support the assessment, what benefit is only inferred, and what is missing. If the goal is unknown, ask for it or make the assessment conditional. A single ride cannot establish long-term improvement; evaluate that separately through historical trends.

Do not give the model unrestricted database writes or shell access. Keep read-only analysis separate from actions such as saving a plan or publishing workouts. Treat text inside imported records as data, not instructions.

### D. Personal training planner

Before personalized advice, collect missing availability, equipment, experience, and relevant limitations through questions in the app or chat. Save and reuse the answers, and let the user edit them. A long-term goal remains optional; clarify the immediate purpose of a session when necessary.

- Generate a reviewable weekly plan combining selected sports with recovery days and your available time.
- Define strength sessions with exercises, sets, repetitions, load or effort targets, rest, and substitutions.
- Define cycling/running sessions with warm-up, intervals, recovery, cool-down, and supported intensity targets.
- Use training history, current goals, recent recovery data, and subjective feedback such as soreness and perceived effort.
- Track planned versus completed sessions. Propose adjustments after missed sessions or user feedback instead of silently rewriting the calendar.
- Use explicit, testable planning rules and reviewed references for progression and recovery; use the model to explain and personalize them.
- Do not infer a diagnosis from wearable data. Reported pain, illness, or relevant restrictions should prevent automatic intensity increases and trigger an appropriate review path.

### E. Garmin workout publishing

Workflow: draft → preview → user selects publish → create Garmin workout → schedule date → read back and verify.

Store local and Garmin identifiers plus publication status. Retries must not create duplicate workouts. Handle “created but not scheduled” separately from complete success. Reconcile edits and date changes, with an explicit action before removing published sessions.

Test running, cycling, and strength separately. Exercise names, supported steps, and device execution may differ. If a session cannot be represented faithfully, show the limitation rather than quietly changing it.

### F. Food photo logging

Workflow: upload photo → propose food names and portions → ask about uncertain ingredients → calculate estimates → user corrects/confirms → save meal.

Store food name, portion, calories, protein, fat, carbohydrates, timestamp, nutrient source, and an uncertainty indication. Allow manual entries, packaged-food label values, recipes, and reusable meals.

Use a vision model for candidate food identification and a nutrient database for calculations where matches exist. USDA FoodData Central provides food search/details through an API with a key and rate limits; cache useful results locally. Regional and homemade foods may need manual recipes. [USDA API guide](https://fdc.nal.usda.gov/api-guide/)

Portion size, oils, and sauces are uncertain from a photo. Estimated meals remain visibly estimated, including in daily totals. Manual confirmation can correct an estimate but does not make it a measurement.

### G. Nutrition targets and status

Calculate an initial daily target from the completed profile using a documented method selected during implementation. Adjust proposals for goals and planned training, and calibrate against longer-term intake and weight trends when available. Avoid double-counting exercise energy already included in a daily energy estimate.

Show target, logged, and remaining calories and macros, with training/rest-day differences where appropriate. Preserve the target used on each day. Allow manual overrides and explain proposed changes. Initial targets and substantial changes should be reviewable.

Start with status inside the app and optional local reminders. “Live” means current as of the last food entry and Garmin sync, not continuous measurement.

In-app status and optional local reminders are enough initially (interpretation of review answer 8). Defer WhatsApp and phone connectivity to later iterations; any future messaging must fit the approved budget. WhatsApp remains optional. Its official business platform uses message pricing, so a permanently free bot cannot be promised. Recheck account setup, message policy, pricing, and public HTTPS webhook requirements before choosing it. Do not base the app on unofficial WhatsApp account automation. [WhatsApp pricing](https://business.whatsapp.com/products/platform-pricing)

### H. Maintenance and accessory replacement history

Use AI prompts to log equipment maintenance, repairs, and replacement of parts or accessories. Examples include a chain, tire, brake pads, running shoes, or an accessory battery. The log is local and user-entered. Garmin Connect remains the sole external health/activity source; this feature adds no device-integration requirement and does not require a full equipment inventory upfront.

**Recommended storage: SQLite as the authoritative log, plus CSV import/export.** Reuse the app's database so records have stable IDs, corrections are reliable, and chat/history/backup share the same data. CSV is the portable format for opening the log in a spreadsheet or keeping a separate copy. A CSV-only live database is not recommended because it makes concurrent edits, relationships, and recovery harder. This recommendation uses no paid service.

Logging workflow: user requests a log entry → AI extracts structured fields → ask only for missing/ambiguous essentials → validate and save through a dedicated tool → show the saved entry with Edit/Undo. A clear instruction to log something is sufficient; do not add an extra approval step for every ordinary entry. Questions, hypotheticals, and plans such as “I should replace my chain” must not be saved as completed maintenance.

Required fields: equipment/item label, work or replacement performed, and event date. Ask for a date when absent; resolve “today” and “yesterday” using the user's timezone and show the exact saved date. Create equipment labels as needed; clarify ambiguous labels without requiring manufacturer, model, or serial number. One-off accessories can be recorded without assigning them to a bike.

Optional fields: component/accessory, old and new part details, quantity, cost and currency, service provider, manually entered mileage/usage, and notes. Missing values stay unknown, not zero. Do not invent a price, currency, part model, mileage, or service interval. Store separate event time and record creation/update times, with stable record IDs and revision history.

Support multiple entries in one prompt, backdated records, corrections, recoverable deletion/undo, filtered history by equipment/date/category, and questions such as “What work did I do this year?” Aggregate costs separately by currency unless an explicit conversion is requested. Provide a simple Maintenance history screen for reviewing and editing entries as well as chat access.

CSV export must be available through a button or AI request, for all entries or a filtered range. Use UTF-8, consistent columns, ISO dates, units and currency fields, proper quoting, and spreadsheet-safe text handling. Suggested columns: `record_id`, `event_date`, `equipment`, `event_type`, `component`, `action`, `old_part`, `new_part`, `quantity`, `cost`, `currency`, `usage_value`, `usage_unit`, `provider`, `notes`, `created_at`, `updated_at`. Current-record CSV exports are for portability; full backups preserve revision history too.

CSV import includes a mapping/preview step, validation, duplicate detection, and a conflict report. Reimporting an unchanged app-generated CSV must not create duplicate records. Modified rows with existing IDs require an explicit merge decision rather than silently overwriting newer data. Exports are snapshots, not a live two-way link to externally edited files. Include maintenance records, equipment labels, and revisions in JSON exports and full backup/restore.

Initial scope is logging, history queries, corrections, and portability. Automated service reminders and Garmin-derived mileage since replacement are future options, not implied requirements; mileage calculations would need explicit assignment of activities to equipment.

## 5. Proposed technical design

These are design choices to review, not installed components.

| Component | Proposed choice | Purpose |
|---|---|---|
| Interface | React + TypeScript with a chart library | Interactive dashboard, meal review, chat, and calendar |
| Local backend | Python + FastAPI | Data integration, calculations, planning, and action validation |
| Database | SQLite with migrations | Simple single-user local storage |
| Files | Local application data folder | Photos, imports, and recoverable exports |
| In-session jobs | Persistent job records plus a scheduler active only during the open app session | Sync, retries, and catch-up; stop on app exit and resume pending work on reopening |
| AI runtime | Ollama with a locally runnable text/tool model and vision model | Avoid recurring inference fees; benchmark before model selection |
| MCP | One application-owned local MCP server | Narrow, validated access to data and actions |
| Secrets | Operating-system credential store | Garmin session tokens and optional API keys |

Ollama supports image input with compatible vision models, but food recognition quality and speed need testing on your hardware. [Ollama vision documentation](https://github.com/ollama/ollama/blob/main/docs/capabilities/vision.mdx)

The app backend acts as the AI host/MCP client. Its local MCP server calls the same application services used by the interface. Proposed tools include `get_health_summary`, `compare_periods`, `list_activities`, `get_nutrition_status`, `draft_training_week`, `save_confirmed_meal`, and `publish_approved_workout`. Write actions require validated inputs and the relevant user action recorded by the application.

MCP connects an assistant to tools and data; it does not provide a model, free hosting, or Garmin authorization. Begin with a local process transport and avoid exposing MCP to the public internet. [MCP architecture](https://modelcontextprotocol.io/specification/2025-03-26/architecture/index)

Core records: user profile and saved questionnaire answers, optional goals and their history, dashboard configurations, daily metrics, activities and samples, strength sets, workouts and steps, scheduled sessions, meal items, nutrient references, daily targets, equipment labels, maintenance/replacement events and revisions, chat evidence, sync jobs, and action history.

Maintenance MCP tools: `log_maintenance`, `list_maintenance`, `update_maintenance`, `undo_maintenance_change`, and `export_maintenance_csv`. They use validated application services and operation IDs so a retried tool call cannot duplicate an entry. A repeated real-world maintenance event remains a separate record; do not deduplicate solely by text similarity.

## 6. Cost, privacy, and availability

**Confirmed constraint: strictly free software and services at present.** No paid server, AI API, subscription, or automatic paid fallback. Run on existing hardware; no hardware purchase is assumed. Benchmark local models. If performance is insufficient, test smaller models or reduce workload rather than switch to a paid service. Existing hardware and electricity still consume resources.

- The app can display stored data offline. Garmin updates and external food lookups need internet access.
- Synchronization and local reminders run only while the computer is awake and the app session is open. No reminders or synchronization occur while the app is closed. Catch up from saved checkpoints on reopening; do not require the app to have been open within the last 24 hours.
- The first edition does not implement background operation or automatic startup. Revisit both in a later iteration. Measure resource consumption during ordinary app use, avoid continuous polling, run one heavy job at a time, and load/release app-owned models on demand. On exit, save checkpoints and stop app-owned processes; do not stop unrelated user-managed services.
- Computer-only access is the initial scope. Phone connectivity and remote access are deferred; no public server or phone setup is required now.
- Free cloud hosting is optional, not a core dependency: quotas, sleeping services, and storage limits must be checked against the selected provider.
- A free hosted AI tier is not the default for personal health data. For example, Google's pricing page lists product-improvement use for free-tier content. Any cloud option needs a review of current terms and an explicit choice about what data leaves the computer. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Bind the app to localhost by default. Protect tokens, redact logs, provide delete/export controls, and support local backups with a tested restore process. SQLite is not encrypted by default; choose disk or database encryption during setup.

## 7. Build phases and completion gates

| Phase | Work | Complete when |
|---|---|---|
| 0 — Decisions and feasibility | Confirm hardware; inspect a full Garmin export; test Garmin Connect data coverage and per-sport publishing; benchmark free local AI and in-session resource use | Capability matrix documents archive/data-type coverage and limitations; resource measurements document first-edition performance; no paid dependencies |
| 1 — Data foundation | Local app, storage, profile, full-history manual import, manual exports, daily sync, Sync now button, retries | Supported archive/file fixtures import correctly; repeat imports and subsequent sync create no duplicates; source totals match sampled Garmin days; jobs resume; export/restore preserves records and relationships |
| 2 — Graphs | Steps, last activity, weekly calories; reusable cards and saved configuration | Basic metrics handle dates, units, and missing data; layout survives restart/restore; adding a supported card requires no dashboard redesign |
| 3 — AI history assistant | MCP tools, grounded answers, ride comparisons/assessments, optional goal and profile updates through chat | Answers match independent calculations and expose evidence; goals can be skipped; form/chat edits share the same persisted profile |
| 3A — Maintenance log | Chat-based maintenance/replacement entries, history screen, corrections/undo, CSV import/export | Clear prompts save accurately; ambiguous prompts ask targeted questions; retries/reimports do not duplicate entries; CSV and backup round trips preserve records |
| 4 — Training and Garmin | Just-in-time training questions, saved answers, weekly planning, feedback, calendar, publishing | Missing context is requested before personalized advice and reused afterward; supported sports pass publication tests without duplicate sessions |
| 5 — Food and nutrition | Photo review, nutrient lookup, manual logging, target calculation | Known-portion meals assess estimate quality; edits and daily totals calculate correctly; uncertainty stays visible |
| 6 — Daily-use finish | Explicit launch/quit lifecycle, backup/restore, reminders during open sessions | App-owned processes stop on exit; no closed-app sync/reminders or login autostart; reopening resumes pending work and catches up all missing intervals |

**Later iterations:** Decide whether to add background operation and automatic startup; neither is included in the first edition. Additional dashboard metrics based on use, AI-added graphs, and phone connectivity; potentially messaging if compatible with the approved budget. These are outside the initial release.

For phase 0, any external test workout should be previewed and deliberately published through a user action. No account access or external write is part of this planning task.

**First useful release:** phases 0–3A: full-history manual Garmin import, manual exports, daily and on-demand synchronization, graphs, questions about your own data including ride comparison and effectiveness, and the maintenance/replacement log. Maintenance storage and its screen can be built once the data foundation exists; AI logging follows the local chat/tool integration. All original capabilities remain in the full scope; training publication and food tracking follow once the data foundation works.

Avoid a firm delivery estimate until phase 0 resolves the biggest risks: Garmin compatibility and local model performance. Test with synthetic fixtures first and a small sample of your actual data during integration validation.

## 8. Recorded review decisions

| Item | Decision |
|---|---|
| 1. Background operation | Excluded from the first edition. Run only during open app sessions; decide about background operation and automatic startup later. |
| 2. History and ongoing data | Bulk Garmin history import first, then synchronization from Garmin Connect as the sole source, regardless of the originating device or sensor. No device inventory is required. |
| 3. Goals | Optional; defined and updated by the user in the app or through AI chat. |
| 4. Dashboard | Start with steps, last activity, and weekly calories. Expand iteratively; design for future AI-added graphs. |
| 5. Training preferences | Ask for necessary information before personalized training advice; save and reuse the answers. |
| 6. Access | Computer first, phone connectivity later. |
| 7. Budget | Strictly free at present; no paid fallback. |
| 8. Messaging | In-app status and local reminders are sufficient initially, interpreting the user's “yes.” |
| 9. Garmin route | Community integration and its potential maintenance needs are accepted for evaluation. |
| 10. Maintenance log | Add AI-prompt logging of maintenance and accessory replacements. Recommended implementation: SQLite as the authoritative log with CSV import/export; no upfront equipment inventory required. |

Open details for feasibility: hardware specifications, representative Garmin archive and Garmin Connect data-type coverage, and whether weekly calories should use a different definition from the proposed energy-expenditure view. Personal goals and training preferences will be collected in the app when relevant, not as prerequisites for this plan.

**Garmin export status:** Received and inspected locally on 6 October 2026. The
original ZIP is excluded from Git and passed integrity and archive-safety checks.
Counts, coverage, and importer implications are recorded in
[`../status/garmin-export-inventory.md`](../status/garmin-export-inventory.md).

**Next step after review:** Begin feasibility work when requested. The repository and planning documents are prepared locally; application implementation and Garmin account connection have not started. GitHub publication is deferred.
