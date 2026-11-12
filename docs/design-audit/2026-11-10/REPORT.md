# UI and usability assessment — 10 November 2026

## Verdict
The app has useful depth, readable activity summaries, explicit data gaps and review steps. Its visual hierarchy gives too many containers and controls equal importance. Repeated white cards, large radii, pill buttons, nested fieldsets and long forms produce a generic administration-tool feel.

Recommended identity: **a personal endurance training journal**. Use warm off-white backgrounds, dark forest-green navigation and primary actions, charcoal text, restrained ochre accents, expressive headings and crisp tabular numbers. Let training timelines and recorded data provide character. Keep chart and status colours meaningful and accessible.

This is a captured review and design proposal; application source was not changed.

## Scope and evidence
Reviewed all nine navigation destinations in the running local app and expanded an activity, workout time settings and training preferences. Screenshots were captured in this run, saved and inspected. Default desktop viewport was approximately 1265 × 712. This covers entry screens and selected settings interactions, not every downstream flow. No chat requests, publications, form submissions or account changes were initiated. Starting the backend also starts its existing automatic services; Data & sync displayed an automatic sync in progress.

## Highest-impact recommendations

1. **Give daily decisions priority** — Dashboard, Training, Health and Nutrition.
   Put today's workout, available readiness information and logging actions first. Dashboard currently opens with a large zero-intake nutrition card; Training opens with publication instructions; Health leads with a missing score. Nutrition's totals and manual editor follow a second chat composer. Move supporting instructions and customization behind clear secondary controls. Retain uncertainty labels and review steps.

2. **Make chat available without reserving a permanent empty column** — every captured desktop screen.
   The empty chat occupies roughly 340 px of this viewport, narrowing charts, calendars and forms. Offer a persistent assistant button and an optional docked panel. Contextual actions can open the same assistant with the relevant activity, date or meal context.

3. **Replace nested settings blocks with summaries and focused editors** — steps 8, 10–13.
   Use rows with a label, current value, short explanation where needed and an Edit action. Show related fields when editing. Keep explicit saves for related changes, previews for consequential changes and visible saved/unsaved feedback. Preserve entered values and keyboard focus when closing or reopening editors.

4. **Reduce decoration that competes with content** — all screens.
   Use section spacing and light dividers for ordinary groups; reserve enclosing surfaces for distinct content or active editing. Start with 10–12 px control radii and 12–16 px content surfaces. Avoid rounded box inside rounded box inside rounded box. Use a distinct primary button, a quiet secondary button and text actions rather than giving every action a pill.

5. **Make status useful and specific** — steps 1, 6, 8–10.
   Replace “Connected · 80 database tables” with actual data freshness, separately from backend availability. Keep database details in diagnostics. “No food logged” should be distinguishable from a complete zero-intake record. Explain missing sleep score alongside the HRV that is available. Profile reports no goals while Training shows an active FTP plan: clarify the relationship between profile goals and plan objectives rather than assuming a data error.

## Settings treatment across the app

| Area | Recommended presentation |
|---|---|
| Weekly availability | Seven compact day rows: “Mon · Cycling · 60–90 min · Edit”. Expand one day at a time; keep multiple activities and priority controls inside its editor. |
| Workout time changes | Short scope selector, duration control and affected-workout summary in one focused editor. Keep Review time change before applying anything. |
| Training preferences | Summary groups for sports, availability, equipment and restrictions. Open the chosen group; keep restrictions and review requirements clear. |
| Charts | Header with title, period and Expand. Move duplicate, export, resize and remove into an accessible menu. Show advanced pan controls when exploring; retain keyboard equivalents. |
| Nutrition targets | Compact calories/macros summary with Edit targets. Keep estimation inputs and assumptions in a dedicated editor. This is proposed from the discovered controls; the target editor was not expanded visually. |
| Meal entry | A clear “Add food” entry with search, manual and photo paths. Use one shared assistant; date, daily totals and saved meals should remain easy to find. |
| Profile | Readable value rows for personal details, units and reference inputs; edit related fields together. Distinguish profile weight from dated weight-history entries. |
| AI connection | Provider, model and connection status in concise rows. Account management and detailed data-sharing explanation stay available on demand. |
| Telegram | Connected-service row with status and last check; expand capabilities and data-sharing details. Keep unlink separate from ordinary edits. |
| Garmin sync | Last successful sync and current progress first; automatic-sync preferences in a small group. Move sign-out and diagnostics away from routine sync actions. |
| Maintenance | History and Add maintenance action first. Initial editor asks for equipment, work and date; reveal optional cost, provider, usage and notes in a secondary section. |

## Captured walkthrough

