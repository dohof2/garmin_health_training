# Personal Health & Training App — Review Plan

Date: 19 September 2026  
Status: Draft for your review. Implementation has not started.

**Goal:** Build a local application personalized to your health, training, nutrition, schedule, and goals. It should combine Garmin history, useful graphs, an AI assistant, training planning, and food tracking while targeting zero recurring service fees.

## 1. Proposed experience

Open the app to see today's health summary, planned workout, and food targets. Explore your history in graphs, ask questions about your data, review proposed training changes, and send selected workouts to Garmin Connect. Add a meal photo, correct the estimated ingredients and portions, and see your updated calorie and macro totals.

On first use, choose **Import Garmin history** to upload your full Garmin account export and build your historical database. Manual import and export remain available afterward. Use a visible **Sync now** button whenever you want fresh Garmin data.

Start with a browser-based app running on your own computer. Your database, photos, and application server stay local by default. Internet access is still required to synchronize with Garmin and use optional external services. A desktop launcher can come later.

## 2. Scope and feasibility

| Your requirement | Planned solution | Dependency or limitation |
|---|---|---|
| Daily Garmin health and activity data | Scheduled synchronization, manual refresh, and historical import | First prove account access and metric availability |
| Manual import and export | First-use Garmin archive import, individual-file imports, and portable data exports | Validate actual archive layouts and report unsupported or incomplete records |
| Graphs of the data you want | Customizable dashboard, date filters, comparisons, activity details | Agree on your priority metrics; some depend on device support |
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

## 3. Personalization to define before implementation

No personal targets or training assumptions are set in this plan. The onboarding profile should collect:

- Main priority: general health, endurance performance, strength, body composition, an event, or a combination.
- Sports, training history, current weekly workload, and preferred training days and duration.
- Equipment: gym/home equipment, bike/trainer, power meter, heart-rate sensor, and Garmin device model.
- Relevant limitations, injuries, recovery preferences, and any clinician-provided restrictions.
- Age, height, weight, units, and other inputs needed by the selected nutrition calculations; sensitive inputs remain optional where possible.
- Dietary preferences, allergies, usual foods, and desired weight trend, if any.
- Local timezone, preferred language, dashboard metrics, and notification preferences.

The user can edit this profile, correct imported values, and override proposed goals. Keep a history of target changes so past charts remain interpretable.

## 4. Features

### A. Garmin data and reliability

- Attempt a daily sync at a configurable time; refresh on demand and catch up after the computer wakes or reconnects.
- Add a prominent **Sync now** button on Today and the data-management screen. Show progress, last successful sync, new/updated record counts, and errors with a retry action. Prevent overlapping sync runs; request login renewal when necessary.
- Prefer a full-history file import during onboarding, with no 90-day restriction. For users starting through the online connection, initially retrieve 90 days and offer a longer backfill where available. Keep backfills resumable and rate limited.
- Candidate health metrics: steps, resting heart rate, sleep, HRV, stress, Body Battery, weight, and energy expenditure.
- Candidate training metrics: sport, duration, distance, pace/speed, heart rate, power, elevation, cadence, and available load/recovery metrics.
- Build a device/account capability list instead of promising every metric.
- Preserve source identifiers, units, timestamps, timezone, and available raw records. Normalize data for charting.
- Re-fetch recent days to capture late device syncs. Update existing records without duplicates; support deleted or corrected activities.
- Show last successful sync, partial failures, missing data, and login renewal needs. Never display missing data as zero.

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

Suggested graphs: sleep and resting-heart-rate trends; HRV where available; weekly volume by sport; pace/power and heart rate within activities; strength progression by exercise; weight trends; and calories/protein/fat/carbohydrates consumed against targets.

Include 7/30/90-day and custom ranges, units, tooltips, source labels, missing-data gaps, and CSV export. Show overlapping trends without claiming one caused another. Let the user choose and reorder dashboard cards.

