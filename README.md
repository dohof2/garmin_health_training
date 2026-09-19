# Garmin Health and Training

A planned local application for personal health, training, and nutrition, built around Garmin history and user-defined goals.

**Status: planning.** No application has been implemented yet.

## Project plan

Read the [review plan](docs/health-training-app-plan.md) for the requirements, architecture proposal, implementation phases, acceptance criteria, integration limitations, and open decisions.

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

React/TypeScript interface, Python/FastAPI backend, SQLite storage, local AI through Ollama, and a scoped local MCP server. These choices remain subject to the plan review and feasibility checks.

## Next steps

1. Review the plan and answer its personalization and hardware questions.
2. Validate Garmin archive formats, online integration, workout compatibility, and local model performance.
3. Build the import/export and synchronization foundation, then graphs and the historical AI assistant.

There are no install or run commands yet. Development begins after the planning review.

## Personal data

Keep Garmin archives, activity files, meal photos, credentials, and local databases outside version control. The repository includes baseline ignore rules; future tests should use synthetic or deliberately anonymized fixtures.
