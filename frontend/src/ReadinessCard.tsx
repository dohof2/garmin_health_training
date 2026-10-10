import { useEffect, useState } from "react";
import StatusDial, { readinessBands } from "./StatusDial";

type Reading = { value: number; unit: string; wake_date: string; source_name: string } | null;
type Group = {
  name: string; budget: number; penalty_min: number; penalty_max: number; complete: boolean;
  baseline_start?: string; baseline_end?: string;
  hrv_baseline?: { count: number; center: number; scale: number } | null;
  rhr_baseline?: { count: number; center: number; scale: number } | null;
  hrv_z?: number | null; rhr_z?: number | null; target_hours?: number;
  exposure?: number; reference_mornings?: number; percentile?: number | null;
  sessions?: Array<{ id: string; ended_at: string; load: number | null; hours_since_end: number }>;
  missing_activity_ids?: string[];
};
type Result = {
  date: string; cutoff: string; status: string; score: number | null; band: string | null;
  score_range: { low: number; high: number } | null; data_quality: string; warnings: string[];
  inputs: { hrv: Reading; rhr_previous_day: Reading; sleep: Reading; sleep_score: Reading };
  groups: Group[]; config_version: string; formula_version: string; caution: string;
  sensitivity?: { low: number; high: number; band_changes: boolean };
  calculation_id: number; calculated_at: string;
};
type Response = {
  latest: Result; trend: Result[]; settings: { parameters: Record<string, number> }; reconstruction: string;
};
const flags: Record<string, string> = {
  rhr_previous_day_context: "Resting heart rate uses the previous completed day, not later observations from this morning.",
  historical_estimate_uses_current_corrected_records: "Historical estimates use corrected records available now, with references drawn only from earlier dates.",
  unusually_high_hrv_no_bonus: "HRV is unusually high. This earns no bonus and does not establish full recovery.",
  hrv_missing_or_insufficient_baseline: "Nightly HRV or enough personal baseline history is missing.",
  rhr_missing_or_insufficient_baseline: "Previous-day resting heart rate or enough baseline history is missing.",
  completed_sleep_missing: "Completed sleep with a recorded wake time is missing for this date.",
  sleep_score_missing: "Sleep quality score is missing.",
  sleep_trend_insufficient: "At least two of the latest three sleep nights are needed for the short trend.",
  workload_coverage_or_reference_incomplete: "Recent workout coverage, explicit loads, end times, or enough fully covered reference mornings are missing.",
  morning_observation_not_finished: "The morning cutoff has not passed yet. Check again after sleep and the selected morning time.",
  band_sensitive_to_provisional_parameters: "Reasonable changes to the prototype parameters change this day's band. Treat the band cautiously.",
};
const titles: Record<string, string> = { autonomic: "HRV and resting heart rate", sleep: "Sleep", workload: "Recent workload" };
const labels: Record<string, string> = {
  sleep_target_hours: "Sleep target (hours)", load_half_life_hours: "Load half-life (hours)",
  autonomic_weight: "HRV / heart-rate budget", sleep_weight: "Sleep budget", workload_weight: "Workload budget",
  baseline_days: "Baseline window (days)", baseline_min_nights: "Minimum baseline nights",
  load_reference_days: "Load reference window (days)", load_min_mornings: "Minimum reference mornings",
  hrv_scale_floor: "Minimum log-HRV scale", rhr_scale_floor: "Minimum RHR scale (bpm)",
  deviation_tolerance: "Deviation tolerance", morning_hour: "Morning cutoff hour (local)",
};
function value(result: Result) {
  if (result.score !== null) return `${result.score} / 100`;
  if (result.score_range) return `${result.score_range.low}–${result.score_range.high} / 100`;
  return result.status === "awaiting_morning" ? "Awaiting morning" : "Insufficient data";
}