### 1. Dashboard — needs stronger priorities
Strength: nutrition has explicit units and targets. Risk: large empty nutrition visualization and idle chat dominate the first screen; summary widgets follow plots. Put a compact daily overview first.
![01 Dashboard](01-dashboard.jpg)

### 2. Activities — sound foundation
Strength: clear dates, names, durations and range presets. Risk: identical large rows reduce scanning density; strength sessions show 0.0 km. Use sport-specific summary columns, lighter row dividers and visible sport filtering/search as history grows.
![02 Activities](02-activities.jpg)

### 3. Activity detail — useful and readable
Strength: expansion reveals clear metric labels and a recorded route. Risk: the generic metric grid gives different sports the same emphasis. Prioritize relevant metrics by sport and make analysis actions easy to find. Map loading, keyboard use and colour interpretation need separate testing.
![03 Activity detail](03-activity-detail.jpg)

### 4. Training — hierarchy needs work
Strength: dates, session types and duration are explicit. Risk: publication copy consumes space before the schedule; only three large day cards fit across the available content width. Lead with today's session and a compact week view; keep publication status/action nearby with details available.
![04 Training](04-training.jpg)

### 5. Nutrition — competing entry paths
Strength: meal description and photo entry are available. Risk: two visible composers and an extra Open chat action make the entry model unclear. Bring date, intake summary and Add food forward; use the shared assistant consistently.
![05 Nutrition](05-nutrition.jpg)

### 6. Health — honest but unhelpful first impression
Strength: missing sleep data is not fabricated; HRV remains available. Risk: several missing-score messages and many chart controls precede the useful graph. Show “Sleep score unavailable · overnight HRV available” once with freshness and a clear next action when appropriate.
![06 Health](06-health.jpg)

### 7. Maintenance — too much form at entry
Strength: inputs have explicit labels. Risk: optional and essential fields share equal prominence; the empty history follows the form. Start with equipment/history and a focused Add maintenance editor.
![07 Maintenance](07-maintenance.jpg)

### 8. Profile — understandable, visually generic
Strength: local storage is explained and saves are explicit. Risk: a large always-open form, repeated weight entry and unclear goal/plan relationship. Use grouped current-value rows and focused editing.
![08 Profile](08-profile.jpg)

### 9. Data & sync — informative, too technical
Strength: connection, last success and automatic schedule are visible. Risk: overlap/check counts compete with freshness; sign-out occupies a large area alongside routine controls. Use a concise sync summary and secondary advanced settings.
![09 Data and sync](09-data-sync.jpg)

### 10. Settings — excessive explanatory blocks
Strength: Telegram limitations and cloud data handling are explained. Risk: a large integration card fills the first screen; assistant settings follow below. Use Connected services and Assistant sections with summary rows and expandable details. Retain the privacy information.
![10 Settings](10-settings.jpg)

### 11. Workout time settings — functional, sprawling
Strength: scope and review action are explicit. Risk: four controls and long explanation spread vertically across a large tinted panel. Use aligned labels, clear scope and a concise preview in a focused editor. This is a scrolled viewport showing the expanded controls.
![11 Workout time settings](11-workout-settings.jpg)

### 12. Training preferences entry — weak section separation
Strength: preferences can be disclosed on demand. Risk: the disclosure follows a large coaching block, and nested rounded sports controls repeat the surrounding container style. Give preferences a compact summary and clear Edit action.
![12 Training preferences](12-training-preferences.jpg)

### 13. Weekly availability — highest settings redesign priority
Strength: per-day activity and time budgets are configurable; keyboard focus is visible in this sample. Risk: nested day fieldsets, optional limits, repeated controls and disabled reorder buttons make two days fill most of a screen. Replace the default form with seven day-summary rows and edit one day at a time. Keep accessible reorder alternatives.
![13 Weekly settings](13-weekly-settings.jpg)

## Accessibility risks and limits
Small muted text, subtle control borders, small information buttons and dense chart toolbars warrant contrast and target-size measurement. The captured keyboard step showed a visible focus outline; that does not establish complete keyboard accessibility. Chart colour scales need text or other redundant cues. New menus and editors need accessible names, logical focus order, Escape behavior and focus restoration.

Mobile reflow, zoom, screen-reader behavior, contrast ratios, validation, error recovery, full keyboard journeys, chart data navigation and save/publish outcomes were not tested. No WCAG compliance claim is made.

## Suggested sequence
First select the visual direction using the actual dashboard and weekly settings as references. Then establish shared settings rows, field groups, menus, buttons and editor patterns. Apply them to weekly availability, profile and connections first; follow with nutrition, charts and dashboard hierarchy. Validate both desktop and mobile before applying across the whole app.
