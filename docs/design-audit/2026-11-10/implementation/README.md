# Implemented training journal

The existing React app now uses the chosen serif journal layout and pale-blue/navy/coral palette. Today's actual training readiness replaces the goal slot. Saved workouts, meal totals, HRV and sleep remain connected to the existing local APIs.

The app's sidebar and mobile navigation preserve all nine sections. Chat is an on-demand native dialog that retains the conversation and draft. Profile, assistant, Telegram, sync and training preferences use summary rows with mounted editors. Weekly availability uses a focused day editor in Training preferences. Following the user’s next request, Dashboard now shows recorded totals for the last seven calendar days instead of availability. Training stages each applied day until Save training answers and preserves the existing backend validation.

Maintenance shows its three essential fields first, with optional details, filters and CSV import disclosed separately. Nutrition puts date and intake before the optional coach/photo flow. Chart exploration and configuration controls are disclosed on demand. Garmin publication remains available after the training calendar with the existing explanation and behavior.

The shared visual system lives in `frontend/src/journal.css`; focused new components are `JournalDashboard`, `SettingsGroup`, `JournalIcons`, `AvailabilityList` and the `journalAvailability` request builder. The production build has been regenerated.

See [the visual QA report](../../../../design-qa.md) for comparison history, tests and limits. All numbered JPEGs in this directory are actual browser captures; `comparison-*.png` are local comparison sheets, not app assets. Earlier captures document issues fixed during the pass.

## Raster asset

- Built-in Image Gen was used; no CLI/API fallback.
- Source: the selected blended concept, saved as `../selected-direction.png`.
- Consuming asset: `frontend/public/assets/journal-contours.png`, used in the page background and sidebar.
- Final prompt: “Generate only a decorative background asset from the top-right topographic contour motif of the supplied training journal UI. No UI, no typography, no icons. 1024 x 1024 PNG. Very fine pale powder-blue contour lines #d5e4ed on uniform near-white #fbfcfd background, flowing organically from upper right toward lower left, sparse sophisticated cartographic contour map. Match source motif subtlety precisely. Flat raster asset, no shadow or gradients. Will be used at 440 x 330 CSS pixels in top-right corner and small in sidebar. Lines very subtle, lots of near-white negative space.”
- The generated bitmap was inspected and copied into the project. Phosphor supplies the new UI icons; existing data visualizations were retained.

## Verification commands

```sh
npm --prefix frontend run build
npm --prefix frontend run test:journal
npm --prefix frontend run test:chat-render
npm --prefix frontend run test:activity-visuals
PYTHONPATH=backend .venv/bin/python -m unittest backend.tests.test_training.TrainingTests.test_invalid_answers_atomic_and_stale_revision_rejected
git diff --check
```

These checks passed. An additional older backend draft-generation test remains a documented failure; see the QA report. Browser testing did not save experimental settings, send chat messages or publish workouts.
