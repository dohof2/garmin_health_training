# Telegram text questions — 26 October 2026

## Hebrew save confirmations — correction, 26 October

Read-only inspection of the live database confirmed migration 034 was loaded and a direct consumed-food report had a successful save receipt. Later Hebrew approval/add/retry messages had completed conversational replies but no save receipts. The defect was the shared nutrition save-intent gate: it did not recognize natural confirmations such as “יש אישור תתעד את זה בנשנושים”, the dictated “מאה אחוז תוסף לסנאקס”, or retry requests ending in “לשמור”. This was not a missing backend restart or a database write failure.

Added bounded pending-food save intent, Hebrew imperative forms, explicit meal-destination selection, retained nutrient/portion estimates and direct proposal saving without another model call where evidence is already sufficient. Legacy pending proposals can enrich their same food identities with nutrient estimates, then save; another model reply cannot substitute new foods/quantities during approval. Already-saved references are confirmed from storage without creating another meal on a new save-again message. Questions about whether saving occurred, negations and hypothetical instructions remain non-writing.

**159 selected tests pass**, including four additional Telegram tests covering the actual command forms with fictional foods, retained estimates, legacy proposal enrichment, negative/status/hypothetical requests and repeated save-again messages. Whitespace validation passes. The previous frontend build remains applicable; this correction changes backend behavior only. No original user report was replayed, personal food saved or live Telegram message sent. The pending proposal and pairing remain in place; restart the app to load the correction, then send an explicit save instruction in Telegram.

Implemented the local Telegram connection after the owner created a bot and saved its token. The owner subsequently reported the bot working. **Text questions and shared-chat meal logging/corrections are implemented**; this is not completion of B0–B5 or the full Telegram plan. Live meal-write verification remains for the owner. The initial question-only checks below are followed by the meal-writing implementation checkpoint.

## Owner setup

1. Quit and reopen `Open Garmin.command` to load migration 033, the backend and built frontend.
2. Open Settings → Telegram → **Connect saved bot**. The app reads service `garmin-app.telegram`, account `bot-token`, from macOS Keychain. Allow access if macOS asks. No token entry in chat or the browser is needed.
3. Open the generated private pairing link and tap Start in Telegram within ten minutes. The paired status appears in Settings. Only the numeric private user/chat pair can ask questions.
4. Send a text question. The Mac must remain awake, online and running the app. `/new` starts a separate Telegram conversation; `/status` and `/help` describe availability.
5. **Disable and unlink** stops intake/delivery and invalidates pairing. History remains local; deletion controls are not implemented in this increment.

## Implemented behavior

The foreground API lifecycle manages an optional worker. Disabled installations never read Keychain or contact Telegram. A file lock beside the database prevents two local consumers of that database. Setup endpoints check loopback client, Host, Origin, cross-site metadata and a custom mutation header. There is no public endpoint, webhook change or background/login service.

Pairing uses 192-bit random codes, hashes, ten-minute expiry, bounded attempts and transactional single use. Groups, wrong users/chats, edits, callbacks and other bots cannot query data. Unpaired messages receive no response or stored content. Authorized updates and offsets commit together. Durable queues deduplicate bot/update IDs, retain conversation turns across restarts and resolve replied-to bot answers within the current conversation. Intake is bounded; oversized or more-than-fifteen-minute-old questions do not invoke inference. Unsupported media is not downloaded.

The adapter reuses the browser's configured provider streams and scoped query handlers, with no paid fallback. Telegram has a separate durable conversation; browser history and selected ride/chart context are not merged. An explicit read-tool allowlist rejects writes, proposals, exports and interactive charts, including unadvertised model calls. Scoped read-only SQLite connections additionally reject writes. Readiness can calculate default/current settings and results without persisting settings or its audit cache in this scope. Browser writes/caching retain their existing behavior.

Replies use plain text and bounded UTF-16 chunks. A durable outbox records sending/sent state. Restart/network ambiguity is marked rather than automatically resent; explicit rate-limit rejections can retry. Settings show worker errors, last poll and uncertain deliveries. Provider exceptions become a generic retry message; request URLs and credential values are not logged. Submitted questions and answers pass through Telegram and the configured provider, as disclosed before pairing. Tokens are never stored in SQLite, API responses or source files.

## Verification and limits

**Final checks: 105 selected tests pass**, including 23 Telegram tests. The frontend production build and whitespace validation pass. The combined test command was `PYTHONPATH=backend:backend/tests .venv/bin/python -m unittest backend.tests.test_telegram_bot backend.tests.test_ai_chat backend.tests.test_ai_providers backend.tests.test_roadmap_workflows backend.tests.test_nutrition_logging backend.tests.test_readiness_v5 backend.tests.test_readiness_forecast`.

