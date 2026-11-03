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

This verifies the live provider path, JSON response contract, general conversation and usage reporting. Catalog selection and multi-turn action scenarios were tested with scripted model decisions against synthetic records; this is not a claim that every real-language selection has been live-evaluated.

## Broader repository test status

A separate full-discovery run executed 724 tests and reported **26 failures and 14 errors**. That suite is not green. Its failures include training-draft fingerprint disagreements, scheduling/prescription expectations, an outdated exact tool-registry inventory, strength exercise expectations and synchronization behavior. The three sprint-status discrepancies were also reproduced before this implementation's domain edits.

These broader failures remain visible; the selected checks above are not a substitute for declaring the entire application regression-free. The full-discovery output is retained in `full-suite.txt` for follow-up. No compatibility agent or fallback was reintroduced to satisfy obsolete routing expectations.

## Existing UI boundaries

Synchronization/authentication, Garmin publication, imports/restores, recipe authoring and dashboard configuration retain their existing app controls. Relevant skills can inspect state and provide working navigation/download links. A link does not claim an operation was executed. Nutrition targets and training/settings changes retain their reviewed save actions.

## Updating a skill

Edit the relevant Markdown body, update its catalog description/examples/version when needed, and add the failing conversation to the regression checks. Catalog metadata is refreshed when its file changes; bodies load on demand. New tool capabilities require a validated adapter, not just an instruction claiming they exist. Restart the backend after Python changes.

Start or restart the app normally to load the new backend and built frontend. Existing provider/model selection, accepted plans, food records and domain validation remain in place.
