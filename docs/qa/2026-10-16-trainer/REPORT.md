# Trainer conversation repair and older-QC consolidation — 16 October 2026

Plan written before execution: [trainer conversation QC repair plan](../../planning/trainer-conversation-qc-fix-plan.md). This report supersedes pending trainer findings in [general QC](../2026-10-15-general/REPORT.md); original observed failures remain historical evidence.

## Repairs

### User QC notes — 17 October 2026 (repaired; see latest evidence)

These original reports are retained as history. Implementation and current verification: [17 October trainer QC](../2026-10-17-trainer/REPORT.md).

- **Keep clarification replies concise.** When filling missing details, ask the next relevant question without repeating retained cycling/strength days, weekday ranges, Friday limits, setup summaries or activation disclaimers on every turn. Show a consolidated setup summary at meaningful review/change points instead. The user specifically found the repeated “I have kept cycling…” availability recap irrelevant while answering questions. Verify a multi-turn clarification sequence remains focused and does not lose retained facts. Pending implementation.
- **Accept natural, contextual answers.** Interpret replies using the pending question rather than requiring exact formats or standalone commands. Examples: “about 5” when asked how many repetitions should capture an approximate capacity of five for the exercise being discussed; “morning” should be understood as a broad time preference rather than rejected for lacking HH:MM. Preserve approximation/uncertainty, do not invent an exact clock time, and clarify only genuine ambiguity (for example which exercise if two were asked together). The separate note below makes time-of-day questions unnecessary for ordinary planning. Add regressions for short replies, approximate counts, broad preferences, ambiguous replies and retained context. Pending implementation; no app changes made for these notes.

- **Do not require a workout time of day.** The user considers clock time irrelevant to trainer planning. Ask for available training days and duration limits, but do not ask for or block plan generation/activation on a session start time. Preserve explicitly supplied times as optional information. Review scheduling/storage assumptions so date-only workouts do not invent a user-confirmed clock time; ask for timing only in a later workflow that actually requires it. Recorded for later implementation; no app changes made for this note.

Durable validated questionnaire state stores partial actual-user answers/provenance, schedule ranges, confirmed times/budgets and pending questions across turns and setup saves. A schema-validated structured extraction path requires supporting user quotations; deterministic extraction remains a fallback. Assistant messages cannot supply user facts. History-supported cycling experience avoids repeated experience questions, while weekly manageable volume still requires user confirmation.

Stored FTP authorization is separate from measured date/source: authorizing225W on16October retains11June measurement and stale status. Stale reference does not enable fresh numeric targets. Save response and UI now state preferences/calibration/direction saved, schedule inactive. Direct Review proposed plan loads fresh canonical state and shows remaining blockers or16week blocks/first7days with final explicit activation. Activation status comes from persisted response.

Actual isolated browser Save→Review exposed a further zero-strength-capacity blocker. Beginner prescriptions now use supported bodyweight wall pushups instead of unsupported dips and omit unavailable pullups, preserving squat/hinge/core and explaining substitutions without inventing equipment. Preview fingerprints no longer vary merely because requests occur at different instants.

## Older items executed

- Running/strength session duration and strength sets/repetitions/rest/load edits now use candidate preview and explicit approval.
- Shared UI calendar utility passes3 executable tests: Jerusalem spring DST, autumn repeated hour, local midnight/year boundary.
- Nutrition25 regression tests pass, including recipe scaling, target preview/save guards, DST and mocked vision success/failure boundaries.
- Export5 tests pass, including safe CSV, backup/restore roundtrip, unsafe-path rejection and original byte preservation.
- Original independent acceptance8 probes pass. Original numbered QA01–14 and FIT/OAuth repairs remain superseded by their later reports, not reopened historical failures.

## Verification checkpoints

- Full backend:449 tests passed16.754s on final checkout; focused training65 and questionnaire8 pass.
- Frontend build and whitespace checks passed; calendar3 tests pass.
- Questionnaire temporary-database E2E covers reproduced16week opening→partial duration/time→225W authorization→budget/restrictions→setup Save→fresh preview→explicit activation, with no plan before approval.
- Parent is exercising actual UI Save/Review/activation on disposable service18016; final browser outcome follows separately. Production conversation/preferences/active plan untouched.

## Remaining boundaries

Historical authenticated whole-account sync, account-specific missing original FIT files, live vision/renewal/revocation, device behavior, full formal screen-reader accessibility and production-size restore are external/manual checks; isolated unit checks do not certify them. Garmin publishing remains planning-only. No real Garmin writes occurred. Production backend requires restart after code verification; parent owns restart.

## Final actual browser evidence

Parent browser passed actual **Save setup → Review plan from saved setup → Approve and activate** on isolated port18016. The initial attempt exposed the zero-capacity strength blocker above; after its repair and isolated-service restart, fresh review showed16weeks,435cycling minutes and60strength minutes. Approval produced a visible active plan19October–7February (`plan-approved624c…`), next7days with threshold/strength/endurance, and expanded strength details with wall pushups.

