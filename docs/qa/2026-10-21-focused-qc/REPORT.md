# Focused pre-trial QC — 21 October 2026

The user agreed to focused QC first, then a week of normal use, followed by detailed all-tab QC. Proposed observation period: 21–27 October, with detailed review from 28 October (Asia/Jerusalem). No background monitoring or reminder was created.

146 tests passed together across sync/recovery, sleep/history, readiness/forecast, casual training adjustments, active plans, trainer-section scenarios, Garmin publication and performance contracts. The 50-request chat/save bank was rerun successfully: 26 reviewable changes, 13 reasoned declines and 11 focused clarifications, using disposable databases. Three sport/goal programs activate and roll their next-seven-day schedules in the trainer-section tests. Garmin publication uses fake providers; the previously user-confirmed live cycling publication remains the real-world evidence. No new Garmin write was made.

Two test-harness corrections were necessary: SQLite snapshots must use backup rather than copying a main file while committed WAL data remains; older active-training tests now explicitly select plan mode and reflect the existing contextual recovery policy (readiness score alone does not force rest). Long-session move tests use a controlled long workout rather than assuming a no-history fixture generates one. Production training rules were not loosened to make tests pass.

Browser checks: active program visible; seven dates 21–27 October; independent today's suggestion returned a 60-minute endurance workout with targets and no saved schedule changes; previous Garmin publication shown as verified.

## Open finding before full trial sign-off

The user's saved Friday 23 October remains 54 minutes, shorter than the 60-minute weekday rides. This is a persisted schedule finding, not covered by declaring the current generator's synthetic fixtures green. A replacement-week preview is currently blocked by an already published session (`Published sessions cannot be replaced locally`). The published workout and personal schedule were preserved. Resolve the local Friday allocation with publication-aware review before claiming the long-ride preference is satisfied. The user then steered work to the nutrition chat; this finding remains open.

This is focused QC, not all-tab business QC or daily-use packaging sign-off. Launch/quit lifecycle and closed-app background behavior remain as documented in the main plan.
