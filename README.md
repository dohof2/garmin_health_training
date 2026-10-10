# Garmin Health and Training

A planned local application for personal health, training, and nutrition, built around Garmin history and user-defined goals.

**Status: local foundation, full safe Garmin-history import, dashboard, and live synchronization are implemented.** The repository
contains a local React/TypeScript interface, a Python/FastAPI backend, a versioned
SQLite schema, and safe idempotent importers for Garmin activities, daily and
sleep metrics, GPX/TCX tracks, detailed activity FIT samples, and compact FIT
heart-rate/stress/respiration history, plus hydration, abnormal-heart-rate, and
daily Garmin nutrition JSON history. A final extended stage covers the
remaining training, biometric, workout, route, goal, gear, Golf, and Tacx data.
The dashboard includes real latest-step and activity cards, a gap-aware weekly
Garmin calories-burned card, reusable 30/90/all date filtering, expandable
activity details with explicit missing values, and a consolidated
coverage/failure view backed by durable import checkpoints. Date-filtered CSV,
versioned JSON, backup ZIP, restore preview, and preserved-original downloads
are available from the Import / Export screen. Live synchronization uses
private local Garmin authentication, per-data-type full-gap checkpoints, a
three-day overlap, restart recovery, historical reconciliation, and original
FIT detail retrieval with versioned session-summary recovery. Full queried source responses are retained locally; explicit activity load/effect and power/HR summary fields are normalized. It currently
refreshes activities, daily summaries, sleep, HRV, and weight/body-composition
data. Dashboard cards can be reordered, hidden, and
restored, with the saved layout persisted locally in SQLite. Activity calendar
dates follow the browser's validated IANA timezone, including daylight-saving
transitions; date-only Garmin health metrics retain their original dates.
Optional local profile fields and multiple training goals can be edited from
the Settings section. The AI provider foundation now supports manual selection
between local Qwen through Ollama and the OpenAI Responses API; grounded chat
now streams answers through either provider. Scoped provider-neutral tools supply deterministic health summaries, filtered activities with sensor
evidence, period comparisons, adjustable similar-ride selection, and local GPS
course matching, while the interface shows periods, freshness, record counts,
matching tolerances, course-performance changes, missing data, and activity
evidence links. Raw GPS coordinates never leave the local matching layer. Conditional ride assessments
and weekly running-volume trends use deterministic calculations. Chat can propose
profile or goal changes, show a preview, and save only after the user clicks
**Save change**. Forms and chat share validators and SQLite storage; stale proposals
cannot overwrite newer edits, and goal changes retain revision history.

## Project plan

Read the [review plan](docs/planning/health-training-app-plan.md) for the requirements, architecture proposal, implementation phases, acceptance criteria, integration limitations, and open decisions. The [implementation backlog](docs/planning/implementation-tasks-and-your-input.md), [progress tracker](docs/status/progress_status.md), [feasibility report](docs/status/phase-0-feasibility-report.md), [live-data coverage](docs/status/live-data-coverage.md), privacy-safe [Garmin export inventory](docs/status/garmin-export-inventory.md), and final [import coverage report](docs/status/import-coverage.md) are stored alongside it in logical documentation folders.

## Planned capabilities

- Import a full Garmin history export on first use, including supported ZIP, FIT, TCX, GPX, CSV, and archive JSON records.
- Manually import and export data, with portable exports and restorable backups.
- Synchronize daily with Garmin Connect and refresh using a **Sync now** button.
- Explore health and activity history through customizable graphs.
- Ask AI questions about historical data, compare similar rides or repeated GPS courses, and assess a ride against its training goal.
- Plan personalized strength, cycling, and running sessions and publish supported workouts to Garmin Connect.
- Review food-photo estimates and log calories, protein, fat, and carbohydrates.
- Track daily nutrition targets and status, with optional messaging later.
- Use local storage and provider-neutral application tools, with local AI available for zero recurring service fees and MCP optional for external AI clients.

## Proposed architecture

React/TypeScript interface, Python/FastAPI backend, SQLite storage, a
provider-neutral AI layer, scoped query tools, and reviewed settings proposals. Ollama is installed
and benchmarked locally. Both Qwen through Ollama and OpenAI are supported behind
one selectable interface; provider switching is manual, so there is no automatic
fallback to a paid API. The in-app assistant calls application tools directly;
an MCP adapter is optional and only needed for external AI clients.

For OpenAI, launch the backend from a terminal where `OPENAI_API_KEY` is set.
The key is read from the process environment and is not saved in SQLite or
returned by the API. The integration uses the official OpenAI Python SDK and
Responses API.

The scoped tool catalog is available locally at `GET /api/ai/tools`. Tools
execute through `POST /api/ai/tools/{tool_name}` with an `arguments` object.
Only registered operations and fields are accepted; models never receive SQL,
shell, or filesystem access.

