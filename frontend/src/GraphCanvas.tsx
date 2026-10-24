import {requestJson} from './request';
import SleepCard from './SleepCard';
import RecoveryDial from './RecoveryDial';
import SortableCards from './SortableCards';
import { memo, useEffect, useRef, useState } from 'react';
import InteractivePlot from './InteractivePlot';
import StatusDial, { fitnessBands } from './StatusDial';

export type ChartSpec = { id?: string; title?: string; metric: string; x_metric?: string; kind: 'line' | 'bar' | 'scatter' | 'dial'; start?: string; end?: string; sport?: string; size?: 'half' | 'full'; timezone?: string; gps_reference_id?: string; reference_lines?: (number | 'mean')[]; trend_line?: boolean; correlation?: boolean; aggregation?: string; rolling_days?: number; sprint_seconds?: number; interval_min_seconds?: number; interval_max_seconds?: number; min_repetitions?: number; threshold_watts?: number; fit_stat?: string; activity_ids?: string[]; window_days?: number; show_chronic?: boolean; show_optimal_range?: boolean };
type ChartSeries = { color?: string; color_name?: string; id: string; label: string; started_at?: string; date?: string; source: string; count: number; display_count: number; missing_samples: number; gap_count: number; mean: number | null; minimum: number | null; maximum: number | null };
export type ChartResult = { spec: ChartSpec; series?: ChartSeries[]; x_domain?: string[]; range_band?: {label: string; points: {date: string; low: number; high: number; source: string}[]}; points: { x: string | number; y: number; date: string; source: string; id: string; series_id?: string; segment?: number; recorded_at?: string }[]; unit: string; x_unit: string; count: number; excluded: number; unpaired: number; latest: { y: number; date: string; source: string } | null; notes: string[]; sources: string[]; analysis?: { sample_count: number; reference_lines: { label: string; value: number }[]; trend: { x_start: string | number; x_end: string | number; y_start: number; y_end: number; slope: number; r_squared: number } | null; pearson_r: number | null; r_squared: number | null; reason: string | null } };
type CatalogItem = { id: string; label: string; unit: string };
type Catalog = { metrics: CatalogItem[]; activity_fields: CatalogItem[] };
type Profile = { birth_date: string | null; sex: string | null };
const reference = 'https://www8.garmin.com/manuals/webhelp/GUID-9183E86B-2399-4CFC-AB50-EAFC6D6ED326/EN-US/GUID-1FBCCD9E-19E1-4E4C-BD60-1793B5B97EB3.html';
const bands = {
  male: [[41.7,45.4,51.1,55.4],[40.5,44,48.3,54],[38.5,42.4,46.4,52.5],[35.6,39.2,43.4,48.9],[32.3,35.5,39.5,45.7],[29.4,32.3,36.7,42.1]],
  female: [[36.1,39.5,43.9,49.6],[34.4,37.8,42.4,47.4],[33,36.3,39.7,45.3],[30.1,33,36.7,41.1],[27.5,30,33,37.8],[25.9,28.1,30.9,36.7]],
};
export const api=requestJson;