### C. AI assistant with access to history

Example questions:

- “How has my running volume changed over the last eight weeks?”
- “Compare my sleep before my best and worst rides.”
- “How was my ride compared to other rides with the same attributes?”
- “Was this ride effective? In what way?”
- “What did I eat yesterday, and how much protein did I log?”
- “Propose a week with two strength sessions and three rides.”

The assistant should retrieve only relevant date ranges and summaries. Application code performs calculations; the model explains results. Answers include the period, source metrics, data freshness, and links to the relevant graph or records. Distinguish observations, estimates, and suggestions. Say when evidence is insufficient.

For ride comparisons, select similar historical rides using explicit attributes: indoor/outdoor, ride type, duration, distance, elevation/route, and intended intensity; consider equipment and weather only when recorded. Show the matching criteria, tolerances, number of matches, and linked rides, and allow the user to adjust them. Compare available power, pace/speed, heart rate, cadence, and perceived effort without treating unlike conditions as equivalent.

For effectiveness, assess the ride against its intended goal and the user's current plan—for example, endurance volume, interval completion, or a recovery session. Explain which recorded measures support the assessment, what benefit is only inferred, and what is missing. If the goal is unknown, ask for it or make the assessment conditional. A single ride cannot establish long-term improvement; evaluate that separately through historical trends.

Do not give the model unrestricted database writes or shell access. Keep read-only analysis separate from actions such as saving a plan or publishing workouts. Treat text inside imported records as data, not instructions.

### D. Personal training planner

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

