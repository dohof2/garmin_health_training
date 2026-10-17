# Trainer start date and review action repair — 16 October 2026

User authorized implementation after observed live two-turn failure. Preserve production chat/plan.

1. Trace actual shared questionnaire, assistant evidence and preview state. Treat requested program start separately from session clock times. Resolve “you can start tomorrow” using browser timezone/current local date, persist candidate start and provenance, retain all existing schedule facts, and ask only unresolved clock/budget details.
2. Preview/roadmap/approval use the agreed start without Monday normalization. A Saturday rest start remains a rest day; first seven calendar days run from requested start while recurring workouts honor weekday mapping. End date derives from agreed16week span. Automatic rolling review retains original program start anchor.
3. Review action carries current candidate evidence or refreshes canonical pending state, triggers preview reliably when Training is already mounted, and scrolls/focuses the review after render. Avoid stale context overwriting requested date. De-duplicate raw missing questions and keep focused next action.
4. Tests exact original16week user request followed by “you can start tomorrow”, timezone/date boundaries, candidate→review→approval date consistency and recurring rest days. Frontend build and actual isolated browser review scroll/focus if available. No production mutation/reload or live account write. Parent owns restart.

## 17 October: optional clock time

User authorizes removal of mandatory session clock times. Accept nullable availability start_time; retain explicit scheduled_date/time_unspecified metadata while preserving existing timestamp storage as an internal timezone-safe anchor only. UI renders date only for unspecified sessions. Validation, preview, approval, rolling fill/review and edits must preserve this distinction and legacy timed sessions. Parent owns conversational state/replies; implementation agents own scheduling/UI. Tests cover date-only16week activation and timed compatibility, no production mutation.