export function ReadinessCard({ timezone, refreshToken }: { timezone: string; refreshToken: string }) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const [historicalDate, setHistoricalDate] = useState<string | null>(null);
  const selectedDate = historicalDate ?? today;
  const setSelectedDate = (value: string) => setHistoricalDate(value === today ? null : value);
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null); setData(null);
    fetch(`/api/readiness?end_date=${selectedDate}&days=14&timezone=${encodeURIComponent(timezone)}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("Readiness could not be loaded.");
        return response.json() as Promise<Response>;
      })
      .then(result => { setData(result); setDraft(result.settings.parameters); })
      .catch(error => { if (error.name !== "AbortError") setError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [selectedDate, timezone, refreshToken, revision]);
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError(null);
    try {
      const response = await fetch("/api/readiness/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parameters: draft }) });
      if (!response.ok) { const body = await response.json(); throw new Error(body.detail || "Parameters could not be saved."); }
      setRevision(current => current + 1);
    } catch (error) { setError(error instanceof Error ? error.message : "Parameters could not be saved."); }
    finally { setSaving(false); }
  };
  const result = data?.latest;
  return <>
    <p>Training readiness <span className="readiness-prototype">Prototype</span></p>
    {result && !loading ? <StatusDial
      value={result.score !== null ? String(result.score) : result.score_range ? `${result.score_range.low}–${result.score_range.high}` : '—'}
      unit="/ 100" bands={readinessBands}
      position={result.score !== null ? result.score / 100 : null}
      range={result.score === null && result.score_range ? { low: result.score_range.low / 100, high: result.score_range.high / 100 } : null}
      interpretation={result.score !== null ? result.score < 50 ? 'Recovery focus · prioritize rest or an easy session.' : result.score < 80 ? 'Ready with care · keep the session manageable.' : 'Well prepared · measured recovery signals are favorable.' : result.score_range ? 'Readiness uncertain · arrows mark the possible range; some inputs are missing.' : result.status === 'awaiting_morning' ? 'Awaiting morning measurements' : 'Not enough data to assess readiness'}
    /> : <h3>{loading ? 'Loading…' : '—'}</h3>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {result && <>
      <span>{result.data_quality} data quality</span>
      <small>{result.date} · {timezone} · after {new Date(result.cutoff).toLocaleTimeString([], { timeZone: timezone, hour: "2-digit", minute: "2-digit" })}</small>
      <p className="readiness-caution">{result.caution}</p>
    </>}
    <details className="readiness-details">
      <summary>Why this result? View trend and assumptions</summary>
      <label>Morning date <input aria-label="Readiness morning date" type="date" max={today} value={selectedDate} onChange={event => { if (event.target.value) setSelectedDate(event.target.value); }} /></label>
      {selectedDate !== today && <button type="button" onClick={() => setSelectedDate(today)}>Return to today</button>}
      {result && <>
        <div className="readiness-contributors">
          {result.groups.map(group => <div key={group.name}>
            <strong>{titles[group.name]}</strong>
            <span>{group.penalty_min === group.penalty_max ? group.penalty_min : `${group.penalty_min}–${group.penalty_max}`} points deducted · {group.complete ? "covered" : "partial evidence"}</span>
            <small>Maximum {group.budget} points</small>
            {group.name === "autonomic" && <small>Baseline {group.baseline_start}–{group.baseline_end}: {group.hrv_baseline?.count ?? 0} HRV nights, {group.rhr_baseline?.count ?? 0} RHR days. HRV {result.inputs.hrv?.value ?? "missing"} ms; previous-day RHR {result.inputs.rhr_previous_day?.value ?? "missing"} bpm.</small>}
            {group.name === "sleep" && <small>{result.inputs.sleep ? (result.inputs.sleep.value / 3600).toFixed(1) : "Missing"} hours against {group.target_hours} hour target; quality {result.inputs.sleep_score?.value ?? "missing"} / 100.</small>}
            {group.name === "workload" && <small>Decayed load {group.exposure}; {group.reference_mornings} complete reference mornings{group.percentile != null ? `; percentile ${Math.round(group.percentile * 100)}` : ""}. {(group.missing_activity_ids ?? []).length} sessions missing load or end time.</small>}
          </div>)}
        </div>
        <p>HRV and resting heart rate share one deduction. Sleep uses the larger duration or quality deduction. Workload combines recorded load and time since each session, then compares it with your earlier mornings. Missing evidence leaves the remaining deduction uncertain.</p>
        <ul className="readiness-flags">{result.warnings.map(flag => <li key={flag}>{flags[flag] ?? flag.replaceAll("_", " ")}</li>)}</ul>
        {result.sensitivity && <p>Parameter sensitivity: {result.sensitivity.low}–{result.sensitivity.high} / 100. {result.sensitivity.band_changes ? "The band changes across tested assumptions." : "The band stays the same across tested assumptions."}</p>}
        <details><summary>Workouts included before the cutoff</summary>
          {result.groups.find(group => group.name === "workload")?.sessions?.map(session => <p key={session.id}><a href="#activities">Workout ending {new Date(session.ended_at).toLocaleString([], { timeZone: timezone })}</a>: load {session.load ?? "missing"}, {session.hours_since_end} hours earlier.</p>)}
        </details>
        <h4>Last 14 mornings</h4>
        <div className="readiness-trend" aria-label="Readiness trend">
          {data?.trend.map(item => <button key={item.date} type="button" onClick={() => setSelectedDate(item.date)} title={`${item.date}: ${value(item)}`} aria-label={`${item.date}: ${value(item)}`}>
            <span className="readiness-trend-track"><span className={`readiness-trend-bar readiness-${item.band ?? "partial"}`} style={{ height: `${item.score ?? item.score_range?.high ?? 0}%` }} />{item.score_range && item.score === null && <span className="readiness-range-mark" style={{ bottom: `${item.score_range.low}%`, height: `${item.score_range.high - item.score_range.low}%` }} />}</span>
            <small>{item.date.slice(5)}</small><small>{item.score ?? (item.score_range ? `${item.score_range.low}–${item.score_range.high}` : "—")}</small>
          </button>)}
        </div>
        <small>Dashed ranges show unknown deductions. A dash means insufficient data. Historical results are reconstructions from corrected records, not stored proof of what was known then.</small>
        <details><summary>Adjust model parameters</summary>
          <p>Defaults and weights are provisional. Budgets must total 100. Saving creates a new parameter version and recalculates the view; earlier calculations remain stored.</p>
          <form onSubmit={event => void save(event)} className="readiness-settings">
            {Object.entries(draft).map(([key, current]) => <label key={key}>{labels[key] ?? key}<input type="number" required step="any" value={current} onChange={event => setDraft(previous => ({ ...previous, [key]: Number(event.target.value) }))} /></label>)}
            <button disabled={saving} type="submit">{saving ? "Saving…" : "Save readiness parameters"}</button>
          </form>
        </details>
        <small>{result.formula_version} · calculation {result.calculation_id} · {result.config_version}</small>
      </>}
    </details>
  </>;
}
