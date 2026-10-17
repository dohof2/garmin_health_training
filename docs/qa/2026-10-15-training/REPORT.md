# Training flow implementation QC — 15 October 2026

Specification: [detailed execution handoff](../../planning/training-tab-flow-proposal.md).

## Implemented

- Training-only composer wording and Send action.
- Explicit duration choices/confirmation, read-only candidate preview and final approval.
- Atomic brief/preferences/program/session approval, durable retry identity, revision conflicts and rollback.
- Abandoned replacement drafts preserve the active schedule; approved replacement preserves completed history.
- Retained Garmin cycling FTP discovery with date/provenance, manual override and 90-day calibration policy. Local stored candidate is stale, so fresh numeric targets must not be claimed.
- Separate today suggestion, seven local calendar dates, readable sport/type colors/icons and one expanded workout detail panel.
- Active-plan editor with fresh brief, cancellation, preview/approval, availability, sport mix, weekly minutes, goals/events, session title/time and cycling duration.
- Duration follow-up continuation in the trainer conversation.

## Verification

- Backend: `PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests` — 427 tests passed after implementation (baseline 416; includes focused synthetic FTP and override cases).
- Frontend: `npm run build --prefix frontend` — TypeScript and Vite production build passed.
- `git diff --check` — passed.
- Focused approval coverage includes explicit duration, retry, stale context, candidate preference isolation and transaction rollback. Legacy remediation tests now approve candidate changes explicitly rather than expecting saving a brief to mutate a plan.
- All mutation tests use temporary databases. The user's active plan was not activated, edited or cancelled during validation.

## Outstanding manual verification and limits

- Browser verification could not run: computer-use tool reported `Browser is not available: iab`. New discussion → duration → approval → reload, keyboard operation, mobile layout and selected-workout refresh need manual browser QC.
- Noncycling session duration/exercise prescription editing is not included in the candidate editor; title and scheduled time remain editable for all sports. Strength prescription details continue to use existing lap rendering.
- No live connected-model conversation was exercised. Duration continuation is covered through existing synthetic conversation checks; broader multi-turn model behavior remains manual QC.
- Dedicated browser calendar DST/midnight and multiple-session interaction assertions remain outstanding.
- The other QC backlog items (readiness speed, VO₂ trend, general assistant wording, activity sync and Explore dates) are outside this change.

## Follow-up corrections

- Duration is asked early in trainer chat, with no duration picker in Upcoming plan. No roadmap or weekly sessions are generated before confirmation. A duration reply continues the pending proposal.
- Roadmap summaries show grouped blocks and week counts with event-aware phases. Weekly generation uses original program start/current block, including reduced recovery/freshen/race dose; workout details retain their block identity.
- Today-only conversational suggestions ask missing available time, retain the ride context for “60 minutes”, and work without an active plan. They remain read-only. Explicit long-term goals take precedence when a message also mentions today.
- Active review retains existing readiness, HRV/RHR deviations, sleep, acute/recent demanding load, effort/soreness/notes and pain safeguards. These constrain current planned work rather than invent future health. Missing data warnings remain visible. Same-block healthy/poor-recovery regression coverage verifies different safe dose.
- Review surfaces approved versus latest dated FTP and measured change. New measurements require a reviewed target update; automatic fill/reconciliation keeps the approved FTP snapshot. No FTP improvement is inferred from a single ride.
- UI preserves the approved “Your personalized training plan starts here” heading and shows block summaries/current block/FTP progress.
- Backend restart was attempted but sandbox denied stopping the existing process, and its escalation was interrupted. Changed backend routes require a restart before live browser validation.
