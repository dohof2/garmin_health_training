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
FIT detail retrieval for activities missing sensor samples. It currently
refreshes activities, daily summaries, sleep, HRV, and weight/body-composition
data. Dashboard cards can be reordered, hidden, and
restored, with the saved layout persisted locally in SQLite. Activity calendar
dates follow the browser's validated IANA timezone, including daylight-saving
transitions; date-only Garmin health metrics retain their original dates.
Optional local profile fields and multiple training goals can be edited from
the Settings section. AI features remain future work.

## Project plan

Read the [review plan](docs/planning/health-training-app-plan.md) for the requirements, architecture proposal, implementation phases, acceptance criteria, integration limitations, and open decisions. The [implementation backlog](docs/planning/implementation-tasks-and-your-input.md), [progress tracker](docs/status/progress_status.md), [feasibility report](docs/status/phase-0-feasibility-report.md), [live-data coverage](docs/status/live-data-coverage.md), privacy-safe [Garmin export inventory](docs/status/garmin-export-inventory.md), and final [import coverage report](docs/status/import-coverage.md) are stored alongside it in logical documentation folders.

## Planned capabilities

- Import a full Garmin history export on first use, including supported ZIP, FIT, TCX, GPX, CSV, and archive JSON records.
- Manually import and export data, with portable exports and restorable backups.
- Synchronize daily with Garmin Connect and refresh using a **Sync now** button.
- Explore health and activity history through customizable graphs.
- Ask AI questions about historical data, compare similar rides, and assess a ride against its training goal.
- Plan personalized strength, cycling, and running sessions and publish supported workouts to Garmin Connect.
- Review food-photo estimates and log calories, protein, fat, and carbohydrates.
- Track daily nutrition targets and status, with optional messaging later.
- Use local storage, local AI, and MCP tools, targeting zero recurring service fees.

## Proposed architecture

React/TypeScript interface, Python/FastAPI backend, SQLite storage, a
provider-neutral AI layer, and scoped read-only query tools. Ollama is installed
and benchmarked locally; the final AI provider selection remains explicit
before T6 integration.

## Next steps

1. Review the plan and answer its personalization and hardware questions.
2. Validate Garmin archive formats, online integration, workout compatibility, and local model performance.
3. Build the import/export and synchronization foundation, then graphs and the historical AI assistant.

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