## Maintenance history

Use **Maintenance** to log completed work, filter history, edit records, inspect
revisions, remove/restore entries, or import/export a CSV snapshot. Clear chat
commands such as “Log that I replaced the chain on my road bike today” save
locally and show Edit/Undo. Missing equipment or dates prompt a focused question.
Common maintenance commands work locally with either provider selected, including
when no AI provider is configured. Costs remain separate by currency.

SQLite stores the authoritative history; CSV is a portable current-record
snapshot. JSON exports include event revisions, and full backups preserve the
entire maintenance module. See [CSV columns and import behavior](docs/maintenance-csv.md)
and [T11 verification](docs/status/t11-verification.md).

## Next steps

1. Use Training to save preferences and review T7 foundation plans; T12 readiness remains advisory.
2. Live-verify the OpenAI path after `OPENAI_API_KEY` is supplied; Qwen is verified locally.
3. Implement T9 nutrition, then T10 daily-use launch/quit, recovery and normal-use checks.
4. Add T8 Garmin workout publishing last, once the local app works without it.

## Local development

Prerequisites: Python 3.13 and Node.js 24.

```sh
cd /Users/dotanhofman/Documents/garmin_app
make setup
make seed
```

`make seed` loads an idempotent, clearly labeled synthetic dataset containing
three activities, four activity samples, and fourteen daily health metrics. It
does not require Garmin credentials and does not overwrite non-synthetic data.

To inspect the ignored local Garmin ZIP without writing records, then perform an
idempotent transactional import of summarized activities and supported daily
metrics:

```sh
make garmin-preview
make garmin-import
make fit-inventory
make fit-preview
make fit-import
make xml-preview
make xml-import
make health-fit-inventory
make health-fit-preview
make health-fit-import
make wellness-preview
make wellness-import
make extended-preview
make extended-import
```

The importer validates archive paths, entry counts, expanded sizes, individual
file sizes, nesting depth, compression ratios, encryption, symbolic links, CRC,
JSON structure, timestamps, identifiers, and numeric values. The original ZIP
is never extracted or modified. FIT inventory/import uses Garmin's official,
pinned Python FIT SDK and checkpoints each physical nested file for safe resume.
The monitoring importer stores only validated heart-rate, stress, and
respiration values in a compact timestamped table; its ignored inventory file
avoids repeat full-archive scans.
The extended importer maintains an auditable classification for every outer
archive file and excludes account, social, device, location-administration,
and other private administrative data from normalized storage.

Start the backend in one Terminal window:

```sh
make backend
```

Start the frontend in a second Terminal window:

```sh
make frontend
```

Then open `http://127.0.0.1:5173`. Run `make test` for the database migration
test and TypeScript checks, or `make build` for a production frontend build.

The Import / Export section creates downloads locally. CSV and JSON follow the
selected dashboard date range. Backup ZIPs always exclude credentials and
session tokens; including the private original source archives is an explicit,
off-by-default option. Restore preview validates paths, checksums, schema,
SQLite integrity, and relationships without replacing the current database.

## Personal data

Keep Garmin archives, activity files, meal photos, credentials, and local databases outside version control. The repository includes baseline ignore rules; future tests should use synthetic or deliberately anonymized fixtures.

### Repair data omitted by earlier sync versions

With the app stopped, create a backup from Import / Export before running recovery. To normalize preserved activity summaries and recover session metadata from the original local archive:

```sh
PYTHONPATH=backend .venv/bin/python -m app.sync_repair
```

Add `--live` to use the saved Garmin session for missing live activity summaries and historical HRV. Add `--skip-fit` when FIT recovery has already completed. The recovery updates existing records; it does not reimport sensor samples. Interrupted HRV history resumes from its committed date. Missing source values remain missing. See [sync recovery verification](docs/status/sync-recovery-verification.md).

### Transparent training readiness

The dashboard includes a provisional morning readiness card with personal HRV/RHR references, sleep adequacy and decayed workout load. Expand it for exact deductions, data gaps, a 14-morning trend, and editable versioned parameters. Missing inputs yield a range or insufficient data. Ask the assistant for training readiness to get the same advisory result. The prototype never changes a workout automatically; its weights are not prospectively validated. See [T12 verification](docs/status/t12-verification.md).

## Training plans

Open **Training** to save sports, availability, equipment, experience and restrictions. Only missing/stale answers require confirmation. Create a Monday draft, review its sessions and context, then explicitly accept it. Edit templates/duration and record completion, effort, soreness or missed sessions. Review next-week volume separately; saving limits leaves the existing calendar unchanged. Goals are optional. Foundation templates are local; Garmin publishing is T8. See [rules and limits](docs/planning/training-rules.md) and [verification](docs/status/t7-verification.md).
