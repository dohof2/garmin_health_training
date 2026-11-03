# Single conversational agent and skill catalog

Status: Catalog and single-agent runtime implemented following user authorization. See [implementation and verification](../qa/single-agent/REPORT.md). The sections below record the design and its rationale.

## Direction agreed in discussion

Use one conversational agent with the user's selected ChatGPT Sol reasoning configuration. Keep one shared conversation and task context across training, nutrition, analysis, and other app capabilities. Model changes are outside this proposal.

The agent interprets natural language, retains clarifications, chooses capabilities, and explains results. Focused skills supply application knowledge, procedures, and access to appropriate tools. Application services perform calculations and validate/persist changes.

This replaces the proposed three-assistant design as the working architectural direction. The older document remains historical context. Useful existing domain services and task receipts can be reused; keyword routing, canned dialogue, and mandatory interpretation calls are not requirements to preserve.

## 1. Catalog design

The catalog has a shallow hierarchy for browsing and a direct search index for finding leaf skills. Hierarchy organizes capabilities; it does not require a separate model call at every level.

The initial prompt contains a short shared instruction set, the eight branch descriptions below, compact current-task context, and discovery tool descriptions. It does not contain every skill body, every tool schema, or the user's complete health history.

| Root branch | What the agent can find here |
|---|---|
| Training | Planned sessions, workout changes, feedback, today's recommendations, programs, and events |
| Activities & analysis | Recorded activities, assessments, comparisons, detailed sections, FIT evidence, and plots |
| Health & recovery | Recorded health trends and the app's readiness/recovery estimates |
| Nutrition | Food logging, corrections, daily balance, targets, and reusable meals/recipes |
| Profile & preferences | Personal details, goals, availability, equipment, restrictions, and calibration |
| Garmin & sync | Connection/sync status, synchronization, and workout publication |
| Equipment maintenance | Completed maintenance work, history, corrections, and undo |
| App & data | Data availability, imports/exports/backups, and dashboard configuration |

### Proposed hierarchy

```text
Training
  Sessions
    Inspect and explain
    Edit or replace
    Move or swap
    Record completion and feedback
    Recommend a workout
  Programs
    Build a new long-term training plan
    Substantially revise an existing program
    Review a week or progression
    Manage events and commitments

Activities & analysis
  Find and inspect activities
  Assess an activity
  Compare activities or periods
  Investigate intervals, climbs, and FIT evidence
  Create or refine plots

Health & recovery
  Explain recorded health trends
  Assess readiness and recovery

Nutrition
  Log food
  Correct, move, or remove a meal
  Explain daily balance
  Plan or adjust targets
  Manage reusable foods, meals, and recipes

Profile & preferences
  Update personal profile and goals
  Update training availability, equipment, and restrictions
  Review or update FTP and HR calibration

Garmin & sync
  Inspect connection and synchronization status
  Run or troubleshoot synchronization
  Publish, update, or remove a Garmin workout

Equipment maintenance
  Log completed work
  Inspect, correct, undo, or export history

App & data
  Discover available data and explain coverage
  Import, export, back up, or restore data
  Configure dashboard and charts
```

This is a proposed inventory of 32 leaf skills, not a requirement to create 32 files immediately. Split a skill when it needs materially different instructions, evidence, or tools. Keep closely related operations together when splitting would create unnecessary discovery and handoffs.

## 2. Initial leaf-skill contracts

"Existing support" below describes the current service/tool foundation. It does not mean the skill exists or that every service is exposed to chat. Implementation must verify interfaces and identify missing adapters before enabling a capability.

