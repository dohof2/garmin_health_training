# T12 readiness algorithm: evidence and proposed v1

Research date: 10 October 2026. Status: implemented as `readiness-v1`, a provisional advisory prototype; predictive usefulness is not prospectively validated. See `../status/t12-verification.md`. The intended outcome is morning readiness for a demanding endurance session. It does not measure general health, muscular recovery in every sport, or the probability of performing well.

## Recommendation and evidence

Use personal physiological deviations, sleep adequacy, and recent training exposure as three groups. Resolve the date and data quality first; explain each deduction from the score. Keep subjective fatigue/soreness as visible context when available. Do not combine six correlated measurements as though they were independent votes.

The strongest directly relevant experimental basis is **HRV-guided endurance training**. [Vesterinen et al., 2016](https://pubmed.ncbi.nlm.nih.gov/26909534/) studied 40 recreational runners and individualized vigorous-session timing against personal HRV ranges. The HRV group performed fewer moderate/high-intensity sessions; results suggested potential benefits, rather than a guarantee of superior adaptation. This supports individualized context and intensity timing, not a published six-input readiness equation.

[Manresa-Rocamora et al., 2021](https://pubmed.ncbi.nlm.nih.gov/34639599/) found improvement in vagal-related HRV with HRV-guided training, but small, statistically non-significant group differences for aerobic fitness and endurance performance. Baseline and measurement methods remain unsettled. A newer [Morinaga and Takai study, 2025](https://www.jhse.es/index.php/jhse/article/download/hrv-guided-training-moderate-intensity-enhances-aerobic/92/3961) also supports the approach, but its small sample and stated limitations prevent treating it as definitive calibration.

[Buchheit, 2014](https://pubmed.ncbi.nlm.nih.gov/24578692/) emphasizes measurement error, meaningful individual changes and training context. [Le Meur et al., 2013](https://pubmed.ncbi.nlm.nih.gov/24136138/) documents parasympathetic hyperactivity in functionally overreached athletes. Accordingly, unusually high HRV should not automatically earn bonus points or imply full recovery.

[Walsh et al., 2021](https://bjsm.bmj.com/content/55/7/356) supports attention to sleep and individual needs while describing limitations in measurement and performance evidence. Duration and the vendor sleep score belong to one group. [Garmin's sleep-score explanation](https://www.garmin.com/en-US/blog/fitness/how-garmin-watches-track-your-sleep-calculate-sleep-score/) says the score already includes duration, quality and HRV-related sleep stress: these inputs overlap.

[Garmin's readiness manual](https://www8.garmin.com/manuals/webhelp/GUID-0221611A-992D-495E-8DED-1DD448F7A066/EN-US/GUID-C21BE0C8-A08E-4DA1-B6C6-2E0E2DDDB372.html) identifies sleep, recovery time, HRV, acute load and recent sleep/stress history. That is useful product context, but it does not provide a reproducible formula. [Garmin's load definition](https://support.garmin.com/en-SG/?faq=SEkNpdGyhR917js0qQL3Q6) describes an EPOC-based estimate; retain it as a vendor estimate, not directly measured fatigue.

Do not use an acute:chronic workload ratio threshold as an injury-risk predictor or a hard training gate. [Impellizzeri et al., 2020](https://pubmed.ncbi.nlm.nih.gov/32502973/) identifies fundamental problems with that interpretation. Workload remains useful descriptive context without claiming causality.

[Saw et al., 2016](https://pubmed.ncbi.nlm.nih.gov/26423706/?dopt=Abstract) found self-reported well-being responsive to training stress. Optional fatigue/soreness and perceived recovery should be displayed beside wearable evidence; feeling poor must not be overridden by a high number. Such a check-in is a later input option, not a prerequisite for opening the app.

**Evidence boundary:** these sources justify the choice of signals and interpretation. They do not validate the weights, thresholds, decay constant or 0–100 mapping below. Those are explicit engineering hypotheses for a versioned prototype, to be tested and adjusted.

## Data audit before the sync repair

Read-only inspection; no personal observations were sent to external services.

| Input | Stored coverage as inspected |
|---|---|
| Overnight HRV average | 12 distinct nights, 28 September–9 October 2026 |
| Sleep HRV average | Same 12 dates; an overlapping source, not 12 additional independent nights |
| Vendor seven-day HRV average | Same 12 dates; do not count overlapping rolling averages as new nightly observations |
| Resting heart rate | 2,977 dates, 20 July 2018–9 October 2026 |
| Sleep duration | 2,913 dates, 6 August 2018–9 October 2026 |
| Sleep score | 1,811 dates, 29 August 2021–9 October 2026 |
| Activity exercise load | `activityTrainingLoad` present in 718 activity payloads; all four October activities lack that field |
| Daily acute/chronic vendor load | 4,452 archive records through 30 September 2026; multiple records per date require deterministic selection |
| Recovery-time estimate | Eight activity payloads have `firstbeatData.results.recoveryTimeMins`; insufficient for assuming universal coverage |

The newest date available is 9 October: do not call this a complete current-morning observation on 10 October. Resolve sleep by the wake date/period end in the configured timezone. A completed daily resting-HR summary can include observations made after that morning; mark it as retrospective context rather than leaking it into an as-of-morning historical estimate.

The initial 12 normalized HRV nights were insufficient for the proposed personal baseline. The 10 October sync repair subsequently recovered 1,434 nightly HRV averages (25 August 2022–10 October 2026), 1,461 vendor weekly averages, and explicit exercise load for 725 activities, including all four October workouts. All five live streams are verified through 10 October. These were ingestion gaps, not unavailable Garmin history; see `../status/sync-recovery-verification.md`. Historical load remains incomplete for older activities where no explicit source value exists. Morning/as-of timing still requires implementation work. Unknown numeric FIT-backup fields must not be guessed into HRV values. Inspect supported FIT definitions before normalizing anything. Prefer retrieving current per-activity exercise load through Garmin detail data; preserve missing load if unavailable. Duration, calories, training effect and exercise load are not interchangeable units.

## Implemented prototype: `readiness-v1`

Score a fixed morning observation after a completed overnight sleep. Persist calculation time, input IDs/dates, source method, timezone, parameter version and any later corrected estimate. Include only sessions finished before the calculation cutoff. Never silently substitute the latest historical day for today.

### 1. Establish personal references

- For nightly HRV, use one consistent overnight-average series in milliseconds. Do not mix the five-minute maximum, weekly average and overnight average. Treat the vendor metric as an overnight HRV estimate; do not assert it is identical to an ECG RMSSD measurement without confirming its definition.
- Compare log HRV with a prior personal baseline. Initial draft: the 28 calendar days ending before the recent three-night window, requiring at least 21 valid nights. Use median and `1.4826 × MAD` for a robust center/scale. Give the scale a configurable floor of 0.05 log units to avoid dividing by nearly zero variability. These choices are provisional.
- Evaluate last night and the mean of log values from the latest three calendar nights. Require at least two observations including the current night for the short trend. Use the more adverse normalized low deviation; a single unusual night is still visible as such. Freeze parameters/reference selection for historical calculations; never use later data to calibrate earlier mornings.
- Resting HR uses its own consistently defined series, baseline and robust scale, with a provisional 2 bpm scale floor. It corroborates HRV rather than duplicating its full weight. Never mix overnight and whole-day RHR in the same baseline without an explicit source change.
- Sleep target starts at an editable adult default of 8 hours, clearly labeled as a default, not a measured personal requirement. Do not learn a low sleep requirement simply because someone habitually sleeps too little. Age-sensitive defaults and user confirmation can be added through T7.

### 2. Calculate three bounded penalties

Let `clip(x) = min(1, max(0, x))`.

**Autonomic group, at most 40 points.** Let `zH` be the signed log-HRV deviation in baseline scale units (negative means below baseline), taking the more negative of last night and the short trend. Let `zR` be the signed RHR deviation (positive means above baseline). Define:

```text
pH = clip((-zH - 0.5) / 2)
pR = clip(( zR - 0.5) / 2)
pA = max(pH, pR)
autonomic_penalty = 40 × pA
```

Using the maximum prevents adding two largely related autonomic signals twice. Show whether one or both are abnormal. Unusually high HRV gets a context flag, no bonus and no automatic fatigue diagnosis. Persistent low HRV or simultaneous HRV/RHR shifts deserve more attention than isolated noise.

**Sleep group, at most 35 points.** Calculate last-night and three-night mean shortfall from the selected sleep target. Use the larger shortfall. A provisional duration penalty reaches its maximum at a three-hour shortfall; a vendor-score penalty reaches its maximum at score 30 and is zero at 80 or above:

```text
pD = clip(max(last_night_shortfall, three_night_mean_shortfall) / 3 hours)
pQ = clip((80 - sleep_score) / 50)
sleep_penalty = 35 × max(pD, pQ)
```

The maximum protects against counting the same poor night twice. It cannot entirely remove overlap between sleep-score physiology and the autonomic group; sensitivity testing must assess this before finalizing weights. Missing quality data makes that portion uncertain, not perfect.

**Recent-workload group, at most 25 points.** Combine intensity and elapsed time in one fatigue-exposure estimate, avoiding a second independent deduction merely because a session was recent:

```text
F = sum(session_exercise_load × 2^(-hours_since_session_end / 36))
```

Use a seven-day lookback and the same method for reference mornings. The 36-hour half-life is a prototype parameter, not a physiological recovery countdown. Compare F with the personal distribution of at least 28 fully covered reference mornings in the previous 56 days. Let q be its empirical percentile, using midranks for ties:

```text
workload_penalty = 25 × clip((q - 0.70) / 0.30)
```

This reduces the score for unusually heavy recent exposure, without declaring normal training harmful or low training load inherently beneficial to fitness. Use one load method consistently. Do not combine EPOC, TRIMP and power-based load in one reference distribution; any fallback needs its own method/version and lower-confidence labeling. Do not add vendor acute load or recovery time again: show them as context. Missing sessions/load or unverified sync coverage make this group incomplete.

### 3. Present score and data quality separately

For complete inputs:

```text
readiness = round(100 - autonomic_penalty - sleep_penalty - workload_penalty)
```

Draft bands: below 50 lower readiness; 50–79 mixed readiness; 80–100 higher readiness. These are interface thresholds to test, not established biological boundaries. A high result means few measured adverse signals; it does not prove muscular recovery or recommend increasing a workout automatically.

Missing values must not earn zero penalties. Keep the fixed group budgets. Return a partial-evidence range based on known deductions and remaining unknown penalty budgets, or “insufficient data” when fresh sleep and meaningful baseline evidence are absent. Do not silently renormalize available inputs to 100. If HRV is absent but RHR is available, the known RHR penalty establishes a minimum autonomic deduction while the unobserved HRV leaves the remainder uncertain.

“Confidence” means data completeness, freshness, baseline maturity and measurement consistency—not a probability that the score is correct. Separate missing-current-night, insufficient-baseline, incomplete-workload and retrospective-RHR flags. Optional self-reported fatigue/soreness remains a visible caution even with a high wearable score.

## Sanity checks and validation before release

With complete evidence and fixed references, the proposed mapping should behave as follows:

| Controlled scenario | Expected behavior |
|---|---|
| Normal HRV/RHR, adequate sleep, usual recent exposure | High score; no automatic harder-session prescription |
| One normal high HRV reading | No bonus above the baseline result |
| One unusually high HRV reading | Context flag; no assumption of exceptional recovery |
| HRV 2.5 scale units below baseline, other inputs normal | 40-point autonomic deduction; one signal does not alone produce the lowest band |
| HRV and RHR both strongly adverse | Same bounded autonomic group, with corroboration explained |
| Five hours sleep against eight-hour target | Full sleep deduction; poor vendor score does not add another 35 points |
| Unusually hard session shortly before morning | Workload deduction; it declines as time passes without additional sessions |
| Strong autonomic deviation + five hours sleep + extreme recent exposure | Can reach the lowest band; explanation identifies all three groups |
| Missing HRV baseline or workload | Partial range/insufficient data, never a fabricated high-confidence current score |
| More rest with persistent poor sleep/physiological shifts | Workload improves; remaining negative evidence persists |

Run sensitivity checks with alternative group budgets, HRV thresholds, sleep targets and 24/36/48-hour load half-lives. If small reasonable parameter changes switch a day's band, display uncertainty and reconsider the mapping. Backtest using past-only references and input timing, not today's entire history. Check continuity, monotonicity, DST/wake-date handling, duplicate sources, delayed corrections and stale data.

Historical data can establish coverage and plausible behavior, but it cannot prove predictive usefulness without outcomes. During normal use, collect optional pre-session perceived recovery and post-session session-RPE/ability to complete the planned session. Evaluate prospectively against a simple sleep-only and HRV-only baseline over several weeks; keep easy/hard sessions and sports separate. Do not optimize against Garmin readiness as ground truth or interpret a missed session as poor readiness. Final weights and a validation claim must wait for this evidence.

An isolated arithmetic check passed eight controlled scenarios and 140 monotonic comparisons for the draft equations. This establishes the intended arithmetic and bounded deductions only; it is not a production implementation, full T12 testing or evidence of predictive validity.

## Implementation order

1. Repair/normalize HRV and workload coverage; establish source timing and morning versus retrospective RHR handling.
2. Implement the pure versioned calculation and scenario/sensitivity tests, including partial ranges.
3. Add the dashboard card/trend with exact deductions, source dates, assumptions and data-quality flags.
4. Expose the same result to the assistant and later planner; retain explicit review for plan changes.
5. Evaluate prospective usefulness and refine the formula transparently.

## Implementation decisions

The morning cutoff is the later of the configured local hour (default 08:00) and recorded wake time. Whole-day RHR from the previous completed day provides explicitly lagged context; current-day RHR is excluded. Workload requires verification through the morning date, to account for early sessions. Recorded ends/FIT session timestamps/Garmin elapsed duration resolve session completion; active duration alone is insufficient. Historical queries reconstruct from current corrected records using past-only references. Configuration versions and calculation revisions remain stored. The dashboard and assistant expose deductions, missing-data ranges and sensitivity without changing workouts. These implementation checks do not validate predictive accuracy.
