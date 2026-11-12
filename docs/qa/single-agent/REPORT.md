# Single-agent skills implementation and verification

## Implemented behavior

Chat now uses one reasoning agent with the existing selected provider/model. The verified saved configuration is ChatGPT `gpt-6.1-sol`; its existing `low` reasoning setting is preserved. There is no role selector, role-based history split, mandatory classifier call, workflow switch, or previous-agent fallback.

The catalog contains 32 versioned skills across eight branches. Browsing Training returns Sessions and Programs before leaf cards. Direct search can find a leaf without traversing every level. Catalog cards exclude full instructions and tool schemas; those load only for selected skills. Loading a new skill replaces unrelated instructions by default, with explicit addition available for compound tasks.

The shared agent interprets language and clarifications. Local tools retrieve evidence, calculate results, validate changes and maintain operation receipts. Nutrition logging/corrections/target proposals use structured inputs from the same agent, with no second conversational nutrition model call.

Task briefs, original conversation dates, record references and pending planning decisions persist locally. The browser retains its conversation ID across restarts. General discussion can answer without loading a skill. Long-term plan construction has a dedicated broader skill and a larger per-turn allowance. Instructions/catalog metadata are kept outside the root prompt and can be updated independently of orchestration code.

## Code organization

- `backend/app/skills/catalog.json`: compact catalog, hierarchy, examples, tool ownership and versions.
- `backend/app/skills/core.md`: shared conversation and selection instructions.
- `backend/app/skills/*.md`: 32 focused skill bodies, including new-plan construction.
- `backend/app/skill_catalog.py`: local search, hierarchical browsing and loading.
- `backend/app/skill_agent.py`: one model/tool loop, selective context, task memory and durable receipts.
- `backend/app/skill_tools.py`: focused adapters over the existing domain services.
- `backend/app/session_changes.py`: exact-session edit/schedule references around existing validators.
- `backend/app/nutrition_operations.py`: structured food logging, corrections and target proposals; no model calls.
- `backend/app/agent_runtime.py`: per-turn usage, including reported reasoning tokens without double-counting them.
- `039_skill_agent.sql`: retains provider/model settings and migrates prior task summaries/nutrition context while removing the workflow setting.

The public `ai_chat.py` entry point now delegates to the single agent. The previous role router, assistant workflow/runtime, standalone nutrition conversational handler, canned maintenance handler, old questionnaire interpreter and unused conversational follow-up helpers were removed. Saved candidate setup remains readable by the Training form. Historical SQL migrations and audit records remain; they are not executable fallback workflows.

Single-session formatting or strength-set edits cannot silently become program-wide changes. Explicit recurring format/progression changes have separate program-level tools. Training proposals still use existing review/Save controls, current-revision checks and domain validation. Food deletion clears affected shared-agent receipts so a retry cannot report a deleted meal as saved.

## Verification

Command: `.venv/bin/python scripts/run_skill_agent_checks.py --frontend`

- **144 selected backend checks passed**, including 42 single-agent/catalog checks, schema upgrade, exact-session selection, source-history preservation, preview rollback, save/retry behavior, skill isolation, per-turn accounting, long-term task resumption, structured nutrition, food correction/moves/deletion, maintenance, Telegram authorization, provider behavior and existing domain checks.
- **33 frontend checks passed.**
- Frontend production build and Python compilation passed. Vite reports the existing large-bundle warning.
- `git diff --check` passed.
- Source inspection found no active old role router, standalone provider chat loops, previous workflow switch, or fallback handler in application/frontend/scripts.

The tests that asserted removed keyword routing, canned replies, role handoffs or native legacy stream loops were retired rather than preserving compatibility implementations. The lists are recorded in [orchestration assertions](retired-orchestration-assertions.md), [nutrition orchestration assertions](retired-nutrition-orchestration-assertions.md), and [dialogue-handler assertions](retired-dialogue-handlers.md). Domain assertions were preserved where independent of those handlers; the fifty prescription cases now call the domain preview/save services directly.

## Live model smoke test

