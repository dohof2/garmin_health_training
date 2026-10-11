# Assistant QC follow-up — 11 October 2026

Current FIT follow-up: [FIT-INTERVAL-QC.md](FIT-INTERVAL-QC.md) supersedes the earlier unresolved lap/time-series finding. Four new scoped tools, numeric FIT-field plots and sprint detection are implemented; 1,044 activities/7,401 laps recovered without errors, 333 backend tests pass, and eight live FIT questions were checked with targeted retests. The original limitations below are historical checkpoints; 18 activities without a recovered inventory remain explicit gaps.

## Current ChatGPT trainer checkpoint

Read [CHATGPT-TRAINER-QC.md](CHATGPT-TRAINER-QC.md) for the current provider work and live retests. ChatGPT/Sol Light uses a separate trainer conversation with application tools, bypassing the Qwen routing and canned-response path described in the historical results below. Latest backend regression: 320 passing tests; frontend build passes. Full isolated live retest completed: 143 unique cases answered without runtime errors after targeted fixes; reviewed flags and remaining limitations are in the trainer report.

The user identified a material remaining data gap: lap messages are not persisted, and assistant tools expose aggregate sample statistics instead of continuous ride investigation. One original FIT file contains 11 laps and 1,786 records, decoded without errors; the app has 2,937,459 samples across 1,057 activities but no saved `fit_laps`. Do not certify interval analysis or complete FIT-field access. See the trainer report for the local read-only verification and follow-up work.

The assistant now handles common ride comparisons and health questions with concise, evidence-based answers. This extends the original QC repairs; it does not certify every application control or every possible question.

## Latest correction: ordinary comparison defaults to records

The user reproduced **“how was my ride compared to other rides in the kast 3 months?”** receiving GPS matching. The previous QC bank did not cover “my ride” without “last/latest” or this date typo, and its scope clarification expectations were too narrow. Passing that bank was not evidence of reliable everyday conversation.

Ordinary ride comparison now defaults directly to general records. GPS matching requires an explicit matching/GPS/same-route request; model-selected matching tools are guarded as well. “My ride” enters the latest-ride comparison flow and “kast” is normalized to “last.” Missing date ranges still ask for a period. Explicit scope-changing follow-ups retain dates. This supersedes the earlier preference to ask a GPS scope question.

**297 backend tests passed** in 10.910 s before the final timing follow-up. **24/24 focused comparison acceptance cases passed**, including the exact reproduction and explicit matching follow-ups; local evidence is `assistant-default-comparison.json`. Browser verification of the exact question returned 35 comparison rides over 11 July–11 October 2026, numerical medians, personal interpretation and recorded training benefit, with no GPS matching. The earlier 133-case result below is a historical checkpoint; the maintained bank now has 134 cases.

Comparison timing also supports days, weeks, months and years, including “over 3 months” and short period replies such as “3 months.” A number without a unit asks which unit was intended. **Final timing regression: 298 backend tests passed.** The exact missing-unit question and “3 months” follow-up are covered. See [backend-default-comparison.txt](backend-default-comparison.txt).

## Repairs completed

- Broad latest-ride questions ask **All rides, or rides on the same GPS route?** when ambiguous. Natural replies retain the original period. Missing periods are clarified. GPS matching uses the actual latest ride as its reference.
- Calendar periods and rolling intervals are distinct and displayed. Date filters survive “all rides” scatter requests. Compact date typos and spelled numbers are supported.
- Health answers distinguish totals, averages and dated changes. A single measurement date cannot establish a trend. Ride inventories exclude hiking, removed records and synthetic fixtures.
- Body Battery, rolling-window and aggregation clarifications accept follow-ups. Wider plots and multiple independent plots retain their requested measurements and periods.
- Invalid local model tool calls receive a validation-guided retry. Health-history questions cannot substitute training settings for measurement data. Capability questions use the real catalog.
- Answers lead with the result and omit generic coaching paragraphs. Training previews retain warnings, ask for missing details and save nothing automatically. Multiple fixed training days, independent durations and common weekday typos are preserved; training today is not silently scheduled into a weekly preview.
- Ride comparisons add a brief personal interpretation from recorded duration and average power. Recent riding time is compared against the middle 50% of up to eight preceding seven-day windows with complete recorded durations; at least four nonempty windows are required. Empty weeks are not assumed to be inactivity. This describes recorded riding time, not physiological training load. Mean power does not justify “steady throughout.”
- The ride answer includes **Garmin's recorded primary benefit** and aerobic/anaerobic Training Effect. Source labels identify endurance/base, tempo, threshold or other benefits when available. Retained single-session FIT scores are supported; numeric scores alone never invent a primary category, and multisport session scores are not assigned to the whole activity.