| Proposed stable ID | Owns | Minimum initial evidence | Existing support / work needed |
|---|---|---|---|
| `training.sessions.inspect` | Explain a planned workout and its purpose | Selected session; relevant program block if needed | Planned workout/program readers; scoped adapter needed |
| `training.sessions.edit` | Duration, intensity, blocks, exercises, sets/reps, format, or sport replacement | Selected session, requested effect, applicable restrictions | Adjustment, strength, format, and block-edit services; consolidate interfaces |
| `training.sessions.schedule` | Move or swap dated sessions | Selected sessions/dates and relevant conflicts | Reschedule/swap services; expose structured references |
| `training.sessions.feedback` | Completion, actual strength sets, feedback, and activity linking | Selected workout and existing feedback/link | Workout feedback and completion services |
| `training.sessions.recommend` | A workout for available time, with or without a plan | Time, sport, explicit plan/independent intent, relevant recovery | `suggest_today_workout`, workout variants |
| `training.programs.build` | Build a new long-term training plan through staged assessment and design | Goals, horizon, historical training/tolerance, availability, restrictions, equipment, calibration, and existing commitments | Coaching preview/approval services; broader evidence gathering and resumable planning draft needed |
| `training.programs.revise` | Substantially revise an existing multi-week program | Current program, requested direction change, relevant evidence and retained decisions | Coaching preview/approval services; preserve completed history and identify affected future blocks |
| `training.programs.review` | Review a week, load distribution, or progression | Relevant week/block and calculated recent-load/tolerance summaries | Active-program review and training-mix services |
| `training.programs.events` | Add/change/remove races, trips, and fixed commitments | Named event, dates, program reference | Event proposal and save services |
| `activities.inspect` | Find activities and answer factual activity questions | Filters or named activity and requested measurements | `list_activities`, activity detail and scoped queries |
| `activities.assess` | Interpret recorded effort against stated intent | Selected activity and user's intent if known | `assess_ride`; preserve supported-sport limits |
| `activities.compare` | Compare rides, periods, similar rides, or repeated courses | Selected records/periods and comparison purpose | Comparison tools and local route matching |
| `activities.investigate` | Within-activity intervals, climbs, laps, streams, or unusual FIT fields | Selected activity/section or bounded search period | Section/climb/sprint analysis, stream and FIT readers |
| `activities.plot` | Create or refine charts using recorded data | Requested axes/metrics, scope, and existing plot spec if relevant | Chart catalog and `create_plots` |
| `health.trends` | Explain steps, sleep, HRV, weight, and other recorded health trends | Requested metrics, dates, units, coverage | Health summary, period comparisons, scoped data queries |
| `health.readiness` | Explain measured inputs and advisory readiness/recovery or forecast | Dated estimate, evidence, missingness, uncertainty | Readiness and projected-readiness tools |
| `nutrition.log` | Record consumed food, including photos when supported | Foods/image, portion evidence, meal/date, pending draft | Nutrition analysis and logging services; expose focused adapter |
| `nutrition.correct` | Correct portions/items, move meals, remove/restore supported records | Exact saved meal/items or pending draft and revision | Nutrition correction/move services; verify supported removal/restore |
| `nutrition.balance` | Daily totals, remaining intake, and target comparison | Selected day's totals and applicable targets | Daily nutrition status and scoped queries |
| `nutrition.targets` | Discuss/propose calorie/macronutrient targets | Goals, existing targets, relevant body/activity summaries | Nutrition target services; distinguish advice/proposal/save |
| `nutrition.library` | Saved foods, meals, recipes, and reuse | Named library item or supplied recipe | Food-library/recipe services; inventory write adapters |
| `profile.personal` | Personal profile and goal changes | Relevant current fields/goals and requested update | Settings proposal and validated save services |
| `profile.training` | Recurring availability, equipment, exclusions, and preferences | Requested preference fields and current values | Training setup/questionnaire services |
| `profile.calibration` | FTP/HR calibration values, sources, dates, and changes | Selected calibration and explicit user measurement/value | Training FTP/HR services; verify update adapters |
| `garmin.status` | Connection, freshness, coverage, and sync/publication state | Relevant status summary | Connection, sync, checkpoints, publication readers |
| `garmin.sync` | Start sync or investigate a specific failure/gap | Current job/checkpoint and reported gap | Sync services; expose bounded job/status adapter |
| `garmin.publish` | Send/update/remove supported workouts and verify result | Exact workout IDs/revisions and remote mappings | Publication and rolling-publication services |
| `maintenance.log` | Log completed equipment maintenance | Equipment, action, date, supplied costs | `log_maintenance` and operation receipts |
| `maintenance.history` | History, corrections, undo, removal/restore, export | Equipment/filter or exact event/revision | Maintenance read/update/undo/export tools |
| `app.data` | Find available datasets and explain missing/partial coverage | Requested information and dataset metadata | App data catalog, scoped queries, import coverage |
| `app.transfer` | Import/export/backups and restore previews | Chosen source/dataset/date scope and operation | Existing import/export/backup/restore services; chat adapters needed |
| `app.dashboard` | Change dashboard layout or saved chart configuration | Relevant current configuration and requested change | Dashboard/chart services; chat adapter needed |

