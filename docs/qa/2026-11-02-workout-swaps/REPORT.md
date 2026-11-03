# Workout swaps and chatbot input costs

Implemented November 2, 2026.

## Findings and changes

- Trainer adjustments previously returned a clarification for every move/swap, regardless of whether the user supplied both dates. Manual scheduling moved only one session, so the old destination occupant could prevent exchanging two sessions.
- Added an atomic swap endpoint and manual **Swap with another workout** control in active-plan workout details. Chat recognizes swap/switch/exchange with today/tomorrow, weekdays or two ISO dates, including the request to do today's workout tomorrow and tomorrow's today. Ambiguous dates/sessions require a selection.
- Preview validates the final arrangement and rolls back; Save checks revisions again and commits both sessions together. Availability, recovery spacing, active-plan membership, fixed events and Garmin ownership remain validated. Dates, optional times and slots move together; workout instructions stay with their workouts. User changes survive daily plan review. Managed Garmin workouts become `update_needed`; remote publication still uses the existing Publish workflow.
- Repeated chatbot inputs included up to 20 history messages (80,000 characters), a shared 17,000-character coaching/data prompt, and the full tool catalog on every ChatGPT tool round. Nutrition allowed 12 turns (72,000 characters). Ordinary charts could return thousands of points to the model, and API answer generation resent schemas despite disabling tool calls.
- Bound model-facing history to eight complete recent messages within a 12,000-character budget. Stored conversation history and deterministic follow-up resolution remain intact. Saved preferences, goals, pending nutrition items and current app context remain separate from this conversational budget.
- Data-science ChatGPT turns use focused instructions and omit training proposal schemas/coaching context. Trainer turns retain coaching tools. Nutrition JSON is compact. Chart evidence remains complete in the app while model-facing outputs contain calculated summaries and endpoints. API final-answer calls omit unused tool schemas.

## Measurements

These are serialized input character counts, not live provider token usage or billing measurements.

- Data-science fixed instructions plus schemas: 48,120 -> 35,959 characters (25.3% reduction, before history and tool results).
- Data-science instructions: 17,297 -> 8,358 characters (51.7% reduction).
- Maximum usual general-chat history: 80,000 -> 12,000 characters (85% reduction). Whole messages can leave the actual budget below 12,000.
- 2,000-point chart fixture: model tool-result payload reduced by more than 95%, with all plotted evidence retained locally.
- Swap preview and save use deterministic application code, with no model calls.

## Verification

- Focused backend checks cover swap preview/commit, failed validation rollback, stale revisions, negation, unavailable destinations, daily review preservation, today/tomorrow chat routing without a model call, request budgets, complete local plot evidence, existing chat, active training, nutrition and shared allowance behavior.
- Frontend production build and TypeScript checks passed.
- Broad backend run: 911 tests, 33 failures and 30 errors. Every failing test name also failed against a temporary baseline containing the starting implementations (preserving pre-existing unrelated working changes). Baseline also had six additional path/resource-related errors from running outside the repository. The full suite is not green; no new failing test names were introduced in this comparison.
- Tests use isolated databases and mocked provider responses. No live user workout was swapped and no provider usage was incurred for QC.

Restart the running local application to load the backend changes; refresh the browser after restart. In Training, select a planned workout, choose **Swap with another workout**, select the second session, then **Save swap**. Previously published sessions need republishing to update Garmin.
