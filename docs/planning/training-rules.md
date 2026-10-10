# T7 training rules, version 1

Implemented 10 October 2026. Authoritative service: `backend/app/training.py`.

## Saved questions and constraints

Save sports, immediate priority, available weekdays/time/session limits, experience per sport, equipment, manageable weekly minutes, excluded sports/movements, other restrictions, and current pain/illness. Only missing or stale fields become questions. Availability/restrictions/pain expire after 30 days; other answers after 90 days. These freshness periods are engineering defaults. Reconfirmation is explicit and versioned. Goals and personal demographic details are optional. Actual U6 answers are collected through Training during use, not invented during development.

Selected/excluded sport conflicts, missing equipment, fewer than two supported strength movements, current pain/illness, and written clinician restrictions block automatic generation. Free text is not interpreted as permission to exercise. Recent pain feedback requires explicit reconfirmation of the current condition. This prototype has no clinician-review override.

## Weekly draft

Choose a current/future Monday and use the saved IANA timezone. One session per saved day, at most six generated sessions. A day without a new workout is reserved; existing unrelated workouts can still occupy that day. Sports rotate by allocated minutes relative to confirmed weekly volume, with immediate priority breaking ties. Volume is capped by confirmed manageable minutes and each slot; individual new-sport sessions cap at 30 minutes, others at 60. Zero volume creates no workout. Strength sessions need one calendar day between them, including adjacent plans. Existing local drafts and plans participate in conflict checks. Unknown existing duration/timing requires review. Ambiguous/nonexistent clock-change times are rejected.

The draft stores optional active goals, recent feedback, the prior 28 days of recorded activity volume, today's readiness calculation identity/summary, preferences and rule version. History may be incomplete; it provides review context rather than increasing confirmed volume. Today's readiness is advisory, not a forecast for future sessions. The interface exposes this context and session explanations.

## Structured workouts

Cycling and running contain timed warmup, conversational steady work and cooldown, totaling the exact session duration. No FTP, maximum heart rate, pace or zones are inferred. Strength selects one supported exercise per permitted movement using available equipment, with one set for new participants or two otherwise, eight repetitions and 90 seconds rest; the exercise count must fit the session budget. Load stays comfortable with repetitions in reserve. These are foundation templates, not a complete sport-specific periodization system.

The general basis for conversational effort and gradual activity buildup is the [HHS Move Your Way guidance](https://odphp.health.gov/moveyourway/activity-planner/why-these-goals). That source does not validate this application's numeric progression, strength prescriptions, freshness windows or recovery heuristics.

## Review, completion and progression

Drafts require explicit acceptance. Template/duration substitutions recheck availability, weekly volume, equipment, restrictions, conflicts and strength recovery. Completion, skipped/cancelled status, perceived effort/soreness (0–10), pain/illness, notes and optional existing activity links are saved with immutable session revisions. Restoring a skipped/cancelled session rechecks constraints. Editing published workouts requires the separate T8 workflow.

Progression is a read-only proposal based on the two most recent finished, accepted weeks. All relevant sessions completed with effort at most 7, soreness at most 3 and no pain permit a reviewed volume increase of at most 5% or 15 minutes, subject to shared availability. Missing feedback maintains volume. Missed sessions, effort at least 8 or soreness at least 5 propose 20% less volume. Pain blocks planning until reconfirmed. These numbers are provisional engineering defaults, not validated universal safety thresholds. Intensity does not increase. Saving reviewed limits is a separate explicit action and never rewrites existing dates.

Version 1 edits templates, duration and feedback, not session dates. Advanced intervals, automatic goal targeting, automatic activity matching, date rescheduling and Garmin publication remain future work. CSV contains current sessions; JSON and full backup preserve preferences, feedback and revisions.