### Dedicated long-term planning skill: `training.programs.build`

This is a broader reasoning workflow with several stages. A small session edit should not load it. When the user asks to build a new plan, the same Sol agent loads this skill and takes the time and context needed to produce a coherent program.

Its catalog description explicitly identifies the larger scope: "Build a new multi-week or season training plan by assessing the athlete, goals, history, constraints, and commitments; retain planning decisions across turns and produce a reviewable program."

#### Inputs it considers

| Area | Relevant planning context |
|---|---|
| Goals and horizon | Primary and secondary goals, priorities, start/end dates, event dates, and what success means to the user |
| Training history | Recent consistency, sport-specific weekly volume, intensity distribution, longer-term trends when relevant, completed-session feedback, and actual tolerated sessions |
| Current state | Recent activity and recovery evidence, interruptions, known limitations, data freshness, and uncertainty |
| Availability and life | Days, time limits, recurring schedule, work/travel disruptions, fixed commitments, and realistic adherence |
| Sports and preferences | Cycling/strength/running mix, priorities, preferred workout types, experience, and enjoyable or disliked sessions |
| Equipment and environment | Bike/trainer/gym access, available strength equipment, terrain, and relevant indoor/outdoor constraints |
| Restrictions | Saved exclusions, disclosed pain/illness/injury, and any supplied professional guidance; unresolved restrictions remain explicit |
| Calibration | FTP/HR settings, dates and sources, sensor availability, and what targets can be supported by the evidence |
| Existing program | Active/future sessions, completed history, previously published workouts, and which future plan the new one would replace |
| Related factors | Relevant nutrition/recovery considerations when they materially affect the requested plan; retrieve narrow evidence first and load another skill only for a distinct task |

These are considerations, not a compulsory questionnaire. Read known information first, identify conflicts or material gaps, and ask only questions that affect the plan. Distinguish user decisions, recorded evidence, estimates, and provisional assumptions. Historical comparisons should use the period needed for the question rather than loading all available history.

#### Staged workflow

1. **Establish the brief:** understand the desired outcome and planning horizon; read saved goals/preferences; retain answers and unresolved decisions.
2. **Assess the baseline:** obtain calculated sport-specific history, training tolerance, recent recovery, and coverage summaries. Drill into individual activities only when needed.
3. **Design the overall structure:** propose phases/blocks, the role of each sport, volume/intensity direction, recovery/review periods, and accommodation of key events. Explain important tradeoffs and assumptions naturally.
4. **Design the practical schedule:** align weekly structure and the initial workout horizon with actual availability, equipment, calibration, and commitments. Validate consistency between blocks and sessions.
5. **Review the draft:** present the program direction and a concrete initial schedule, explain uncertain inputs, and incorporate the user's revisions without repeating the intake.
6. **Activate through the existing reviewed workflow:** preserve completed history, make any replacement of future training explicit, and report the confirmed local result. Garmin publication is a separate capability when requested.
7. **Hand off future review context:** retain the brief, assumptions, block structure, review criteria, and initial evidence references so `training.programs.review` can assess progress later.

Stages are internal working structure, not a demand for seven separate confirmations or seven model calls. The agent can complete several stages in one exchange when the evidence is sufficient. A long-term program does not require generating every detailed workout months ahead; define the full direction and materialize a suitable initial horizon using the app's supported workflow.

#### Continuity and cost

Persist the planning brief, selected record references, evidence dates, decisions, assumptions, draft, and next unresolved question. The user can return later and continue without restarting. Refresh time-sensitive evidence before activation when necessary; do not replay the entire planning conversation or all historical records.