const jsonRequest = (value: unknown, method = 'POST'): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
const label = (id: string) => id === 'activity_elevation' ? 'Total climb' : id.replace('activity_', 'Activity ').replace('vo2_', 'VO₂ max · ').replaceAll('_', ' ');
function localDate() { return new Intl.DateTimeFormat('en-CA', {year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()); }
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const loadWidget: ChartSpec = {id:'acute-load-4-weeks',metric:'acute_training_load',kind:'line',title:'Acute training load · 4 weeks',size:'full',window_days:28,show_chronic:false,show_optimal_range:true};
const defaults: ChartSpec[] = [
  loadWidget,
  { id: 'vo2', metric: 'vo2_cycling', kind: 'dial', title: 'VO₂ max · cycling', size: 'half' },
  { id: 'weight', metric: 'weight', kind: 'line', title: 'Weight history', size: 'half' },
];

const healthDefaults: ChartSpec[] = [{id:'health-sleep-score',metric:'sleep_score',kind:'line',title:'Sleep & overnight HRV',size:'half'},{id:'health-weight',metric:'weight',kind:'line',title:'Weight history',size:'half'}];

function rating(value: number, profile?: Profile | null, measurementDate?: string) {
  if (!profile?.birth_date) return { text: 'Add your birth date in Profile for an age comparison.', fraction: null };
  const birth = new Date(profile.birth_date + 'T00:00:00');
  const now = measurementDate ? new Date(measurementDate + 'T00:00:00') : new Date();
  const age = now.getFullYear() - birth.getFullYear() - (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate()) ? 1 : 0);
  const sex = profile.sex?.toLowerCase().trim();
  const population = sex === 'male' || sex === 'm' ? 'male' : sex === 'female' || sex === 'f' ? 'female' : null;
  if (!population) return { text: `Age ${age} · Select male or female reference population in Profile.`, fraction: null };
  if (age < 20 || age > 79) return { text: `Age ${age} · Reference table covers ages 20–79.`, fraction: null };
  const index = Math.floor(age / 10) - 2;
  const thresholds = bands[population][index];
  const level = thresholds.filter(t => value >= t).length;
  // Open-ended categories need finite drawing bounds. Use a numeric scale,
  // keeping every reference boundary and the observed value on that scale.
  const low = Math.max(0, Math.min(value, thresholds[0] - (thresholds[3] - thresholds[0]) / 3));
  const high = Math.max(value, thresholds[3] + thresholds[3] - thresholds[2]);
  const span = high - low;
  const dialBands = fitnessBands.map((band, i) => ({
    ...band,
    end: i < 4 ? (thresholds[i] - low) / span : 1,
    detail: i === 0 ? `< ${thresholds[0]}` : i === 4 ? `≥ ${thresholds[3]}` : `${thresholds[i - 1]}–< ${thresholds[i]}`,
  }));
  return { text: `${['Poor','Fair','Good','Excellent','Superior'][level]} · age ${age}${measurementDate ? ' at measurement' : ''} · ${20 + index * 10}–${29 + index * 10} ${population} reference`, fraction: (value - low) / span, dialBands };
}

export function Plot({ result, profile, height=365, onReset, resetAvailable=false }: { result: ChartResult; profile?: Profile | null; height?: number; onReset?:()=>void; resetAvailable?:boolean }) {
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(400);
  useEffect(() => { const observer = new ResizeObserver(entries => setWidth(Math.max(260, entries[0].contentRect.width))); if (frame.current) observer.observe(frame.current); return () => observer.disconnect(); }, [result.spec.kind, result.points.length > 0]);
  if (!result.points.length) return <div className="graph-empty">No recorded observations for this selection. Try another metric or period.</div>;
  if (result.spec.kind === 'dial') {
    const value = result.latest!.y;
    const comparison = result.spec.metric.startsWith('vo2_') ? rating(value, profile, result.latest!.date) : null;
    return <div className="graph-dial">{comparison ? <StatusDial value={value.toFixed(1)} unit={result.unit} bands={comparison.dialBands ?? fitnessBands} position={comparison.fraction} interpretation={comparison.text} /> : <div className="plain-dial-value"><strong>{value.toFixed(1)}</strong><span>{result.unit}</span><p>Latest {label(result.spec.metric)}</p></div>}{comparison && <a href={reference} target="_blank" rel="noreferrer">Garmin / Cooper five-category reference · v8, Sep 2026</a>}<p className="graph-meta">{result.latest!.date} · {result.latest!.source.replaceAll('_',' ')}</p></div>;
  }
  return <div ref={frame}><InteractivePlot result={result} width={width} height={height} onReset={onReset} resetAvailable={resetAvailable}/></div>;
}

function download(result: ChartResult) {
  const rows = ['date,x,y,x_unit,y_unit,source,activity_id,activity_name,segment,recorded_at', ...result.points.map(p => [p.date,p.x,p.y,result.x_unit,result.unit,p.source,p.id,result.series?.find(s => s.id === p.series_id)?.label ?? '',p.segment ?? '',p.recorded_at ?? ''].map(v=>`"${String(v).replaceAll('"','""')}"`).join(','))];
  const url=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'})); const a=document.createElement('a'); a.href=url; a.download='chart-data.csv'; a.click(); URL.revokeObjectURL(url);
}