Evidence: [activation screenshot](browser-activation.png). The chat setup card was deterministic synthetic fixture output; Save, canonical preview, approval and active-program rendering used real application routes and a disposable database. This verifies the UI action chain; it does not claim live-model extraction reliability or real personal-data plan quality. Multi-turn questionnaire extraction is separately covered by eight temporary-database tests. Mobile/keyboard/formal accessibility remain uncertified. Production was not mutated; parent handles production restart independently.

## Review link and requested start date follow-up

Fixed same-page review navigation/focus, partial-summary handling and stale evidence. Review recomputes the canonical pending candidate with request race guards. “You can start tomorrow” resolves once in the user timezone and persists its actual date; preview, activation and rolling generation support non-Monday anchors without shifting weekday availability.

Verification: 451 backend tests passed in 28.902 seconds; frontend TypeScript/production build and whitespace check passed. Exact opening/follow-up and local-midnight persistence regressions cover saving and activation. Isolated browser on port18017 received deliberately stale partial Monday evidence: clicking Review focused training-plan-review and displayed a ready preview beginning October17 with all16 blocks anchored to that date. No live preference or plan changes. Screenshot: [review and tomorrow](review-tomorrow.png). Live connected-model behavior remains unverified.

### Named start dates

Trainer date parsing now accepts “start in Oct 19”, “start on October 19”, “October 19th, 2026”, “19 October 2026” and abbreviated months with a period. Dates without a year use the current local year. Invalid calendar dates and past dates require clarification; no implicit next-year rollover. Focused questionnaire tests cover named-date persistence, explicit next-year dates, leap days, invalid dates and past dates.

## Partial proposal review crash — repaired

Observed real browser blank Training page: TypeError reading cycling from undefined weekly_minutes in TrainingCoachPanel. Partial candidate answers were incorrectly typed as complete preferences. Display now merges sparse candidate fields with saved preferences/default collections without adding defaults to submitted candidates. Explicit empty arrays remain meaningful. A second missing equipment key in backend strength preview now returns clarification instead of raising KeyError.

454 backend tests pass; 6 Node frontend tests pass; production TypeScript/build and diff whitespace checks pass. Browser on isolated18018: chat Review link with sparse sport-only candidate opens focused Details needed, renders16week blocks and missing fields, retains inactive approval, no console errors. This verifies incomplete review rendering; missing answers still require completion. [Screenshot](partial-review.png). No real preferences or plans changed.

## Approval disabled-state follow-up

Observed real preview had zero workouts and needs_input status; disabled Approve was accurate but unexplained at action location. The UI now gives the specific reason, labels incomplete schedules “Plan incomplete — finish details first”, and provides “Complete plan details in chat” which focuses/prefills a request for only the next missing detail without submitting it. Ready preview equality now compares object content canonically, preventing key-order differences from blocking unchanged approval; array ordering and actual edits still matter. No validation was bypassed and no real plan activated.

Verification: frontend build and7 Node tests pass, including equal-content/different-key-order approval regression. Actual isolated browser18018 verifies incomplete blocker label, actionable continuation and focused prefilled chat; screenshot [approval recovery](approval-recovery.png). Backend unchanged in this follow-up; prior454-test checkpoint remains applicable. Live model completion of all missing details is not certified by this UI test.

## Conversational completion flow

Incomplete coaching responses no longer offer a review link. An incomplete review automatically places the retained next question in trainer chat and focuses the empty answer box; no extra continuation click or generated user message is required. Backend persists/exposes its next question with the pending draft; older drafts fall back to actual preview questions. Review/activation content appears only for ready plans. Duplicate saved-preference questions live inside optional preferences with a distinction from newer chat answers.

454 backend tests pass (18.356s), including pending next-question persistence; frontend7 tests and production build pass. Isolated browser18018 verified same-page review→one next question in chat, no premature review link/activation and focused composer. [Screenshot](chat-next-question.png). Live connected-model broader dialogue remains outside this UI check. No real plan or preferences changed.

## Weekday range versus Friday exception

Preserve ride availability range60–90 independently from Friday long-ride allowance300minutes, including wording with hours before Friday. Do not require a single fixed weekday duration; use range upper end as an availability ceiling, leaving actual workout dose to existing budget/block/recovery rules. An explicit later weekday duration choice leaves Friday intact. Ride-days-except clause derives cyclingMon/Wed/Fri/Sun and possible strengthTue/Thu/Sat instead of treating excluded cycling days as ride days or replacing recurring ride days with Friday only. Trainer summary explicitly acknowledges both limits, distinguishes availability from required dose.

Regression reproduces supplied wording and verifies range, sport days, Friday300 versus ordinary-day90 after time confirmation and Friday300 versus ordinary-day60 after explicit override. Full backend455 tests pass16.826s; whitespace check passes. No real saved preferences/plan changed.

## Open conversation loop — 17 October 2026

User reports the trainer repeatedly asks for missing parts and cannot finish the plan. Fix together with optional time-of-day, concise clarification and natural contextual answers. Acceptance requires approximate repetition replies to fill the specific pending exercise, repeated short answers to advance different fields, no required clock time, durable progress and a reviewable plan which activates only on explicit approval. Implementation/verification follows below.
