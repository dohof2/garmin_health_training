# Recorded activity overlays — 2026-10-11

Resolved the assistant's refusal to overlay two activities' recorded power on one chart. This was a missing chart capability, not missing FIT power data.

Implemented:
- `create_plots` supports `stream:power`, `stream:heart_rate`, `stream:cadence`, and `stream:speed`, with activity IDs and an elapsed-time X axis.
- One to eight independent recordings share axes and receive distinct colours, labels and alternating solid/dashed lines. Each recording aligns to its own activity start; pauses remain part of elapsed time. GPS matching is not used.
- Explicit IDs are preserved in plot context and pinned dashboard charts. Date selection uses the requested timezone. More than eight matches asks for narrower dates/IDs rather than silently selecting a subset.
- Synthetic, removed and unknown activities cannot enter an overlay. Missing/nonfinite/negative values and gaps over three seconds break lines. Recorded zeros are retained.
- All selected samples contribute to counts and per-trace statistics. Display reduction keeps bucket extrema and endpoints with original segment IDs, bounded to 2,000 points per trace; very fragmented traces may omit short segments, explicitly noted. CSV includes displayed points, activity identity, elapsed seconds and timestamps.
- Model receives trace summaries/colours and evidence metadata rather than thousands of raw display points. Frontend receives the full calculated plot. Assistant instructions distinguish continuous traces from ride averages and sprint history.

Verification:
- 348 backend tests and frontend typecheck pass; frontend production build passes.
- 12 dedicated tests cover separate start alignment, zeros, gaps, timezone day selection, virtual rides, excluded sources, invalid scopes, eight-activity bound, extrema reduction, fragmented-display bounds, missing streams, metric conversions, pin persistence and compact model evidence.
- Connected ChatGPT tested against two invented activities: exact user request produced one power overlay with two traces; follow-up replaced power with heart rate for the same IDs. Both passed without errors. Repeatable runner: `scripts/run_activity_overlay_qc.py` (requires network and existing account authorization; fixture data only).
- Actual user request rerun in app: one chart, two labelled colour traces, elapsed-time labels, 5,501 recorded power observations. Chart visually verified. Personal-data screenshot retained only locally at `/private/tmp/activity-power-overlay.jpg`, outside the repository.

Limits:
- Elapsed alignment is not an automatic clock-offset/power-meter calibration or proof the recordings describe the same session.
- CSV is the displayed-point export, not an export of every raw sample; display reduction is disclosed.
- Arbitrary FIT field discovery remains available separately; these overlays currently support the four normalized continuous sample fields above.