function VO2Trend({metric,refresh}:{metric:string;refresh?:string|number}) {
  const today=localDate();const startDate=new Date(`${today}T12:00:00Z`);startDate.setUTCDate(startDate.getUTCDate()-27);
  const [range,setRange]=useState({start:startDate.toISOString().slice(0,10),end:today});
  const [result,setResult]=useState<ChartResult|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  useEffect(()=>{const controller=new AbortController();setError('');if(!range.start||!range.end||range.start>range.end){setError('Choose a valid date range.');return;}setLoading(true);void api<ChartResult>('/api/charts/query',{...jsonRequest({spec:{metric,kind:'line',start:range.start,end:range.end,timezone}}),signal:controller.signal}).then(r=>{if(!controller.signal.aborted)setResult(r);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[metric,range.start,range.end,refresh]);
  return <section aria-label="VO₂ max trend"><h4>VO₂ max trend</h4><div className="builder-fields"><label>From<input type="date" value={range.start} max={range.end} onChange={e=>setRange({...range,start:e.target.value})}/></label><label>To<input type="date" value={range.end} min={range.start} max={today} onChange={e=>setRange({...range,end:e.target.value})}/></label></div><button type="button" onClick={()=>setRange({start:startDate.toISOString().slice(0,10),end:today})}>Last 4 weeks</button>{loading?<p role="status">Loading trend…</p>:error?<p role="alert">{error}</p>:result&&<Plot result={result} height={280}/>}</section>;
}

function StandardChartCard({ spec, initial, profile, refresh, actions }: {spec: ChartSpec; initial?: ChartResult; profile?: Profile | null; refresh?: string | number; actions?: React.ReactNode}) {
  const [showVO2Trend,setShowVO2Trend]=useState(false);
  const [weightRange,setWeightRange]=useState<'six-months'|'custom'>('six-months');
  const [customRange,setCustomRange]=useState({start:spec.start??'',end:spec.end??localDate()});
  const today=localDate();const sixMonths=new Date(`${today}T12:00:00Z`);const originalDay=sixMonths.getUTCDate();sixMonths.setUTCDate(1);sixMonths.setUTCMonth(sixMonths.getUTCMonth()-6);const monthEnd=new Date(Date.UTC(sixMonths.getUTCFullYear(),sixMonths.getUTCMonth()+1,0)).getUTCDate();sixMonths.setUTCDate(Math.min(originalDay,monthEnd));
  const querySpec=spec.metric==='weight'?{...spec,...(weightRange==='six-months'?{start:sixMonths.toISOString().slice(0,10),end:today}:customRange)}:spec;
  const [result,setResult]=useState<ChartResult | null>(initial ?? null);
  const [error,setError]=useState(''); const [expanded,setExpanded]=useState(false); const [loadRefresh,setLoadRefresh]=useState(0),[refreshingLoad,setRefreshingLoad]=useState(false),[loadNotice,setLoadNotice]=useState('');
  useEffect(() => {const controller=new AbortController();setError(''); if(initial){setResult(initial);return;} setResult(null); api<ChartResult>('/api/charts/query',{...jsonRequest({spec:{...querySpec,timezone}}),signal:controller.signal}).then(result=>{if(!controller.signal.aborted)setResult(result);}).catch(e=>{if(!controller.signal.aborted&&e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[JSON.stringify(querySpec),initial,refresh,loadRefresh]);
  return <article className={`graph-card ${spec.size==='full'||expanded?'graph-card--full':''}`}>
    <div className="graph-heading"><div><h3>{spec.title || label(spec.metric)}</h3><p>{spec.gps_reference_id ? 'GPS-matched rides · ' : ''}{spec.metric.startsWith('stream:') ? 'Recorded activity traces · aligned by elapsed time' : spec.window_days ? `Last ${spec.window_days} days` : `${querySpec.start||'All history'} → ${querySpec.end||'Latest'}`}{spec.sport && spec.sport!=='all'?` · ${spec.sport}`:''}</p></div><button type="button" onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>{expanded?'Collapse':'Expand'}</button></div>
    {spec.metric==='weight'&&<div className="weight-range-controls"><label>Period<select value={weightRange} onChange={e=>setWeightRange(e.target.value as 'six-months'|'custom')}><option value="six-months">Last 6 months</option><option value="custom">Custom range</option></select></label>{weightRange==='custom'&&<><label>From<input type="date" value={customRange.start} max={customRange.end||today} onChange={e=>setCustomRange({...customRange,start:e.target.value})}/></label><label>To<input type="date" value={customRange.end} min={customRange.start||undefined} max={today} onChange={e=>setCustomRange({...customRange,end:e.target.value})}/></label></>}</div>}
    {result?.latest && spec.metric==='sleep_score' && <p className="health-score-summary"><strong>{result.latest.y.toLocaleString(undefined,{maximumFractionDigits:1})}<span> / 100</span></strong><span>Latest recorded sleep score · {result.latest.date}</span></p>}
    {error?<p role="alert">{error}</p>:result?<><Plot result={result} profile={profile} height={expanded?520:365} onReset={spec.metric==='weight'?()=>setWeightRange('six-months'):undefined} resetAvailable={spec.metric==='weight'&&weightRange!=='six-months'}/><div className="graph-meta">{result.count.toLocaleString()} observations · {result.sources.join(', ').replaceAll('_',' ')}{result.excluded>0?` · ${result.excluded} missing values`:''}{result.unpaired>0?` · ${result.unpaired} unpaired`:''}</div><details className="graph-notes"><summary>Data and pairing details</summary>{result.notes.map(note=><p key={note}>{note}</p>)}</details></>:<div className="graph-empty" role="status">Loading recorded data…</div>}
    {spec.metric.startsWith('vo2_')&&<><button type="button" aria-expanded={showVO2Trend} onClick={()=>setShowVO2Trend(v=>!v)}>{showVO2Trend?'Hide VO₂ max trend':'Show VO₂ max trend'}</button>{showVO2Trend&&<VO2Trend metric={spec.metric} refresh={refresh}/>}</>}
    <div className="graph-actions">{spec.window_days && spec.metric==='acute_training_load' && <button type="button" disabled={refreshingLoad} onClick={async()=>{setRefreshingLoad(true);setLoadNotice('Fetching recorded daily load…');try{const response=await api<{fetched_days:number;failed_dates:string[]}>('/api/charts/training-load/refresh',jsonRequest({timezone}));setLoadNotice(`${response.fetched_days} days fetched${response.failed_dates.length ? ` · ${response.failed_dates.length} dates could not be fetched` : ''}.`);setLoadRefresh(v=>v+1);}catch(error){setLoadNotice(error instanceof Error?error.message:'Could not refresh load');}finally{setRefreshingLoad(false);}}}>{refreshingLoad?'Refreshing…':'Refresh load history from Garmin'}</button>}{loadNotice && <span role="status">{loadNotice}</span>}{spec.metric === 'weight' && <button className="primary-button" type="button" onClick={() => { window.dispatchEvent(new Event('open-weight-entry')); }}>＋ Add weight</button>}{actions}{result && <button type="button" onClick={()=>download(result)}>Export CSV</button>}</div>
  </article>;
}

export function ChartCard(props: React.ComponentProps<typeof StandardChartCard> & {healthSleep?: boolean}) {
  if(props.healthSleep && props.spec.metric==='sleep_score')return <SleepCard spec={props.spec} actions={props.actions} refresh={props.refresh}/>;
  return <StandardChartCard {...props}/>;
}

function GraphCanvas({ mode='dashboard', profile, refresh=0 }: { mode?: 'dashboard'|'health'; profile?: Profile | null; refresh?: string | number }) {
  const layoutUrl=mode==='health'?'/api/health/widgets':'/api/dashboard/widgets';
  const [catalog,setCatalog]=useState<Catalog|null>(null),[widgets,setWidgets]=useState<ChartSpec[]>([]),[ready,setReady]=useState(false);
  const [error,setError]=useState(''),[saving,setSaving]=useState(false),[editing,setEditing]=useState<ChartSpec|null>(null);
  const builderRef=useRef<HTMLFormElement>(null);
  useEffect(()=>{if(editing){builderRef.current?.scrollIntoView({behavior:'instant',block:'start'});builderRef.current?.querySelector<HTMLInputElement>('input')?.focus({preventScroll:true});}},[editing?.id]);
  const [notice,setNotice]=useState('');
  useEffect(()=>{let active=true;setError('');void api<{widgets:ChartSpec[]|null}>(layoutUrl).then(w=>{if(active){setWidgets(w.widgets??(mode==='health'?healthDefaults:defaults));setReady(true);}}).catch(e=>{if(active)setError(e.message);});void api<Catalog>('/api/charts/catalog').then(c=>{if(active)setCatalog(c);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[refresh,mode]);
  const save=async(next:ChartSpec[])=>{setSaving(true);setError('');try{const r=await api<{widgets:ChartSpec[]}>(layoutUrl,jsonRequest({widgets:next},'PUT'));setWidgets(r.widgets);setNotice(mode==='health'?'Health dashboard saved.':'Dashboard saved.');return true;}catch(e){setError(e instanceof Error?e.message:'Could not save layout');return false;}finally{setSaving(false);}};
  useEffect(()=>{if(mode!=='dashboard')return;const pinned=(event:Event)=>{const spec=(event as CustomEvent<ChartSpec>).detail;sessionStorage.removeItem('garmin-pending-pin');setEditing({...spec,id:crypto.randomUUID()});};const retained=sessionStorage.getItem('garmin-pending-pin');if(retained){try{pinned(new CustomEvent('pin-chart',{detail:JSON.parse(retained)}));}catch{sessionStorage.removeItem('garmin-pending-pin');}}window.addEventListener('pin-chart',pinned);return()=>window.removeEventListener('pin-chart',pinned);},[mode]);
  const items = catalog ? [...catalog.metrics,...catalog.activity_fields].map(item=>item.id==='activity_elevation'?{...item,label:'Total climb'}:item) : [];
  const visible=widgets;

  return <section className="graph-canvas" aria-label={mode==='health'?'Health graphs':'Customizable graph dashboard'}>
    <div className="section-heading"><div><p>{mode==='health'?'Health history':'Modular canvas'}</p><h2>{mode==='health'?'Your health, over time':'Your graphs. Your layout.'}</h2><span className="graph-meta">{mode==='health'?'Recorded Garmin measurements and manual weight entries. Add, edit or remove cards to choose what you see.':'Add or replace any graph. Drag to rearrange, or use the move buttons.'}</span></div>{<button className="primary-button" type="button" disabled={!ready||saving} onClick={()=>setEditing({id:crypto.randomUUID(),metric:items.find(i=>i.id==='weight')?.id??items[0]?.id??'vo2_cycling',kind:'line',size:'half'})}>{mode==='health'?'＋ Add card':'＋ Add graph'}</button>}</div>
    {error&&<p role="alert">{error}</p>}<p className="canvas-status" role="status">{saving?'Saving layout…':notice}</p>
    {editing&&<form ref={builderRef} className="graph-builder" onSubmit={e=>{e.preventDefault();const index=widgets.findIndex(w=>w.id===editing.id);const next=[...widgets];if(index<0)next.push(editing);else next[index]=editing;void save(next).then(saved=>{if(saved)setEditing(null);});}}>
      <div className="graph-heading"><h3>{widgets.some(w=>w.id===editing.id)?'Replace or configure graph':'Add a graph'}</h3><button type="button" onClick={()=>setEditing(null)}>Cancel</button></div>
      {editing.gps_reference_id && <p className="graph-meta">This graph uses GPS-matched rides for the selected reference. <button type="button" onClick={() => { const {gps_reference_id, ...unscoped} = editing; void gps_reference_id; setEditing(unscoped); }}>Use all activities instead</button></p>}
      <div className="builder-fields"><label>Title<input maxLength={100} value={editing.title??''} placeholder="Name this graph" onChange={e=>setEditing({...editing,title:e.target.value})}/></label><label>Chart type<select value={editing.kind} onChange={e=>{const kind=e.target.value as ChartSpec['kind'];if(editing.metric.startsWith('stream:')){setEditing({...editing,kind:'line',x_metric:'elapsed_time'});return;}setEditing({...editing,...(kind==='dial'?{trend_line:false,correlation:false,reference_lines:[]}:{}),kind,x_metric:kind==='scatter'?'date':undefined});}}><option value="line">Line history</option><option value="bar">Bars</option><option value="scatter">Scatter comparison</option><option value="dial">Latest value / dial</option></select></label><label>{editing.kind==='scatter'?'Y metric':'Metric'}<select value={editing.metric} onChange={e=>{const {sprint_seconds,interval_min_seconds,interval_max_seconds,min_repetitions,threshold_watts,fit_stat,activity_ids,...base}=editing;void sprint_seconds;void interval_min_seconds;void interval_max_seconds;void min_repetitions;void threshold_watts;void fit_stat;const stream=e.target.value.startsWith('stream:');const sprint=e.target.value==='activity_sprint_power';setEditing({...base,metric:e.target.value,...(stream?{kind:'line' as const,activity_ids,trend_line:false,correlation:false,reference_lines:[],aggregation:undefined,rolling_days:undefined}:{}),...(sprint?{sprint_seconds:10,interval_min_seconds:10,interval_max_seconds:15,min_repetitions:2,kind:'scatter' as const}:{}),x_metric:stream?'elapsed_time':sprint?'date':editing.kind==='scatter'?(editing.x_metric==='date'?'date':e.target.value):undefined});}}>{items.map(m=><option key={m.id} value={m.id}>{m.label} ({m.unit})</option>)}</select></label>{editing.kind==='scatter'&&<label>X axis<select required value={editing.x_metric??''} onChange={e=>setEditing({...editing,x_metric:e.target.value})}><option value="date">Date / time</option>{items.filter(m=>m.id.startsWith('activity_')===editing.metric.startsWith('activity_')).map(m=><option key={m.id} value={m.id}>{m.label} ({m.unit})</option>)}</select></label>}{['line','bar'].includes(editing.kind)&&<label>X axis<input readOnly value={editing.metric.startsWith('stream:') ? 'Elapsed time (seconds)' : 'Date / time'}/></label>}<label>From<input type="date" value={editing.start??''} max={editing.end||undefined} onChange={e=>setEditing({...editing,start:e.target.value})}/></label><label>To<input type="date" value={editing.end??''} min={editing.start||undefined} onChange={e=>setEditing({...editing,end:e.target.value})}/></label><label>Activity filter<select value={editing.sport??'all'} onChange={e=>setEditing({...editing,sport:e.target.value})}><option value="all">All activities</option><option value="cycling">Cycling</option><option value="running">Running</option><option value="indoor_cycling">Indoor cycling</option></select></label><label>Width<select value={editing.size??'half'} onChange={e=>setEditing({...editing,size:e.target.value as 'half'|'full'})}><option value="half">Half canvas</option><option value="full">Full canvas</option></select></label></div>{editing.metric.startsWith('stream:') && <p className="graph-meta">{editing.activity_ids?.length ? `${editing.activity_ids.length} selected recordings will remain separate traces.` : 'Choose From and To dates to select up to eight recordings.'} Missing samples break the line; elapsed time includes pauses.</p>}{editing.metric==='activity_sprint_power'&&<div className="builder-fields"><label>Effort duration bin (seconds)<input type="number" min="1" max="120" required value={editing.sprint_seconds??10} onChange={e=>setEditing({...editing,sprint_seconds:Number(e.target.value),interval_min_seconds:Number(e.target.value),interval_max_seconds:Number(e.target.value)})}/></label><label>Minimum repetitions per ride<input type="number" min="2" max="50" required value={editing.min_repetitions??2} onChange={e=>setEditing({...editing,min_repetitions:Number(e.target.value)})}/></label><label>Power threshold (W, optional)<input type="number" min="1" value={editing.threshold_watts??''} placeholder="1.8 × ride median positive power" onChange={e=>setEditing({...editing,threshold_watts:e.target.value?Number(e.target.value):undefined})}/></label></div>}{editing.metric.startsWith('fit:')&&<label>FIT field statistic<select value={editing.fit_stat??'mean'} onChange={e=>setEditing({...editing,fit_stat:e.target.value})}><option value="mean">Mean</option><option value="maximum">Maximum</option><option value="minimum">Minimum</option><option value="sum">Sum</option><option value="count">Non-missing count</option></select></label>}<button className="primary-button" disabled={saving} type="submit">{saving?'Saving…':'Save graph'}</button>
    </form>}
    <SortableCards id={`${mode}:graphs`} className={`graph-grid ${mode==='health'?'health-graph-grid':''}`}>{visible.map(spec=><div className={`graph-slot ${spec.size==='full'?'graph-slot--full':''} ${mode==='health'&&spec.metric==='sleep_score'?'health-sleep-slot':''}`} key={spec.id} aria-label={spec.title??label(spec.metric)}><ChartCard healthSleep={mode==='health'} spec={spec} profile={profile} refresh={refresh} actions={<>{spec.window_days && spec.metric==='acute_training_load' && <label className="load-overlay-toggle"><input type="checkbox" checked={!!spec.show_chronic} disabled={saving} onChange={e=>void save(widgets.map(w=>w.id===spec.id?{...w,show_chronic:e.target.checked}:w))}/>Overlay chronic load</label>}{spec.kind!=='dial' && !(mode==='health' && spec.metric==='sleep_score') && !spec.window_days && !spec.metric.startsWith('stream:') && <button type="button" disabled={saving} aria-pressed={!!spec.trend_line} onClick={() => void save(widgets.map(w => w.id===spec.id ? {...w,trend_line:!w.trend_line} : w))}>{spec.trend_line?'Remove trend line':'Add trend line'}</button>}<button type="button" disabled={saving} onClick={()=>setEditing({...spec})}>Replace / edit</button><button type="button" disabled={saving} onClick={()=>void save([...widgets,{...spec,id:crypto.randomUUID()}])}>Duplicate</button><button type="button" disabled={saving} onClick={()=>void save(widgets.filter(w=>w.id!==spec.id))}>Remove</button></>}/></div>)}{mode==='health'&&<div key="recovery" className="graph-slot recovery-slot" aria-label="Recovery time"><RecoveryDial timezone={timezone} refreshToken={String(refresh)}/></div>}</SortableCards>
    {ready&&!widgets.length&&<p className="graph-empty">Your canvas is empty. Add any graph to get started.</p>}
  </section>;
}

export function AssistantPlots({ plots, profile }: {plots:ChartResult[];profile?:Profile|null}) {
  const [page,setPage]=useState(0),[notice,setNotice]=useState('');
  const total=Math.ceil(plots.length/4);
  useEffect(()=>setPage(Math.max(0,total-1)),[plots.length]);
  if(!plots.length)return null;
  return <section id="assistant-plots" className="assistant-plots" aria-label="Assistant plot workspace"><div className="section-heading"><div><p>Assistant plot workspace</p><h2>Explore the evidence</h2></div>{total>1&&<div><button disabled={!page} onClick={()=>setPage(page-1)}>Previous plots</button><span> {page+1} / {total} </span><button disabled={page>=total-1} onClick={()=>setPage(page+1)}>Next plots</button></div>}</div><div className="graph-grid">{plots.slice(page*4,page*4+4).map((result,i)=><ChartCard key={`${page}-${i}`} spec={result.spec} initial={result} profile={profile} actions={<button type="button" onClick={()=>{sessionStorage.setItem('garmin-pending-pin',JSON.stringify(result.spec));window.dispatchEvent(new CustomEvent('pin-chart',{detail:result.spec}));window.location.hash='dashboard';setNotice('Review the graph in the dashboard builder and save it.');}}>Pin to dashboard</button>}/>)}</div><p role="status">{notice}</p></section>;
}

export function WeightEntry({ onSaved, unit='kg' }: {onSaved:()=>void;unit?:'kg'|'lb'}) {
  const [day,setDay]=useState(localDate()),[value,setValue]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[sendToGarmin,setSendToGarmin]=useState(false);
  return <form id="weight-entry" className="weight-entry" onSubmit={async e=>{e.preventDefault();setBusy(true);try{const saved=await api<{id:string}>('/api/weight',jsonRequest({date:day,value:Number(value),unit}));setValue('');setMessage('Weight measurement saved locally.');onSaved();if(sendToGarmin){try{const delivery=await api<{message:string}>(`/api/weight/${saved.id}/garmin`,jsonRequest({timezone}));setMessage(delivery.message);}catch{setMessage('Saved locally. Garmin delivery is unconfirmed; check Garmin Connect before sending another copy.');}}}catch(error){setMessage(error instanceof Error?error.message:'Could not save weight');}finally{setBusy(false);}}}><h3>Log a weight measurement</h3><p>Dated entries appear alongside Garmin measurements in your graphs.</p><div className="builder-fields"><label>Date<input type="date" required value={day} max={localDate()} onChange={e=>setDay(e.target.value)}/></label><label>Weight ({unit})<input type="number" required step="0.1" min="1" value={value} onChange={e=>setValue(e.target.value)}/></label></div><label className="weight-publish-toggle"><input type="checkbox" checked={sendToGarmin} disabled={busy} onChange={e=>setSendToGarmin(e.target.checked)}/>Also send this measurement to Garmin Connect</label><button className="primary-button" disabled={busy}>{busy?'Saving…':sendToGarmin?'Save and send to Garmin':'Save measurement'}</button><p role="status">{message}</p></form>;
}

export default memo(GraphCanvas);
