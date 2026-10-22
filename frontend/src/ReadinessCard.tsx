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
  inputs: { hrv: Reading; rhr_previous_day: Reading; rhr?:Reading; rhr_selection?:{kind:"same_day"|"previous_day_fallback"|"projected"|"missing";date:string|null;provisional:boolean;description:string}; sleep: Reading; sleep_score: Reading; hrv_7day?:{average:number|null;nights:number} };
  groups: Group[]; config_version: string; formula_version: string; caution: string;
  sensitivity?: { low: number; high: number; band_changes: boolean };
  calculation_id: number|null; calculated_at: string;cache_status?:'stored'|'deferred';
};
type Forecast = {hrv_7day?:{average:number|null;nights:number};comparison?:{today_score:number|null;baseline_score:number;contributors:Array<{name:string;today_penalty:number;projected_penalty:number;score_change:number}>;explanation:string};date:string;as_of:string;status:string;score:number|null;range:{low:number;high:number}|null;reason?:string;model?:{lookback_days:number;usable_mornings:number;selected:string;baseline_mae:number|null;regression_mae:number|null;evaluation_mornings:number};assumptions:string[];limitations:string[];validation:{mornings:number;mean_absolute_error:number|null;range_method?:string}|null};
type Response = {
  latest: Result; trend: Result[]; settings: { parameters: Record<string, number> }; reconstruction: string;
};
const flags: Record<string, string> = {
  rhr_same_day_provisional: "Today's stored resting heart rate is provisional and may change as the daily record updates.",
  rhr_same_day_historical_reconstruction: "Same-day resting heart rate uses corrected historical records; its availability that morning is unknown.",
  rhr_previous_day_fallback: "No eligible same-day resting heart rate is stored, so the previous day's value is used.",
  rhr_previous_day_context: "Previous-day resting heart rate was used because a same-day reading was unavailable.",
  historical_estimate_uses_current_corrected_records: "Historical estimates use corrected records available now, with references drawn only from earlier dates.",
  unusually_high_hrv_no_bonus: "HRV is unusually high. This earns no bonus and does not establish full recovery.",
  hrv_missing_or_insufficient_baseline: "Latest nightly HRV, at least five of the last seven nights, or enough personal baseline history is missing.",
  rhr_missing_or_insufficient_baseline: "Resting heart rate or enough baseline history is missing.",
  completed_sleep_missing: "Completed sleep with a recorded wake time is missing for this date.",
  sleep_score_missing: "Sleep quality score is missing.",
  sleep_trend_insufficient: "At least two of the latest three sleep nights are needed for the short trend.",
  workload_coverage_or_reference_incomplete: "Recent workout coverage, explicit loads, end times, or enough fully covered reference mornings are missing.",
  morning_observation_not_finished: "The morning cutoff has not passed yet. Check again after your recorded sleep ends.",
  band_sensitive_to_provisional_parameters: "Reasonable changes to the prototype parameters change this day's band. Treat the band cautiously.",
};
const titles: Record<string, string> = { autonomic: "HRV and resting heart rate", sleep: "Sleep", workload: "Recent workload" };
const labels: Record<string, string> = {
  sleep_target_hours: "Sleep target (hours)", load_half_life_hours: "Load half-life (hours)",
  autonomic_weight: "HRV / heart-rate budget", sleep_weight: "Sleep budget", workload_weight: "Workload budget",
  baseline_days: "Baseline window (days)", baseline_min_nights: "Minimum baseline nights",
  load_reference_days: "Load reference window (days)", load_min_mornings: "Minimum reference mornings",
  hrv_scale_floor: "Minimum log-HRV scale", rhr_scale_floor: "Minimum RHR scale (bpm)",
  deviation_tolerance: "Deviation tolerance", morning_hour: "Fallback morning hour (no wake time)",
};
function value(result: Result) {
  if (result.score !== null) return `${result.score} / 100`;
  if (result.score_range) return `${result.score_range.low}–${result.score_range.high} / 100`;
  return result.status === "awaiting_morning" ? "Awaiting morning" : "Insufficient data";
}