WhatsApp remains an optional later phase. Its official business platform uses message pricing, so a permanently free bot cannot be promised. Recheck account setup, message policy, pricing, and public HTTPS webhook requirements before choosing it. Do not base the app on unofficial WhatsApp account automation. [WhatsApp pricing](https://business.whatsapp.com/products/platform-pricing)

## 5. Proposed technical design

These are design choices to review, not installed components.

| Component | Proposed choice | Purpose |
|---|---|---|
| Interface | React + TypeScript with a chart library | Interactive dashboard, meal review, chat, and calendar |
| Local backend | Python + FastAPI | Data integration, calculations, planning, and action validation |
| Database | SQLite with migrations | Simple single-user local storage |
| Files | Local application data folder | Photos, imports, and recoverable exports |
| Background work | Persistent job records plus a local scheduler | Daily sync, retries, and catch-up |
| AI runtime | Ollama with a locally runnable text/tool model and vision model | Avoid recurring inference fees; benchmark before model selection |
| MCP | One application-owned local MCP server | Narrow, validated access to data and actions |
| Secrets | Operating-system credential store | Garmin session tokens and optional API keys |

Ollama supports image input with compatible vision models, but food recognition quality and speed need testing on your hardware. [Ollama vision documentation](https://github.com/ollama/ollama/blob/main/docs/capabilities/vision.mdx)

The app backend acts as the AI host/MCP client. Its local MCP server calls the same application services used by the interface. Proposed tools include `get_health_summary`, `compare_periods`, `list_activities`, `get_nutrition_status`, `draft_training_week`, `save_confirmed_meal`, and `publish_approved_workout`. Write actions require validated inputs and the relevant user action recorded by the application.

MCP connects an assistant to tools and data; it does not provide a model, free hosting, or Garmin authorization. Begin with a local process transport and avoid exposing MCP to the public internet. [MCP architecture](https://modelcontextprotocol.io/specification/2025-03-26/architecture/index)

Core records: user profile, daily metrics, activities and samples, strength sets, workouts and steps, scheduled sessions, meal items, nutrient references, daily targets, chat evidence, sync jobs, and action history.

## 6. Cost, privacy, and availability

**Recommended baseline: no paid cloud server and no paid AI API.** Run on your existing computer. Local models need sufficient memory and disk space; benchmark before committing to the full AI experience.

- The app can display stored data offline. Garmin updates and external food lookups need internet access.
- Automatic synchronization and reminders only run while the host computer is awake and the background service is running. Catch up after downtime.
- A phone interface and access away from home are separate deployment decisions. Localhost alone is not accessible from a phone. Secure remote access and an always-on host would require additional setup.
- Free cloud hosting is optional, not a core dependency: quotas, sleeping services, and storage limits must be checked against the selected provider.
- A free hosted AI tier is not the default for personal health data. For example, Google's pricing page lists product-improvement use for free-tier content. Any cloud option needs a review of current terms and an explicit choice about what data leaves the computer. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Bind the app to localhost by default. Protect tokens, redact logs, provide delete/export controls, and support local backups with a tested restore process. SQLite is not encrypted by default; choose disk or database encryption during setup.

## 7. Build phases and completion gates

| Phase | Work | Complete when |
|---|---|---|
| 0 — Decisions and feasibility | Confirm hardware/profile; inspect a representative full Garmin export and its schemas; test Garmin login, history, per-sport publishing; benchmark local AI | A capability matrix documents import-format and health/activity coverage, what works, what fails, and any revised scope |
| 1 — Data foundation | Local app, storage, profile, full-history manual import, manual exports, daily sync, Sync now button, retries | Supported archive/file fixtures import correctly; repeat imports and subsequent sync create no duplicates; source totals match sampled Garmin days; jobs resume; export/restore preserves records and relationships |
| 2 — Graphs | Customizable dashboard and activity/history views | Agreed metrics render correctly across dates, units, timezones, and missing days |
| 3 — AI history assistant | MCP tools, grounded answers, evidence links, similar-ride comparison, goal-based ride assessment | Historical answers match independent calculations; ride matches expose criteria; effectiveness answers cite goals/evidence and handle insufficient data |
| 4 — Training and Garmin | Weekly planning, feedback, calendar, publish/read-back workflow | Each supported sport completes a verified publish/schedule test; retries do not duplicate sessions |
| 5 — Food and nutrition | Photo review, nutrient lookup, manual logging, target calculation | Known-portion meals assess estimate quality; edits and daily totals calculate correctly; uncertainty stays visible |
| 6 — Daily-use finish | Launcher/background startup, backup/restore, reminders; optional phone/WhatsApp | A week of normal use survives sleep, network loss, expired sessions, and restart without lost entries |

For phase 0, any external test workout should be previewed and deliberately published through a user action. No account access or external write is part of this planning task.

**First useful release:** phases 0–3: full-history manual Garmin import, manual exports, daily and on-demand synchronization, graphs, and questions about your own data including ride comparison and effectiveness. All original capabilities remain in the full scope; training publication and food tracking follow once the data foundation works.

Avoid a firm delivery estimate until phase 0 resolves the biggest risks: Garmin compatibility and local model performance. Test with synthetic fixtures first and a small sample of your actual data during integration validation.

## 8. Your review checklist

Please add answers or comments below; these decisions are intentionally open.

1. **Computer:** Operating system, processor, memory, and whether it can stay on for background sync.
2. **Garmin:** Watch/bike-computer models, sensors, and how much historical data you want.
3. **Top goals:** Your priorities across health, strength, cycling, running, and nutrition.
4. **Dashboard:** Which metrics and graphs matter most to you?
5. **Training:** Days/hours available, equipment, experience, and relevant limitations.
6. **Access:** Computer only, phone at home, or access from anywhere?
7. **Budget/privacy:** Strictly zero recurring fees and local AI, or optional cloud services if local performance is insufficient?
8. **Messaging:** Are in-app status and local reminders enough initially, or is WhatsApp essential?
9. **Garmin route:** Are you comfortable evaluating a community integration, knowing it can require maintenance?

**Next step after review:** Revise this plan around your answers, then begin the agreed feasibility work. No application code, dependency installation, account connection, or deployment has been performed.