Allow a larger measured context and reasoning budget than a session edit. Load phase design, sport-specific progression, and scheduling references when those stages need them. Token efficiency means avoiding unrelated context and repeated work, while giving Sol enough evidence and reasoning space for a consequential long-term plan.

The skill does not create background monitoring or automatically revise training in future chats. Scheduled reviews or automatic actions require a separate explicit product decision and user instruction.

#### Acceptance cases

- "Build me a new training plan" loads this skill and reuses known information before asking focused questions.
- Goals, history, availability, recovery, restrictions, and commitments meaningfully affect the resulting plan.
- Changing an event date during intake updates the retained brief and affected design without discarding other decisions.
- Returning to an unfinished plan continues the same draft; stale evidence is refreshed selectively.
- A complete program has coherent blocks and a workable initial schedule, with assumptions stated and completed history preserved.
- "Replace today's strength with a ride" remains in session editing and does not load this skill.

## 3. Selection instructions and discovery tools

The proposed "skill for choosing skills" is a small always-available instruction section plus catalog metadata. It does not require loading a selection skill before being allowed to discover other skills, and it is not a second agent.

Proposed discovery interface, for later implementation:

- `find_skills(query, current_skill_ids?)`: search the whole catalog and return a few compact candidate cards, including their paths. Search can cross branches in one call.
- `list_skill_children(path)`: browse one branch when useful. Return descriptions, not full bodies.
- `load_skill(skill_id)`: obtain that leaf's versioned instructions and focused tool schemas. The runtime makes those tools available to the same agent.

These are conceptual interfaces, not tool definitions being installed by this plan. Search can begin with a simple local index of authored descriptions/examples; an embedding service is not required for the first version. Search results are suggestions for the agent, not an authoritative intent classifier.

Selection procedure:

1. Read the message with the current conversation/task. Decide whether it is discussion, continuation, or a new action/question using model reasoning.
2. Answer ordinary education or discussion directly when no app-specific evidence/action is needed.
3. Continue with the relevant loaded skill when it still fits. Do not rediscover it for "today's", "the strength", "yes", or "make it 30 minutes".
4. Otherwise search for the actual requested capability. Load the best-fitting leaf; explore another candidate only if necessary.
5. Use the skill's focused tools to obtain evidence or perform the authorized workflow.
6. Add a second skill only when the request needs its distinct capability. Refer to already selected record IDs/results instead of restarting context collection.
7. Answer naturally using confirmed results. Retain compact task state for the next turn.

No compulsory separate model call for classification, no switch among Trainer/Data Scientist/Nutritionist personas, and no mandatory keyword gate before the model can interpret the message.

### Example catalog card

```yaml
id: training.sessions.edit
path: Training / Sessions / Edit or replace
summary: Change the prescription or replace one planned session.
use_when:
  - The user wants different duration, intensity, blocks, exercises, or sport.
examples:
  - Replace today's strength with the endurance ride intended for yesterday.
  - Make the second work interval four minutes.
nearby:
  training.sessions.schedule: Changing dates while keeping the sessions.
  training.sessions.feedback: Reporting completed work or actual sets.
status: planned
version: 1
```

The full skill body is separate. Neighbor descriptions clarify ownership; they are not a list of automatically loaded dependencies. The displayed example is illustrative, not a new catalog implementation.

## 4. What each skill contains

Use a consistent compact format:

- Purpose and scope, including nearby capabilities it can hand work to when necessary.
- Domain knowledge that the general model cannot infer from app data/schema alone.
- Required evidence and how to obtain it, starting with the narrowest useful query.
- Workflow for interpreting references, preparing a result, and handling continuation.
- Relevant tools, their units/date semantics, and actual supported operations.
- What constitutes a proposal, a saved local change, and a verified external result.
- How to respond to missing data, real conflicts, unavailable capabilities, and failures.
- Representative successful conversations and links to regression cases.
- Version and compatible tool-contract version.

Separate discovery metadata from loaded instructions and extended reference material. For example, `activities.investigate` need not load complete FIT field inventories until an unusual field is relevant. `training.sessions.edit` can load detailed strength or interval references only for that kind of edit; separate leaf skills can be introduced later if measurements justify them.

