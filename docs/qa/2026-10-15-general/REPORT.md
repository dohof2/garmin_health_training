# Current general QC fixes — 15 October 2026

This report supersedes the pending user follow-ups in [the original audit](../2026-10-11/REPORT.md). That audit's numbered findings and FAIL verdict are historical; their repairs are documented in [FIXES.md](../2026-10-11/FIXES.md). Training changes have [separate evidence](../2026-10-15-training/REPORT.md).

| Item | Current implementation and evidence |
| --- | --- |
| Readiness slow | Profile on disposable populated DB: 14-day request 12.884 s, with 11.575 s spent repeatedly decoding activity JSON. Prepare shared sessions/series once per request, reuse across days/sensitivity; avoid payload decoding when recorded end exists. After: 14-day first request 0.1558 s, repeat 0.0897 s; one day 0.0664 s. No shared stale cache. Exact calculation parity and one-prepare regression checks added. These timings are local measurements, not a guarantee for every machine. [Detailed performance evidence](../2026-10-15/readiness-performance.txt). |
| Readiness intermittent/loading | Today renders independently of forecast; background refresh preserves its current dial. Changing selected date clears mismatched data. Request abort/error handling retained. Browser reliability remains manually unverified. |
| Explore through today | Default 30-day range ends on browser-local today and input maximum includes today rather than latest stored activity date. |
| Renamed synced activity | Existing stable Garmin identifier upsert confirmed; rename/retry/detail-preservation regression ensures same activity identity/count and updated name. No real authenticated sync was run. |
| VO₂ trend | Card toggle opens inclusive four-week/28-day trend, editable From/To and reset; handles empty data. Production build passed, interactive browser check pending. |
| Educational questions | Direct educational path answers common metric definitions including power/TSS without personal-record/model tools. Personal-data requests retain evidence routing. Tone instructions reduce repetitive source attribution. |

## Pending user follow-up — 16 October 2026

### Trainer long-term plan blocked after repeated answers and Save — observed 16 October

Evidence: read the existing Training tab conversation and visible proposal/status cards through browser accessibility state without refreshing, submitting or changing the user's plan. These are observed UI/conversation failures; underlying persistence/routing causes have not yet been diagnosed.

- **Answers not carried into a complete proposal.** The user requested 16 weeks of FTP/endurance with occasional sprints, cycling Sunday/Monday/Wednesday/Friday, strength Tuesday/Thursday, Saturday mostly off, Friday long rides, 60–90 minutes on weekdays and up to five hours Friday; provided power/HR sensor access, no pain, bodyweight/dip/pull-up equipment, beginner strength and indoor/outdoor power access. Despite this, the final UI still marks sports, priority, availability, experience, weekly minutes and restrictions missing. Distinguish genuinely unspecified details (such as exact start times or explicit weekly budget) from answers already provided; preserve partial answers and ask only a focused unresolved question. Infer cycling experience/workload from history as requested, without silently treating inferred manageable volume as user confirmation.
- **Saved setup confused with saved plan.** Multiple “Review training preferences and direction” cards show disabled “Saved” buttons and “Saved. The trainer will use these preferences and calibration.” Yet later assistant responses claim earlier save proposals were incorrect or that answers “did not save ... anything.” Make save acknowledgments and subsequent tool context consistent with actual saved state. Show exactly what was saved: preferences/calibration/direction versus a workout schedule or active program.
- **Long-term plan never generated.** After repeated setup saves and requests to activate, the page still shows “No training plans yet,” no active plan and no complete scheduled-session preview. The trainer repeats prerequisites rather than completing the pending 16-week proposal. Add an end-to-end regression reproducing the conversation and save actions through to a block roadmap, reviewable first seven days and visible final activation action.
- **Activation path not discoverable/reachable.** The user repeatedly asks “is it now active?”, “make it active” and “I approve it.” The assistant repeatedly refers to “Approve and activate plan,” but no ready proposal with that action is visible. Keep explicit activation approval, but provide a direct next action/status showing remaining blockers and a link to the actual preview; after activation show plan identity, date range and active status. Never imply conversational approval created a plan.
- **Question loop and loss of conversation evidence.** The trainer re-asks days/durations and strength experience after the user supplied them, and eventually says schedule information appeared only in its own replies although the user's opening message explicitly contains the days. Test extraction from original user messages, multi-turn retention, saved-state refresh after Save, and conflict handling without dropping earlier answers. The specific indoor/outdoor question after an ambiguous “yes” was a legitimate clarification, unlike the repeated full questionnaire.
- **FTP provenance may be overwritten by authorization.** The chat identifies Garmin FTP 225 W measured June 11, asks permission to use that provisional reference, then a saved card displays `ftp confirmed on: 2026-10-16` and source `user confirmed`. Investigate whether approval to use an old measurement has been treated as fresh calibration. Keep original measurement date/source separate from authorization date; do not silently certify a new FTP test or bypass stale-calibration policy.

