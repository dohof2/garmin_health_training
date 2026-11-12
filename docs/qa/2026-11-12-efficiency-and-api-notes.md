# QC notes — assistant efficiency and Garmin data integration

Recorded 12 November 2026. **Notes only: pending design and implementation. No implementation, migration, schedule, or remote operation is authorized by these notes.**

## 1. Make routine ride reviews more efficient while retaining interval analysis

The November 11 ride review used 6 model calls, 32,291 reported input tokens and 772 output tokens. The trace included an empty cycling-filter lookup (the ride was mountain biking), a successful lookup, section analysis and a separate task-memory update. Repeated context and tool definitions contributed to input usage.

Proposed direction:

- Provide one focused ride-review tool that resolves cycling subtypes and returns core statistics plus useful interval/section comparisons.
- Calculate from recordings locally and give the model compact results with units, sample coverage and limitations. Keep the useful interval comparison; use GPS for route-specific questions rather than routinely sending coordinates.
- Retain resolved activity references automatically, avoid repeated lookups, and send only relevant history and tool definitions.
- Aim for 2–3 model calls for routine reviews. Measure input/output usage and response quality before claiming savings; do not achieve savings by dropping useful interval analysis or evidence quality.

Status: proposed, not implemented.

## 2. Use the API for inbound import; retain the current workout-publication method

User direction: move inbound import to the Garmin API while keeping workout publication through the current method. The integration design and recurrence remain unresolved.

Before implementation, determine how the two paths coexist, including their authentication, responsibilities, publication verification/reconciliation and prevention of duplicate sends. Decide the import/refresh and publication triggers and recurrence separately, including manual versus automatic behavior and freshness requirements. No frequency is selected in this note.

Related research: [Garmin Personal API migration plan](../planning/garmin-personal-api-migration-plan.md). This user direction supersedes that document's earlier recommendation to remove the existing client entirely; the previous migration design needs revision before implementation. API data coverage and remaining gaps must be verified before cutover.

Status: user direction recorded; design and cadence pending, no migration implemented.

## 3. Review import and refresh efficiency end to end

Review inbound fetching, historical import, incremental refresh, local processing and frontend refresh together. Identify repeated requests, unnecessary history reloads, redundant processing and refreshes triggered without changed data. Establish current request counts, latency and data freshness before choosing changes.

Evaluate incremental fetching/checkpoints, deduplication, caching, request coalescing, concurrency and rate-limit handling where supported. Preserve completeness, recovery after interrupted imports and clear partial-failure reporting. Verify that newly imported data reaches affected views without unnecessary full reloads.

The user expects the API may help; this is a hypothesis to measure, not an established performance improvement. Coordinate with note 2 when choosing recurrence.

Status: QC investigation requested for later; not implemented.