export function ReadinessCard({ timezone, refreshToken }: { timezone: string; refreshToken: string }) {
  const [clock,setClock]=useState(()=>Date.now());
  useEffect(()=>{const timer=window.setInterval(()=>setClock(Date.now()),60000);return()=>window.clearInterval(timer);},[]);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(clock));
  const [historicalDate, setHistoricalDate] = useState<string | null>(null);
  const selectedDate = historicalDate ?? today;
  const setSelectedDate = (value: string) => setHistoricalDate(value === today ? null : value);
  const [data, setData] = useState<Response | null>(null);
  const [forecastError,setForecastError]=useState<string|null>(null);
  const [forecast,setForecast]=useState<Forecast|null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") {
        setClock(Date.now());
        setRevision(current => current + 1);
      }
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null);setForecastError(null);setForecast(null);setData(previous=>previous?.latest.date===selectedDate?previous:null);
    const current=fetch(`/api/readiness?end_date=${selectedDate}&days=14&timezone=${encodeURIComponent(timezone)}`, { signal: controller.signal, cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Readiness could not be loaded.");
        return response.json() as Promise<Response>;
      })
      ;
    const projection=selectedDate===today ? fetch(`/api/readiness/forecast?timezone=${encodeURIComponent(timezone)}`,{signal:controller.signal,cache:"no-store"}).then(async response=>{if(!response.ok) throw new Error('Tomorrow’s readiness forecast could not be loaded.');return response.json() as Promise<Forecast>;}).catch(error=>{if(!controller.signal.aborted&&error.name!=='AbortError')setForecastError(error.message);return null;}) : Promise.resolve(null);
    void current.then(result=>{if(controller.signal.aborted)return;setData(result);setDraft(result.settings.parameters);}).catch(error=>{if(!controller.signal.aborted&&error.name!=='AbortError')setError(error.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    void projection.then(value=>{if(!controller.signal.aborted)setForecast(value);});
    return () => controller.abort();
  }, [selectedDate, today, timezone, refreshToken, revision]);
  useEffect(()=>{if(data?.latest.status==='awaiting_morning'&&clock>=Date.parse(data.latest.cutoff))setRevision(r=>r+1);},[clock,data?.latest.cutoff,data?.latest.status]);
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
  const rhr=result?.inputs.rhr_selection?result.inputs.rhr:result?.inputs.rhr??result?.inputs.rhr_previous_day;
  const rhrSelection=result?.inputs.rhr_selection;
  const rhrLabel=rhrSelection?.kind==='same_day'?'Same-day resting heart rate':rhrSelection?.kind==='projected'?'Projected resting heart rate':rhrSelection?.kind==='missing'?'Resting heart rate unavailable':'Previous-day resting heart rate (fallback)';
  return <>
    <div className="readiness-overview"><section className="readiness-today" aria-label={selectedDate===today?"Today’s measured readiness":"Selected day’s measured readiness"}>
    <h3 className="readiness-day-title">{selectedDate===today?"Today’s readiness":"Recorded readiness"} · {selectedDate}</h3><p>Based on morning measurements <span className="readiness-prototype">Prototype</span></p>
    {result ? <StatusDial
      value={result.score !== null ? String(result.score) : result.score_range ? `${result.score_range.low}–${result.score_range.high}` : '—'}
      unit="/ 100" bands={readinessBands}
      position={result.score !== null ? result.score / 100 : null}
      range={result.score === null && result.score_range ? { low: result.score_range.low / 100, high: result.score_range.high / 100 } : null}
      interpretation={result.score !== null ? result.score < 50 ? 'Recovery focus · prioritize rest or an easy session.' : result.score < 80 ? 'Ready with care · keep the session manageable.' : 'Well prepared · measured recovery signals are favorable.' : result.score_range ? 'Possible range for this day · incomplete measurements prevent a single score.' : result.status === 'awaiting_morning' ? 'Awaiting morning measurements' : 'Not enough data to assess readiness'}
    /> : <h3>{loading ? 'Loading…' : '—'}</h3>}
    {result && result.score===null && result.score_range && <p className="readiness-range-key">Outer arc: possible readiness <strong>{result.score_range.low}–{result.score_range.high} / 100</strong> for {result.date}. These are the lower and upper bounds for the same day.</p>}
    {loading&&result&&<p role="status">Refreshing readiness…</p>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {result && <>
      {result.inputs.hrv_7day?.average!=null&&<p>Seven-day HRV average: <strong>{result.inputs.hrv_7day.average.toFixed(1)} ms</strong> · {result.inputs.hrv_7day.nights}/7 nights.</p>}
      <div className="readiness-explanation"><strong>{rhrLabel}: {rhr?`${rhr.value} ${rhr.unit}`:'Not recorded'}</strong>{rhr&&<p>Recorded date: {rhr.wake_date} · Source: {rhr.source_name.replaceAll('_',' ')}{rhrSelection?.provisional?' · Provisional':''}</p>}{rhrSelection?.description&&<p>{rhrSelection.description}</p>}{!rhrSelection&&rhr&&<p>Previous-day fallback from the recorded evidence.</p>}</div>
      <span>{result.data_quality} data quality</span>
      <small>{result.date} · {timezone} · observation {new Date(result.cutoff).toLocaleTimeString([], { timeZone: timezone, hour: "2-digit", minute: "2-digit" })}</small>
      {result.status==='awaiting_morning'&&<p className="readiness-explanation">Waiting for completed sleep or missing morning measurements. Recorded wake time takes priority over the fallback morning hour.{result.inputs.sleep && result.inputs.hrv ? ' Sleep and HRV are already synced.' : ' Sync after your sleep measurements are available.'}</p>}
      {result.status==='insufficient_data'&&<p className="readiness-explanation">{result.warnings.filter(f=>!['rhr_previous_day_context','historical_estimate_uses_current_corrected_records'].includes(f)).map(f=>flags[f]??f).join(' ')}</p>}
      <p className="readiness-caution">{result.caution}</p>
    </>}
    </section>
    {forecastError&&<p role="alert">{forecastError}</p>}
    {forecast&&selectedDate===today&&!loading&&<section className="readiness-forecast" aria-label="Tomorrow’s projected training readiness">
      <h3 className="readiness-day-title">Tomorrow’s forecast · {forecast.date}</h3><p>Projection · awaiting tomorrow’s measurements</p>
      {forecast.score!==null ? <StatusDial value={String(forecast.score)} unit="/ 100 · forecast" bands={readinessBands} position={forecast.score/100} interpretation={forecast.score<50?'Projected recovery focus':forecast.score<80?'Projected ready with care':'Projected favorable recovery signals'}/> : <p>{forecast.reason??'Not enough history to project tomorrow.'}</p>}
      {forecast.comparison&&<div className="readiness-explanation">
        <p>{forecast.comparison.explanation}</p>
        <ul>{forecast.comparison.contributors.map(item=><li key={item.name}>{item.name}: {Math.abs(item.score_change)<0.5?'no material change':`${Math.abs(item.score_change).toFixed(1)} points ${item.score_change>0?'higher':'lower'}`} versus today.</li>)}</ul>
        {forecast.model?.selected==='regularized_regression'&&<p>The final score also includes a correction based on historical forecast errors.</p>}
      </div>}
      {forecast.range&&<p>Estimated range: <strong>{forecast.range.low}–{forecast.range.high} / 100</strong>. {forecast.range.high-forecast.range.low>=30?'Wide range · tomorrow remains uncertain.':'Actual morning measurements can differ.'}</p>}
      {forecast.model&&<small>100-day model review · {forecast.model.usable_mornings} usable mornings · {forecast.model.selected==='regularized_regression'?'regression selected':'recent-trend model retained'}.</small>}
      {forecast.validation&&<small>Historical checks: {forecast.validation.mornings} mornings{forecast.validation.mean_absolute_error!==null?` · average error ${forecast.validation.mean_absolute_error} points`:''}.</small>}
      {forecast.status==='provisional'&&<p>{forecast.reason}</p>}
      {forecast.hrv_7day?.average!=null&&<p>Projected seven-day HRV average: <strong>{forecast.hrv_7day.average.toFixed(1)} ms</strong> · includes one projected night.</p>}
      <small>Updated {new Date(forecast.as_of).toLocaleTimeString([],{timeZone:timezone,hour:'2-digit',minute:'2-digit'})} · assumes no further workouts before tomorrow morning.</small>
      <details><summary>Forecast method and uncertainty</summary>{forecast.model&&<p>Chronological checks: trend-model error {forecast.model.baseline_mae??'unavailable'} points; regression error {forecast.model.regression_mae??'unavailable'} points across {forecast.model.evaluation_mornings} mornings. Regression is selected only with enough checks and at least 5% improvement.</p>}<ul>{forecast.assumptions.map(a=><li key={a}>{a}</li>)}</ul><ul>{forecast.limitations.map(a=><li key={a}>{a}</li>)}</ul>{forecast.validation?.range_method&&<p>{forecast.validation.range_method}</p>}</details>
    </section>}
    </div>
    <button type="button" disabled={loading} onClick={()=>setRevision(r=>r+1)}>Refresh readiness</button>
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
            {group.name === "autonomic" && <small>Baseline {group.baseline_start}–{group.baseline_end}: {group.hrv_baseline?.count ?? 0} HRV nights, {group.rhr_baseline?.count ?? 0} RHR days. HRV {result.inputs.hrv?.value ?? "missing"} ms; {rhrLabel} {rhr?.value ?? "missing"} bpm{rhr?.wake_date?` · ${rhr.wake_date}`:""}{rhrSelection?.provisional?" · provisional":""}.</small>}
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
        <small>{result.formula_version} · {result.calculation_id!=null?`calculation ${result.calculation_id}`:'Calculated from current data · history save pending'} · {result.config_version}</small>
      </>}
    </details>
  </>;
}