Synthetic tests cover pairing/expiry/attempt limits, wrong identities/groups/edits, duplicate intake, durable history/reply context, new conversations, stale/media handling, disable during inference, bot/offset isolation, delivery ambiguity/retries/chunking, Keychain error redaction, read-only tools/database access, local endpoint protections and worker lifecycle. Shared-chat, provider, roadmap, nutrition logging and readiness tests run alongside them. Frontend production build passes with the existing bundle-size advisory. Browser inspection used an empty isolated database on port 5174; the Telegram card and Connect saved bot button were visible. The owner's token was not read and no live Telegram message was sent during verification.

An exploratory legacy `test_ai_tools` run still fails its exact catalog expectation: four tools already present in committed HEAD are absent from its expected list. It is not counted as passing. An initial roadmap import failed without `backend/tests` on PYTHONPATH; the corrected combined command includes it.

Remaining after the meal-writing follow-up: full dataset acceptance, mixed-role/action parity, plan/goal writes, photos, voice, interactive charts, browser continuation, server deployment, delete-history controls and live meal-write sign-off. Failed inference requires an owner retry. No security audit is claimed. Telegram retains pending updates for at most 24 hours, so extended shutdowns may lose messages.

Protocol reference: [Telegram Bot API](https://core.telegram.org/bots/api#getupdates). Setup does not clear existing webhooks or discard pending updates.

## Deferred user requirement — longer offline-message window, 26 October

The user requested extending the current fifteen-minute message-age cutoff later so messages sent while the Mac sleeps or the app is closed can be processed on reopening without routine resubmission. Choose the longer duration during that implementation; no duration was selected yet. Preserve original sent timestamps and timezone when resolving “today”, “yesterday” and meal dates, distinguish historical questions from current readiness/advice, and revalidate any future time-sensitive action before applying it. Test overnight sleep, date boundaries, queued-message ordering and restart/dedup behavior. Increasing the app cutoff cannot extend Telegram's upstream pending-update retention; longer outages would require an always-running receiver. Recorded for later; current behavior is unchanged.

## Settings visibility follow-up — 26 October

The user could not find Telegram and requested a section within Settings. A fresh load of the running app already showed the connection card, consistent with an older open browser page being a possible cause. Telegram is now pinned as the first explicit Settings section, outside saved card ordering and the profile/AI settings loading gate. Renamed the enclosing heading from Assistant settings to Settings and added a Telegram loading status. Rebuilt the frontend and verified the live Settings screen on port 8765 shows Telegram and Connect saved bot. Existing browser pages need a refresh; no token access or pairing was performed.

## Shared-chat meal writes — 26 October

The user explicitly requested that the working bot save/update meals through the application's chat. Nutrition turns now invoke `ai_chat.chat_stream` with the same automatic report logging and meal services as browser chat. Other routes retain read-only tools/database access. Nutrition-target and training writes are still unavailable through Telegram.

Migration 034 retains per-conversation role, pending foods and saved meal IDs/revisions. Stable `telegram:<bot>:<update>` identities reuse the existing atomic nutrition operation receipts. Recovery after a domain commit returns the saved result without repeating inference or adding meals, including after the normal fifteen-minute age gate. Original sent time anchors meal dates across midnight. `/new` creates a new context; it does not erase meals. Pairing survives migration/restart.

An authorization callback rechecks the enabled bot, owner/chat and conversation inside the same transaction that saves a meal, so unlink during inference blocks the write. Shared chat also supports one named gram-quantity correction against saved meal references, with revision validation and receipt replay; ambiguous names ask for a full food/amount correction. Other food items, original meal date, nutrient sources and uncertainty are preserved. Multi-food arbitrary edits, replacement/deletion and media are not claimed. Questions, hypotheticals and negated instructions do not save meals. Only persisted outcomes produce saved confirmations; uncertain processing errors ask the owner to inspect the log before retrying.

The browser chat retains saved meal references for these same corrections. The visible Nutrition panel refreshes its day data every five seconds and on return/focus, without resetting an unsaved form. Settings describe meal support and show a restart notice when connected to an older question-only backend.

**155 selected tests pass**, including 15 Telegram nutrition cases covering Hebrew reports through the shared entry point, calorie rescaling, same-row correction, unchanged other foods, ambiguous/stale revisions, duplicate delivery, crash-after-commit replay, unauthorized senders, unlink during inference, negation/questions, original-date midnight handling, pending-food continuation and target/training write restrictions. The selected existing Telegram, nutrition, shared-chat, roadmap, provider and readiness suites pass together. Production frontend build and whitespace validation pass. No actual user food report was replayed, personal meal saved or live bot message sent. Restart the normal app to load migration 034 and this backend; then send a new meal report for owner verification.