Garmin documents primary-benefit labels separately from aerobic/anaerobic scores: [About Training Effect](https://www8.garmin.com/manuals/webhelp/GUID-31D23DBB-57C2-4DF7-A0C9-8D1A00AB4BE7/EN-US/GUID-7275629E-743A-4658-A284-C84F42A66AE5.html). The latest stored ride has an explicit Aerobic Base label, with both effect scores also retained in its FIT session.

## Verification

The reproducible [question bank](ASSISTANT-QUESTIONS.md) contains **133 human-language cases**. [The runner](../../../scripts/run_assistant_acceptance.py) exercises the real FastAPI chat endpoint on an isolated SQLite copy, with real local Ollama calls where the app requires them. Common deterministic requests pass through the same endpoint without a model call. Counts must not be described as 133 independent model completions.

Initial live execution failed 14 of 125 cases, primarily verbose training responses and model tool routing/arguments. Reviewing actual answers additionally caught a non-ride inventory and an unsupported single-date trend. A later expanded case caught FTP improvement being routed to the chart catalog; that routing is now corrected. Numeric checks independently query SQL for ride counts/medians and health sums/means/counts. Dedicated fixtures cover missing data, removed/synthetic exclusions, dated endpoints, training commitments, volume quartiles, FIT-only effects and missing benefit labels.

Private answer/evidence files remain local and excluded from Git: `assistant-acceptance-live-initial.json` and `assistant-acceptance-final.json`. The bank's expected dates are fixed to this snapshot; update them before a later-date run.

Browser checks on the running app verified both scope choices, this-year and trailing-year periods, the personal ride summary, the recorded primary benefit and a standalone benefit question. The newest comparison's answer start was visible at 88.5 px in a 954 px viewport after completion. No training proposal was saved and the user's unfinished Training form was preserved.

Final checkpoint:

- **133/133 assistant cases passed**, with **8 actual local-model requests**. Longest answer in the isolated snapshot: **112 words**. The production browser comparison has more retained fields and a longer grounded answer; the word count is not a universal hard cap.
- **295 backend tests passed** in 11.389 s. The final log is [backend-assistant-followup.txt](backend-assistant-followup.txt).
- **Eight independent acceptance probes passed**: [acceptance-assistant-followup.txt](acceptance-assistant-followup.txt). Clarification is accepted only when it explicitly identifies the ambiguous Body Battery measurement or requests separate aggregation/rolling plots.
- Frontend TypeScript/Vite build and `git diff --check` passed.

| Category | Cases | Passed |
|---|---:|---:|
| clarification | 8 | 8 |
| ride | 18 | 18 |
| plot | 32 | 32 |
| summary | 16 | 16 |
| followup | 15 | 15 |
| readiness | 6 | 6 |
| training | 10 | 10 |
| unsupported | 6 | 6 |
| model | 12 | 12 |
| multiplot | 4 | 4 |
| clarification-followup | 4 | 4 |
| benefit | 2 | 2 |

## Remaining scope

OpenAI mode has no configured key and was not exercised live. Free-form reasoning is not exhaustively certified by the bank. Source labels may be absent on older activities; absence must remain explicit. General QC still needs the original report's unverified conditional controls, full historical authenticated sync, nutrition photo paths, production-sized restore and formal accessibility checks. No external Garmin writes occurred. Changes from this follow-up are local and uncommitted; baseline commit is `6815f23`.

## ChatGPT account connection checkpoint

The user requested using their existing ChatGPT account instead of separately billed API access. Added a separate ChatGPT provider using the official local-client OAuth flow: loopback callback, PKCE, one-use state, signed ID-token verification (issuer, audience, expiry, nonce and returning-account subject), protected backend credential file, serialized renewal, account model catalog and explicit sign-out. The assistant uses the public Responses endpoint with streamed, unstored requests and namespaced data tools. Failed or unfinished streams are errors; there is no paid fallback. Migration 020 preserves the existing provider settings.

Verification: **311 backend tests pass**, including **13 new offline account/security/stream checks**, plus the frontend TypeScript/Vite production build and `git diff --check`. Evidence: [backend-chatgpt-connection.txt](backend-chatgpt-connection.txt). Tests use isolated temporary credentials, mocked network responses and signed test identities; they do not certify live account eligibility or inference.

Browser verification on the real local app: Settings loaded, ChatGPT was selected and saved, Continue with ChatGPT generated a valid authorization URL, and navigation reached OpenAI's actual sign-in page. A visible fallback link handles blocked popups. User authentication and permission consent are pending; no access/refresh credentials have been received and no health records were sent to OpenAI in this verification. After sign-in, refresh models, select an available model and save; live assistant QC remains pending.

Mobile status: the UI can be served to a phone by a future authenticated backend deployment or network setup, with credentials retained on the backend. **Current services bind to 127.0.0.1 and are not phone-accessible.** Current OAuth sign-in must finish on this computer. Native mobile packaging and mobile-only sign-in are not implemented or tested.

Protocol references: [OpenAI sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions), [models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference). Eligibility and shared plan limits remain subject to OpenAI's current preview rules.

## External-browser callback failure follow-up

User reported a failed callback after Chrome login. Backend logs confirm two HTTP 400 callbacks, but the previous generic error handler did not preserve a diagnostic, so the original cause remains unconfirmed. Fixed two usability defects: new attempts no longer invalidate other fresh attempts (up to eight, ten-minute expiry and one-use state remain), and Settings can copy a fresh authorization link directly for Chrome. Callback errors now distinguish stale state, denied authorization, missing registration/code, network/HTTP failure and identity verification without echoing tokens or upstream payloads.

Verification: 313 backend tests and frontend build pass. Browser verified the new copy button and its success message after the backend restart. Chrome inspection was blocked by automatic approval review; user consent/retry and live model/inference checks remain pending. Old links from before the restart cannot succeed; use the newly copied link.

## Confirmed TLS failure and repair

The user supplied the network-failure callback message. Credential-free probes outside the shell sandbox reproduced `SSLCertVerificationError: unable to get local issuer certificate` against both OpenAI discovery and token endpoints. Framework Python's default CA file is absent. The installed certifi bundle successfully verifies the connection (discovery HTTP 200). OAuth HTTP requests and PyJWT signing-key downloads now use an explicit verified TLS context from that bundle; hostname and certificate validation remain enabled. Actual backend discovery and JWKS fetching passed with four signing keys available.

315 backend tests pass, including verified-TLS and safe certificate-error checks. Backend restarted; fresh Chrome link copied through Settings. User retry and authenticated inference remain pending. This supersedes the earlier unconfirmed network-failure diagnosis.

## Live account connection confirmed

User completed sign-in successfully. Actual Settings refresh loaded the account model catalog; GPT-6.1 Sol was selected and saved, with `reasoning.effort=low` (Light). Provider readiness showed Ready. A live backend connection test using only a harmless instruction, no tools, no health records and no chat history returned exactly `Connection works.` through the ChatGPT account provider. Account sign-in, model discovery and basic streamed inference are now verified. Personal-data assistant/tool quality, live renewal, revocation and mobile deployment remain pending. Existing 315-test offline checkpoint still applies; no new source changes in this confirmation.

## Settings presentation cleanup

User requested removing the confusing Astra field from the current ChatGPT setup. Settings now shows fields only for the selected provider: ChatGPT model/account, local Ollama model, or separate API model/key instructions. The current account has one compact connected summary, Sol Light explanation, Refresh models and collapsed Manage account actions. Removed the three-provider status grid and inactive API/Ollama fields from the ChatGPT view. Existing saved provider configuration remains available when explicitly selected. Frontend production build and whitespace checks pass; browser verified the connected ChatGPT layout and local-provider field switching, then restored ChatGPT without saving a provider change. Backend was unchanged; existing 315-test checkpoint applies.

## Personal-data source boundary

User required personal data to come from Garmin rather than the OpenAI account. Audited authentication and assistant/provider paths: no ChatGPT history, memory or userinfo import exists; model requests receive only app conversation, Garmin/local tool results and app instructions. Future authorization scopes no longer request `profile` or `email`. Removed persisted account email and retained identity tokens, including existing credentials; account labels are generic. ID tokens are validated transiently for sign-in security, while opaque subject/client identifiers and access/refresh credentials remain only in backend authentication storage. They are never model context. Existing upstream grants are not retroactively revoked by this change; no profile/userinfo request uses them.

Added a grounding instruction forbidding claims of access to OpenAI profile/conversations/memories and a clear Settings data-source description. 316 backend tests and frontend build pass. Existing account remains connected after local metadata cleanup. No personal-data inference test was sent to OpenAI during this change.