Status: implemented in the authorized 16 October repair. See [current trainer repair evidence](../2026-10-16-trainer/REPORT.md). The observations above preserve the original failure; browser activation verification is tracked in that report. No production plan or preferences changed during validation.

- **Trainer FTP — request authorization, not repeated entry.** The user reports being asked for FTP again despite an available stored value. Look up the available cycling FTP first, display its value, source and recorded date, and ask only for authorization to use it (for example, “I have your FTP as 225 W, recorded June 11. Use this for your plan?”). If stale, explain that fact in the same confirmation rather than demanding re-entry; authorization must not falsely change the measurement date or bypass calibration policy silently. Request a value only if none is available or the user wants to change it. Verify available, stale, missing and manual-override cases. User-reported; pending investigation and implementation.

- **Trainer experience questions — inspect activity history first.** Before asking about past sport/activity experience, the trainer should review the user's recorded activities and infer supported experience from sport-specific history, consistency, duration and volume. Do not ask the user to repeat information already evidenced by records. Ask a focused question only when activities are absent or the relevant history is insufficient; explain the gap. Do not equate an absence of recorded activities with being a beginner, or infer unrecorded skills, injuries or equipment. Verify sufficient-history, no-history and insufficient-history cases. Recorded for later assessment; no implementation change or verification performed for this item.

## Verification checkpoint

- Full backend unittest suite: 436 tests passed after these changes.
- Frontend TypeScript and Vite production build: passed.
- Independent original acceptance probes: 8 passed on disposable databases.
- VO₂ reference/gauge executable audit: 96 boundary cases plus historical-age/pointer checks passed.
- User production training plan was not modified. Performance measurements used a database copy; sync tests use temporary fixtures.

## Remaining verification and scope

Browser automation inventory returned no browsers, and native Chrome computer-use access was not approved. Therefore no live UI timing, mobile, keyboard, VO₂ range interaction or training end-to-end claim is made. The readiness backend latency improvement is measured; the independent today/forecast rendering behavior is source/build-verified.

Backend restarted successfully after final verification; `/api/health` returned `status: ok` and `database: ready`. Frontend uses development HMR.

Historical full-account sync, OpenAI/vision/provider checks, browser CSV delivery, production-size backup/restore and formal accessibility coverage remain explicit external/manual verification gaps. Earlier completed repairs must not be described as unresolved solely because the original audit retains its historical findings.

Training candidate editor currently supports all-session title/time and cycling duration; strength exercise/noncycling duration edits remain a scoped limitation. Approved snapshots remain protected against later FTP sync changes.

## Sleep-card follow-up

- Default explicitly requests browser-local waking date and says “Last night's score”; historical navigation uses the selected date. Missing last-night data is never substituted with older data.
- Larger colored score and recorded qualitative rating sit directly beneath the heading. Missing qualifiers say “Rating not recorded”; no unsupported score thresholds were invented.
- Nightly HRV aggregate is prominent above its plot. Supported stored aggregate fields are used without averaging sparse samples into a new measurement or fabricating a trace.
- Missing score, HRV aggregate and HRV trace each have explicit messages within the plot area.
- Backend sleep API changed to support timezone-aware default date and aggregate/missing metadata; backend restart is required but was not attempted for this follow-up.
- Focused sleep tests: 7 passed, including three new date/aggregate/missing cases. Frontend production build passed. Browser visual verification remains unavailable.