A read-only smoke test used the existing ChatGPT `gpt-6.1-sol` connection. The request explicitly asked for one sentence of general education, with no personal record reads or changes. It completed with **one model call, no loaded skills, 1,376 reported input tokens and 33 reported output tokens**. No personal workout or nutrition record was changed.

That initial smoke test covered general conversation only. Subsequent real workout and Hebrew meal reports exposed failures in the manually requested JSON response envelope; the stored receipts locate the workout failure after skill loading, before any domain edit. The original raw provider response was not retained, so its precise malformed shape is unknown.

## Native tool protocol correction

The agent now sends native function definitions, receives native function calls and returns correlated function outputs. Final replies are ordinary text. Native reasoning/output items are retained in order across tool rounds, including streams whose terminal event contains only metadata. The selected Sol model and its reasoning setting remain unchanged. There is no conversational JSON-envelope fallback.

Failed requests now retain their original user message and a safe failure stage/type for diagnosis, without retaining provider exception payloads. Nine additional protocol tests cover actual provider stream parsing, plain Hebrew replies, malformed tool arguments, correlated calls, native OpenAI/Ollama adapters and both reported requests. All **153 selected backend checks passed** after this correction.

A live Sol test against temporary synthetic records successfully looked up today's strength workout and requested only the missing replacement-ride duration (six model calls). The exact Hebrew yogurt report selected only `nutrition.log` and asked for product/weight (four calls). A follow-up specifying 150 g plain 3% yogurt and authorizing an estimate saved one lunch entry with estimated nutrients and returned a natural Hebrew confirmation (three calls). No real workout or nutrition record was modified. These checks cover the reported scenarios, not every possible skill selection.

## Published strength replacement correction

The reported replacement reached a historical blanket rejection of any published strength workout. Verified app-managed sessions in `published` or `update_needed` state now produce the ordinary reviewed replacement. Save retains the remote identity and marks `update_needed`; the existing Send to Garmin approval/update/read-back path applies the new cycling payload to that same remote workout and preserves the calendar entry. Unverified mappings and unresolved publication states still require reconciliation through the publication result. The edit skill (version 2) explains these local-save/remote-update boundaries instead of requesting manual calendar deletion.

All **155 selected backend checks and 25 Garmin publication/workout-swap checks passed**. The added end-to-end domain regression publishes synthetic strength, previews without mutation, saves the cycling replacement, verifies historical preservation, then approves/sends and verifies one remote update with no additional workout or calendar creation. Another regression covers unresolved/unmanaged publication states. A read-only check confirmed the reported current strength session has a verified app-managed mapping; no user records or live Garmin workouts were changed during this correction.

## Shared weekly allowance and missed-session correction

Replacements now use the same `training_volume` estimate, confirmed weekly range, recovery context and program-start-anchored week as plan construction. The separate five-percent/15-minute weekly-dose ceiling is no longer used for replacements. Individual-ride and recovery checks remain separate. Remaining weekly room subtracts actual recorded riding (with linked/reported completions deduplicated) and current/future planned rides; past unperformed plans reserve neither minutes nor recovery/quality spacing. Actual rides count even when sync coverage is partial.

Shared accounting is also used by ongoing cycling allocation, new-plan commitments, session edit/reschedule checks, strength allowance checks and nutrition training-day selection. Completion reconciliation removes unmatched past plans from visible plan/history using an internal `missed` state. That marker preserves publication identity and late-sync matching: a uniquely matching delayed recording restores completion, without assuming that missing sync data means training was performed. Ambiguous recording matches remain unresolved. Cleanup runs at startup, plan review and activity-sync reconciliation; historical source records and completed activities are preserved.

Verification: **161 focused backend checks and 65 domain/history/launcher checks passed**. Tests cover the confirmed-range override, non-Monday program weeks, missed published sessions, late completion recovery, partial sync and duplicate prevention. Prior long-ride tests now distinguish completed reservations from unperformed past plans. A separate 70-test exploratory selection initially had eight failures, reproduced with the same tests against the original committed application code. Their subsequent investigation and resolution follow below.

