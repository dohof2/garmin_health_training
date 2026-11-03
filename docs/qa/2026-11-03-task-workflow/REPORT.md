# Task-oriented assistant trial and manual workout placement

Implemented November 3, 2026. The new workflow is a reversible trial. Restart the local app to load the new backend and frontend.

## Use and rollback

In **Settings → Assistant → Assistant workflow**, choose:

- **Task-based · token-saving trial**: new default.
- **Previous workflow · rollback**: the previous chat implementation, retained as `_legacy_chat_stream` in `backend/app/ai_chat.py`.

Click **Save AI settings**. Once this version is running, the choice applies to subsequent chat requests without restarting. Switching does not delete plans, meals, chat receipts or new-workflow task state. The legacy path does not call the new coordinator. There is no automatic fallback after a failure.

Emergency server override: start the existing launcher with `HT_ASSISTANT_WORKFLOW=legacy`. This environment override takes precedence over Settings; unset it before using the Settings selector to re-enable the trial. Schema migrations are additive and do not require reversing tables for rollback.

## New workflow

- One coordinator identifies the task, selects a small set of tools and resumes durable task state. The three specialists share operation receipts, budget accounting and canonical application services.
- Trainer adjustments call the existing validated proposal services directly. Full planning uses small typed fact extraction for richer messages, local parsing for short intake answers, and the existing prescription/planning rules. A task retains its planning candidate independently of the text window and mirrors the current candidate to the existing review UI.
- Data questions use scoped local summaries, selected records and chart specifications. Clear supported queries/plots need no model call. General explanations do not automatically retrieve personal history. A program overview reads its brief and building blocks, not a full database snapshot.
- Nutrition reuses the existing food, correction and receipt services. Food logging omits body/activity history and calorie-target schemas/instructions. Target tasks load that context when necessary.
- Dates resolved from the original request remain absolute on continuations. A new explicit date amendment uses the current turn's date. Saved training changes are checked against actual records before a retry can prepare a reversal.
- Explicit mixed requests are separate ordered tasks with individual receipts. Partial failures are reported without repeating successful operations.
- Read-only advice channels can save conversation bookkeeping while canonical writes remain blocked. Telegram shares the selected workflow, with its existing channel restrictions.
- A new conversation receives a fresh conversation ID. Status questions do not grant write authorization.

## Token controls

Budgets are cumulative across a task's turns, not just the final answer. They are guarded before model requests. UTF-8 byte-based estimates are labelled as estimates; provider-reported input/output counts are recorded when available. Provider output totals include provider-accounted reasoning. No billing reduction is claimed from estimated counts alone.

The initial full-planning trial uses an **estimated input ceiling of 6,000 tokens and an output ceiling of 2,000 tokens**, with at most eight model calls over that task stage. A richer intake message uses one small fact-extraction request; short answers can use zero calls. This supersedes the more generous preliminary planning-document budget. Detailed workout generation remains local.

Other task classes have smaller task-specific call/input/output limits. Output allowance is bounded per call and across the task. A budget stop retains progress and requires an explicit `next stage`; it never silently retries or switches providers. Usage details appear below new-workflow answers and in logs without prompts, health content or credentials.

## Drag-and-drop in Next 7 days

- Drag a planned workout card onto an empty day to move it.
- Drop onto a specific workout, or a day containing one planned workout, to exchange their dates atomically.
- If a day contains several planned workouts and the drop does not identify one, a placement form offers a specific swap or moving alongside the existing sessions.
- Pointer-based dragging supports mouse, pen and touch. The existing Move/Swap forms remain available for keyboard operation. Escape/pointer cancellation does not save a placement.
- Manual moves/swaps can be one-time exceptions to recurring sport/day and duration allowances. Saved weekly availability is unchanged. Vacated slots are retained so automatic review does not regenerate the workout that was moved away.
- Completed/fixed sessions, stale revisions, active-plan boundaries, recovery spacing and verified Garmin ownership remain guarded. Completed demanding work is included in spacing checks.
- Dates and calendar slot metadata change; prescription instructions/durations stay with the workout. Previously published sessions require the existing Publish workflow to update Garmin.

## Verification

- **104 focused tests passed**, covering new/legacy selection, settings rollback without canonical data mutation, durable status/follow-ups, frozen dates, replay receipts, saved-swap replay prevention, mixed tasks, scoped prompts, small planning intake, food context, read-only channels, budget stops, safe errors, interruption/receipt recovery, additive migration recovery, and manual date placement.
- HTTP-level streaming test verifies that budget context stays active during model generation, does not cross worker-context boundaries between chunks, and replays a completed receipt without another provider call.
- Frontend TypeScript and production build passed. Python compilation and whitespace checks passed.
- Broad regression run before the last interruption-specific cases: **946 tests; 34 failures and 28 errors**. All failing test names match the pre-trial November 3 run. The repository-wide suite is not green; the trial's focused checks are green. The final focused checks cover the subsequent receipt/interruption changes.

### Browser checks on an isolated database copy

The temporary app ran on port 8777 against `/tmp/garmin-workflow-ui`, separate from the normal application on port 8765. No real workout dates were changed by these checks.

1. Dragged Tuesday November 3 strength (25 minutes) to the empty Sunday November 8 cell. Tuesday became empty; Sunday showed that same strength session.
2. Dragged Friday November 6 endurance (120 minutes) onto Monday November 9 recovery (30 minutes). Friday displayed recovery; Monday displayed endurance. Both dates persisted after reload.
3. Submitted “How many steps in the last 7 days?” through the browser. The response covered October 28–November 3 with seven recorded days, displayed **0 model calls**, and completed without a network error after the streaming integration fix.
4. Verified the Settings selector exposes the new trial and previous-workflow rollback options.
5. Verified New conversation clears the displayed test exchange and starts a fresh conversation before another successful zero-model query.

Screenshots: [manual placement result](dragged-workouts.png), [workflow selector and zero-model query](workflow-settings.png).

Two integration issues were caught and fixed during verification: ContextVar lifetime across streamed worker chunks, and an incremental migration needed for batch receipts. External integration flags were disabled in the test copy after detecting an inherited background Telegram polling configuration; no test messages were sent. Future copied-data UI setups should disable external integration flags before starting the server.

Model-dependent paths were exercised with mocked providers. No live OpenAI/ChatGPT token allowance was consumed for these checks. Actual model quality and account usage should be observed during the trial using the visible counters; no end-to-end live-provider benchmark is claimed.