Tools should accept structured record references and changes where practical. A new conversational skill sitting in front of a brittle free-text parser would leave the same underlying problem. Plan adapters that let model interpretation reach the existing validators without requiring users to phrase requests in special ways.

## 5. Ownership boundaries and shared evidence

| Request | Primary skill | Add another skill only if needed |
|---|---|---|
| Replace today's strength with yesterday's planned endurance ride | Session edit | Source/destination lookup is part of this skill; do not invoke full program design |
| Swap strength and cycling dates | Session schedule | Inspect nearby conflicts through scoped tools; no program generation |
| I did the strength workout yesterday | Session feedback | Editing the calendar is a separate requested effect; do not infer it automatically |
| Was my ride endurance or tempo? | Activity assessment | Investigation only if detailed evidence is necessary |
| Plot power against HR during that ride | Activity plot | Investigation only if the question also asks for interpretation of specific sections |
| Why is my HRV lower this week? | Health trends | Readiness if the user also asks about workout readiness |
| I ate two eggs after my ride | Nutrition log | A ride mention alone does not load training/analysis |
| Change Tuesday's availability permanently | Training preferences | Program revision only if the user asks to rebuild affected training |
| Send the replacement ride to Garmin too | Garmin publication after session edit/save | Carry the exact saved workout revision into publication |
| Log that I replaced the bike chain | Maintenance log | "Bike" alone does not load workout editing |

Reading health evidence for a workout decision does not always require loading `health.readiness`: the session skill can have a narrow readiness-read tool. Load another skill for its procedure or explanation expertise, not merely because a data dependency exists.

## 6. Conversation and context management

One conversation carries the original intent, resolved records, user's clarifications, selected skill/version, current proposal, confirmed results, and pending uncertainties. Switching skills must not erase that state.

Keep a compact task record for important references and operation receipts, alongside enough recent conversation for natural interpretation. Task state supports reasoning; an incomplete field must not automatically trigger a canned question when the conversation or a read tool can resolve it.

Resolve relative dates in the user's timezone and preserve the intended dates across continuation. A past completion date and a future edit target are distinct references. Never infer that reporting a completed workout authorizes rewriting its history.

When moving to a new subject, omit irrelevant skill bodies/tool schemas from the next request. Merely hiding a tool does not remove its instructions from previously accumulated model context: the runtime must manage the actual serialized context. Retain useful conclusions/references without replaying unrelated skill text or every tool result. Do not discard evidence needed for the answer or active operation.

Keep an active task on a compatible skill/tool version through completion. A catalog update should affect new selection without silently changing the meaning of a pending save. If a safety/correctness fix invalidates an existing proposal, refresh that proposal against current records.

## 7. Token efficiency without weakening reasoning

- Keep root descriptions and discovery cards short. Full skills, schemas, and references load selectively.
- Keep the existing Sol reasoning configuration; do not substitute keyword logic for reasoning to improve a token count.
- Query selected dates, sessions, columns, and calculated summaries. Expand to streams/raw evidence when the actual question requires it.
- Preserve current-skill continuity so short follow-ups avoid repeated search and setup.
- Reuse valid evidence; refresh when revisions, data freshness, or scope change.
- Do not assume every skill change needs a separate model call. Measure discovery rounds and model/tool turns together.
- Investigate repeated searches, duplicate reads, retries, and stale context as waste. A legitimate multi-step investigation is not itself waste.
- Measure full input/output usage and provider-reported reasoning usage when available, with estimates clearly labeled. Do not double-count reasoning already included in a provider's output-token total.
- Cache/version stable catalog and instruction material where the current provider supports it. Measure savings instead of assuming that loading is free.

Initial design targets for the pilot: top-level catalog approximately 500 tokens or less; a search usually returns at most three brief candidate cards; ordinary leaf instructions approximately 400–1,000 tokens excluding necessary tool schemas. These are authoring targets to test, not hard stops that prevent completing a legitimate task. Program design may need more reference material.

## 8. Validation around operations

Keep conversational interpretation flexible. Validate concrete operations in the application:

- Referenced records exist and belong to the relevant local dataset/program.
- Proposed changes match current revisions and valid domain constraints.
- Retried writes use operation receipts rather than applying twice.
- Local saves and remote Garmin publication have separate verifiable outcomes.
- Available tools obey the channel's actual permissions and current review/save rules.

This plan does not introduce a new approval policy or an automatic save policy. Preserve the current behavior during the catalog pilot and discuss changes separately. Tools with missing adapters remain unavailable rather than being presented as working capabilities.

## 9. Improving skills after bugs

Each reported bug should include the conversation, expected behavior, selected skill(s), loaded-context summary, tool results, and usage. Use synthetic or privacy-safe reproductions in committed tests; avoid copying private health records into documentation.

| Failure | Likely correction |
|---|---|
| Search finds the wrong branch or leaf | Catalog description, hierarchy placement, examples, or retrieval |
| Agent loads several irrelevant skills | Shared selection instructions or overlapping catalog ownership |
| Correct skill follows the wrong procedure | That skill's instructions/examples |
| Procedure has a distinct missing capability | Add a leaf or subreference, then update its catalog entry |
| Clarification or record identity is forgotten | Context/task-memory integration, not another spelling rule |
| Save/calculation/API result is wrong | Application/tool code and its contract |
| Output claims success after a failure | Skill result handling plus enforceable tool-result semantics |
| Correct result costs too much | Inspect loaded bytes, query scope, repeated calls, and actual serialized history |

Update authored catalog metadata with the skill change so descriptions and bodies do not drift. Keep a small reviewed regression set per skill and a shared set for selection, continuation, and cross-skill requests. Do not add a permanent instruction for every observed wording variant.

## 10. Proposed pilot order

1. Agree on this hierarchy, skill ownership, and the smallest shared selection instructions.
2. Specify catalog-card and full-skill formats; inventory actual tool contracts and missing structured adapters.
3. Author the first five skills: session inspect, session edit, session schedule, nutrition log, and activity plot. These exercise distinct branches and the original reported failure.
4. Compare real conversation outcomes and total usage against the current implementation using the same model configuration. Include multi-turn clarification, mixed requests, discussion-only requests, and failure recovery.
5. Add feedback, nutrition correction/balance, activity assessment/comparison, and readiness.
6. Add the dedicated long-term plan-building skill, major program revision, preferences/calibration, publication, maintenance, and remaining app/data capabilities. Include a full resumable planning conversation in the acceptance set; assess planning completeness as well as token usage. Deeper procedures should follow tool readiness and regression coverage.

### Pilot acceptance examples

- The reported typo-heavy strength/endurance conversation keeps one task and only asks for information still genuinely unresolved.
- A session replacement does not load nutrition, charting, or full program-generation instructions.
- "Today's" resolves the pending reference without keyword-specific clarification code.
- A food report mentioning a ride selects nutrition logging without loading workout editing.
- "Discussion only" produces discussion without preparing or applying changes.
- A request to edit a workout and publish it uses the two necessary capabilities in sequence, preserving the saved workout identity.
- A failed publication reports the confirmed local save and the separate remote failure accurately.
- A repeated save cannot duplicate or reverse the operation.
- Selection accuracy, unnecessary skill loads, model calls, token usage, and elapsed time are measured over complete conversations. Quality is assessed alongside cost.

## Ongoing skill refinement

The shared selection instructions, catalog cards, and all 32 skill bodies now live in `backend/app/skills`. Continue refining individual skills against reported conversations and the regression suite. The original session-change conversation and resumable new-plan workflow are covered by runtime tests.

The implementation removes the previous role router and workflow switch. Existing validated domain services, saved records, provider/model selection, and explicit review controls are preserved.

## References

- Existing app capabilities: `README.md`, `backend/app/ai_tools.py`, domain services, and routes in `backend/app/main.py`.
- Earlier proposal being replaced as the working direction: `docs/planning/three-assistant-architecture-plan-2026-11-03.md`.
- Official OpenAI documentation: [Agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents) and [Guardrails and human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals). The hierarchy, skill contracts, and pilot targets above are proposed application design decisions.