The user's missed 60-minute ride dated 2026-11-02 was reconciled locally and removed from the visible updated plan/history. Read-back confirms the active week is **2026-11-02–2026-11-08**, the confirmed weekly allowance is **330 minutes**, performed riding is **0 minutes**, remaining planned riding is **180 minutes**, and available room is **150 minutes**. No future workout was changed and no Garmin write was made by this cleanup. Restart the backend to load the new calculation and visibility rules.

## Eight training failures: investigated and resolved

The eight failures were obsolete assertions or incomplete fixtures, rather than regressions caused by the shared allowance change:

| Failure cases | Cause | Correction |
| --- | --- | --- |
| Three sprint/anaerobic request cases | Expected rejection under old programme-week/feedback quotas; the current policy and existing advanced-cycling acceptance checks explicitly removed those quotas. | Expect reviewed proposals under normal conditions; assert the requested workout category and retain save/revision/retry checks. Add explicit fatigue, elevated-load and deliberate recovery-phase rejection coverage. |
| Three weekly-minute cases | Treated saved optional caps of 240/300 minutes as guaranteed prescribed volume. These fixtures contain no completed riding history, so their effective provisional ceiling is 180 minutes. | Separately assert that the requested cap is persisted and that effective volume remains 180. Verify existing workouts reserve their actual scheduled minutes and prevent duplicate scheduling. Preserve the fixed 180-minute commitment unchanged. |
| Longest-slot case | Expected Saturday first in a chronologically sorted response and assumed 120 minutes of availability proved capacity for a 120-minute ride. Current allocation also preserves a purposeful shorter weekday ride. | Add recorded two-hour riding history, locate sessions by date and check a 90-minute Saturday plus 30-minute Monday within the 120-minute cap. Independently verify that without history the Saturday session remains 60 minutes. |
| FTP target case | Looked for threshold power in the first session (an endurance ride) and used the old 225–237.5 W interval. The MTB power-tolerance change predates this work. | Select the actual threshold session and its work laps; assert the current 225–262.5 W band at FTP 250 W, with the preserved 243.75 W midpoint. |

One production explanation was also stale: a recovery/phase rejection still claimed that sprint work required two tolerated completed quality sessions. Its message now describes the actual recovery/phase reason. Eligibility and prescribed intensity were not relaxed in order to pass these checks.

Normal-week interval targets remain conditional, never mandatory quotas. Existing checks for intentional recovery blocks, fatigue/adverse feedback, recorded hard rides, load and reduced availability remain enabled. The added rejection test confirms no workout is changed by an unsuitable sprint request. The affected suites are now included in `scripts/run_skill_agent_checks.py`; its expanded **235 backend tests passed**, and `git diff --check` passed. This does not assert that the older full-repository discovery run below is entirely resolved.

## Initial broader repository test status

A separate full-discovery run executed 724 tests and reported **26 failures and 14 errors**. That suite is not green. Its failures include training-draft fingerprint disagreements, scheduling/prescription expectations, an outdated exact tool-registry inventory, strength exercise expectations and synchronization behavior. The three sprint-status discrepancies were also reproduced before this implementation's domain edits.

These broader failures remain visible; the selected checks above are not a substitute for declaring the entire application regression-free. The full-discovery output is retained in `full-suite.txt` for follow-up. No compatibility agent or fallback was reintroduced to satisfy obsolete routing expectations.

## Existing UI boundaries

Synchronization/authentication, Garmin publication, imports/restores, recipe authoring and dashboard configuration retain their existing app controls. Relevant skills can inspect state and provide working navigation/download links. A link does not claim an operation was executed. Nutrition targets and training/settings changes retain their reviewed save actions.

## Updating a skill

Edit the relevant Markdown body, update its catalog description/examples/version when needed, and add the failing conversation to the regression checks. Catalog metadata is refreshed when its file changes; bodies load on demand. New tool capabilities require a validated adapter, not just an instruction claiming they exist. Restart the backend after Python changes.

Start or restart the app normally to load the new backend and built frontend. Existing provider/model selection, accepted plans, food records and domain validation remain in place.
