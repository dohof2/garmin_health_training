# Friday allocation correction — 22 October 2026

## Cause and correction

The shared preview already prioritized the longest available cycling slot, but
active-plan review used proportional reductions and never restored a saved
shortened long ride. Its four-week reference also advanced every day, changing
one week's budget as uncompleted days elapsed.

The shared volume estimate now anchors the four completed seven-day reference
periods to the program week (Monday for plans without a program start). The
reference advances at the next week boundary; current load, feedback and recovery
still apply immediately. Future-week previews use the latest completed reference,
not invented future activity. Up-to-20% progression still requires recorded
tolerance and suitable load; recovery/taper weeks cannot receive that increase.

Active review now uses the shared purposeful-ride allocator, giving the uniquely
longest cycling slot priority. It reserves past planned/completed and published
sessions, preserves fixed commitments and manual adjustments, respects shared
daily availability, and keeps strength outside cycling's weekly budget. It edits
only eligible local sessions rather than replacing the whole plan. Whole-plan
replacement around published sessions remains intentionally restricted.

The review policy/fingerprint changed so an earlier same-day review cannot hide
the correction. New manual edits and saved casual adjustments retain an explicit
marker so automatic allocation cannot expand them again. A tight budget omits
unsupported filler rides rather than making the designated long ride the shortest.

## Saved plan and UI

The saved current week now has a 264-minute cycling ceiling, with Friday allocated
84 minutes and Sunday 60. Current recovery evidence still limits tomorrow's Friday
ride to 60 easy minutes. The card explicitly says “Recovery-adjusted · planned
1h 24m”; its details explain the temporary cap. This is not an 84-minute workout
prescription while the recovery restriction remains active. With normal recovery,
the regression fixture restores the full 84-minute long-endurance prescription.

A consistent local SQLite backup was taken before the repair. The actual saved
week was reviewed, SQLite quick_check passed, and every published workout row was
identical before/after. No new Garmin publication or remote update was performed.
The browser card and detailed recovery explanation were checked locally; the
personal screenshot remains ignored by Git at `friday-recovery.png`.

## Verification

- 213 selected backend tests passed together, including the complete 12-case
  allocation regression suite and advanced cycling cases.
- Coverage includes persisted 54-minute Friday/48-minute Sunday repair to 84/60,
  exact step duration, stable refresh, past/future published reservations, manual
  overrides, recovery limits/weeks, tight budgets, shared daily strength time, multiple cycling slots within one daily limit and
  reference-week rollover. Production frontend build and whitespace checks passed.
- An additional 80-case legacy trainer run still has 17 failures and 14 errors.
  Running the same selection against committed `8e5cc21` in an isolated checkout
  produced the identical failing-case set; this change introduces no new failures
  in that selection. The full historical suite is not green or signed off.

Next: normal-use trial, then detailed all-tab user QC. Existing managed daily-use
sessions need Quit and reopening to load changed Python code; development reload
and the repaired saved database were verified in this session.
