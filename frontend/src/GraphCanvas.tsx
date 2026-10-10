import { useEffect, useRef, useState } from 'react';
import StatusDial, { fitnessBands } from './StatusDial';

export type ChartSpec = { id?: string; title?: string; metric: string; x_metric?: string; kind: 'line' | 'bar' | 'scatter' | 'dial'; start?: string; end?: string; sport?: string; size?: 'half' | 'full'; timezone?: string; gps_reference_id?: string; reference_lines?: (number | 'mean')[]; trend_line?: boolean; correlation?: boolean };
export type ChartResult = { spec: ChartSpec; points: { x: string | number; y: number; date: string; source: string; id: string }[]; unit: string; x_unit: string; count: number; excluded: number; unpaired: number; latest: { y: number; date: string; source: string } | null; notes: string[]; sources: string[]; analysis?: { sample_count: number; reference_lines: { label: string; value: number }[]; trend: { x_start: string | number; x_end: string | number; y_start: number; y_end: number; slope: number; r_squared: number } | null; pearson_r: number | null; r_squared: number | null; reason: string | null } };
type CatalogItem = { id: string; label: string; unit: string };
type Catalog = { metrics: CatalogItem[]; activity_fields: CatalogItem[] };
type Profile = { birth_date: string | null; sex: string | null };
const reference = 'https://www8.garmin.com/manuals/webhelp/GUID-9183E86B-2399-4CFC-AB50-EAFC6D6ED326/EN-US/GUID-1FBCCD9E-19E1-4E4C-BD60-1793B5B97EB3.html';
const bands = {
  male: [[41.7,45.4,51.1,55.4],[40.5,44,48.3,54],[38.5,42.4,46.4,52.5],[35.6,39.2,43.4,48.9],[32.3,35.5,39.5,45.7],[29.4,32.3,36.7,42.1]],
  female: [[36.1,39.5,43.9,49.6],[34.4,37.8,42.4,47.4],[33,36.3,39.7,45.3],[30.1,33,36.7,41.1],[27.5,30,33,37.8],[25.9,28.1,30.9,36.7]],
};
export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The request could not be completed.');
  return result as T;
}
const jsonRequest = (value: unknown, method = 'POST'): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
const label = (id: string) => id.replace('activity_', 'Activity ').replace('vo2_', 'VO₂ max · ').replaceAll('_', ' ');
function localDate() { return new Intl.DateTimeFormat('en-CA', {year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()); }
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const defaults: ChartSpec[] = [
  { id: 'vo2', metric: 'vo2_cycling', kind: 'dial', title: 'VO₂ max · cycling', size: 'half' },
  { id: 'weight', metric: 'weight', kind: 'line', title: 'Weight history', size: 'half' },
  { id: 'rides', metric: 'activity_speed', x_metric: 'activity_power', kind: 'scatter', title: 'Power vs speed across rides', sport: 'cycling', size: 'full' },
];

function rating(value: number, profile?: Profile | null) {
  if (!profile?.birth_date) return { text: 'Add your birth date in Profile for an age comparison.', fraction: null };
  const birth = new Date(profile.birth_date + 'T00:00:00');
  const now = new Date();
  const age = now.getFullYear() - birth.getFullYear() - (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate()) ? 1 : 0);
  const sex = profile.sex?.toLowerCase().trim();
  const population = sex === 'male' || sex === 'm' ? 'male' : sex === 'female' || sex === 'f' ? 'female' : null;
  if (!population) return { text: `Age ${age} · Select male or female reference population in Profile.`, fraction: null };
  if (age < 20 || age > 79) return { text: `Age ${age} · Reference table covers ages 20–79.`, fraction: null };
  const index = Math.floor(age / 10) - 2;
  const thresholds = bands[population][index];
  const level = thresholds.filter(t => value >= t).length;
  return { text: `${['Poor','Fair','Good','Excellent','Superior'][level]} · age ${age} · ${20 + index * 10}–${29 + index * 10} ${population} reference`, fraction: (level + .5) / 5 };
}

export function Plot({ result, profile, height=365 }: { result: ChartResult; profile?: Profile | null; height?: number }) {
  const frame = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(400);
  useEffect(() => { const observer = new ResizeObserver(entries => setWidth(Math.max(260, entries[0].contentRect.width))); if (frame.current) observer.observe(frame.current); return () => observer.disconnect(); }, []);
  if (!result.points.length) return <div className="graph-empty">No recorded observations for this selection. Try another metric or period.</div>;
  if (result.spec.kind === 'dial') {
    const value = result.latest!.y;
    const comparison = result.spec.metric.startsWith('vo2_') ? rating(value, profile) : null;
    return <div className="graph-dial">{comparison ? <StatusDial value={value.toFixed(1)} unit={result.unit} bands={fitnessBands} position={comparison.fraction} interpretation={comparison.text} /> : <div className="plain-dial-value"><strong>{value.toFixed(1)}</strong><span>{result.unit}</span><p>Latest {label(result.spec.metric)}</p></div>}{comparison && <a href={reference} target="_blank" rel="noreferrer">Garmin / Cooper reference · v8, Sep 2026</a>}<p className="graph-meta">{result.latest!.date} · {result.latest!.source.replaceAll('_',' ')}</p></div>;
  }
  const scatter = result.spec.kind === 'scatter';
  const points = result.points.map(p => ({ ...p, nx: scatter ? Number(p.x) : Date.parse(p.date + 'T00:00:00Z') }));
  const analysis = result.analysis;
  const trend = analysis?.trend;
  const xs = points.map(p => p.nx), ys = [...points.map(p => p.y), ...(analysis?.reference_lines.map(p => p.value) ?? []), ...(trend ? [trend.y_start, trend.y_end] : [])];
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const rawMinY = result.spec.kind === 'bar' ? Math.min(0,...ys) : Math.min(...ys), rawMaxY = Math.max(...ys);
  const padding = rawMinY === rawMaxY ? Math.max(1, Math.abs(rawMaxY) * .05) : 0;
  const minY = rawMinY - padding, maxY = rawMaxY + padding;
  const xSpan = maxX-minX || (scatter ? 1 : 86400000), ySpan = maxY-minY || Math.max(1, Math.abs(maxY)*.1);
  const left=64, right=width-18, top=32, bottom=height-65;
  const x = (v:number) => minX === maxX ? (left+right)/2 : left + 8 + (v-minX)/xSpan*(right-left-16);
  const y = (v:number) => bottom-8-(v-minY+ySpan*.08)/(ySpan*1.16)*(bottom-top-16);
  const number = (n:number) => n.toLocaleString(undefined, {maximumFractionDigits:1});
  const tickX = (n:number) => scatter ? number(n) : new Date(n).toLocaleDateString(undefined,{month:'short',year:'2-digit',timeZone:'UTC'});
  const segments: typeof points[] = [];
  points.forEach((p,i) => { if (!i || p.nx-points[i-1].nx > 7*86400000) segments.push([]); segments[segments.length-1].push(p); });
  return <div ref={frame} className="plot-frame"><svg viewBox={`0 0 ${width} ${height}`} style={{height}} role="img" aria-label={`${result.spec.title ?? label(result.spec.metric)}. ${result.count} recorded observations.`}>
    <text x={left} y="16" className="axis-label">{result.unit}</text>
    {[0,1,2,3,4].map(i => {const v=minY+(maxY-minY)*i/4; return <g key={i}><line x1={left} x2={right} y1={y(v)} y2={y(v)} className="chart-grid"/><text x={left-10} y={y(v)+4} textAnchor="end">{number(v)}</text></g>;})}
    {(minX === maxX ? [0] : [0,1,2]).map(i => <text key={i} x={minX===maxX ? x(minX) : left+(right-left)*i/2} y={bottom+22} textAnchor={minX===maxX?'middle':i===0?'start':i===2?'end':'middle'}>{tickX(minX+xSpan*i/2)}</text>)}
    <text x={(left+right)/2} y={height-11} textAnchor="middle" className="axis-label">{scatter ? `${label(result.spec.x_metric!)} (${result.x_unit})` : 'Date'}</text>
    {result.spec.kind==='line' && segments.map((segment,i) => <polyline key={i} points={segment.map(p => `${x(p.nx)},${y(p.y)}`).join(' ')} className="chart-line"/>)}
    {analysis?.reference_lines.map((line,i) => <g key={`ref-${i}`}><line x1={left} x2={right} y1={y(line.value)} y2={y(line.value)} className="chart-reference"/><text x={right-4} y={y(line.value)-5} textAnchor="end">{line.label}: {number(line.value)} {result.unit}</text></g>)}
    {trend && <line x1={x(scatter?Number(trend.x_start):Date.parse(trend.x_start+'T00:00:00Z'))} x2={x(scatter?Number(trend.x_end):Date.parse(trend.x_end+'T00:00:00Z'))} y1={y(trend.y_start)} y2={y(trend.y_end)} className="chart-trend"><title>Least-squares trend</title></line>}
    {points.map((p,i) => <g key={i}><title>{`${p.date}: ${scatter ? `${number(Number(p.x))} ${result.x_unit}, ` : ''}${number(p.y)} ${result.unit} · ${p.source.replaceAll('_',' ')}`}</title>{result.spec.kind==='bar'?<rect x={x(p.nx)-Math.min(7,(right-left)/points.length/3)} y={y(p.y)} width={Math.max(1,Math.min(14,(right-left)/points.length*2/3))} height={Math.max(1,y(0)-y(p.y))} className="chart-mark"/>:<circle cx={x(p.nx)} cy={y(p.y)} r={scatter?4:points.length<100?3:1.5} className="chart-mark"/>}</g>)}
  </svg>{analysis && (result.spec.correlation || result.spec.trend_line) && <div className="plot-analysis" role="status">{analysis.pearson_r !== null && <strong>Pearson r = {analysis.pearson_r.toFixed(3)} · R² = {analysis.r_squared!.toFixed(3)}</strong>}{trend && <span>Dashed amber line: linear regression · fitted change {(trend.y_end-trend.y_start)>=0?'+':''}{(trend.y_end-trend.y_start).toFixed(2)} {result.unit}{!result.spec.correlation ? ` · R² = ${trend.r_squared.toFixed(3)}` : ''}</span>}<span>{analysis.sample_count} {scatter ? 'paired observations' : 'observations; X is calendar time'}. {analysis.reason ?? 'Association does not establish causation; conditions and outliers can affect the result.'}</span></div>}</div>;
}

function download(result: ChartResult) {
  const rows = ['date,x,y,x_unit,y_unit,source', ...result.points.map(p => [p.date,p.x,p.y,result.x_unit,result.unit,p.source].map(v=>`"${String(v).replaceAll('"','""')}"`).join(','))];
  const url=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'})); const a=document.createElement('a'); a.href=url; a.download='chart-data.csv'; a.click(); URL.revokeObjectURL(url);
}

export function ChartCard({ spec, initial, profile, refresh, actions }: {spec: ChartSpec; initial?: ChartResult; profile?: Profile | null; refresh?: string | number; actions?: React.ReactNode}) {
  const [result,setResult]=useState<ChartResult | null>(initial ?? null);
  const [error,setError]=useState(''); const [expanded,setExpanded]=useState(false);
  useEffect(() => {const controller=new AbortController();setError(''); if(initial){setResult(initial);return;} setResult(null); api<ChartResult>('/api/charts/query',{...jsonRequest({spec:{...spec,timezone}}),signal:controller.signal}).then(setResult).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[JSON.stringify(spec),initial,refresh]);
  return <article className={`graph-card ${spec.size==='full'||expanded?'graph-card--full':''}`}>
    <div className="graph-heading"><div><h3>{spec.title || label(spec.metric)}</h3><p>{spec.gps_reference_id ? 'GPS-matched rides · ' : ''}{spec.start||'All history'} → {spec.end||'Latest'}{spec.sport && spec.sport!=='all'?` · ${spec.sport}`:''}</p></div><button type="button" onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>{expanded?'Collapse':'Expand'}</button></div>
    {error?<p role="alert">{error}</p>:result?<><Plot result={result} profile={profile} height={expanded?520:365}/><div className="graph-meta">{result.count.toLocaleString()} observations · {result.sources.join(', ').replaceAll('_',' ')}{result.excluded>0?` · ${result.excluded} missing values`:''}{result.unpaired>0?` · ${result.unpaired} unpaired`:''}</div><details className="graph-notes"><summary>Data and pairing details</summary>{result.notes.map(note=><p key={note}>{note}</p>)}</details></>:<div className="graph-empty" role="status">Loading recorded data…</div>}
    <div className="graph-actions">{spec.metric === 'weight' && <button className="primary-button" type="button" onClick={() => { const form = document.getElementById('weight-entry'); if (!form?.getClientRects().length) { window.location.hash = 'profile'; return; } form.scrollIntoView({ behavior: 'instant', block: 'start' }); form?.querySelector<HTMLInputElement>('input[type="number"]')?.focus({ preventScroll: true }); }}>＋ Add weight</button>}{actions}{result && <button type="button" onClick={()=>download(result)}>Export CSV</button>}</div>
  </article>;
}

export default function GraphCanvas({ mode='dashboard', profile, refresh=0 }: { mode?: 'dashboard'|'health'; profile?: Profile | null; refresh?: string | number }) {
  const [catalog,setCatalog]=useState<Catalog|null>(null),[widgets,setWidgets]=useState<ChartSpec[]>([]),[ready,setReady]=useState(false);
  const [error,setError]=useState(''),[saving,setSaving]=useState(false),[editing,setEditing]=useState<ChartSpec|null>(null);
  const [dragId,setDragId]=useState<string|null>(null),[notice,setNotice]=useState('');
  useEffect(()=>{let active=true; Promise.all([api<Catalog>('/api/charts/catalog'),api<{widgets:ChartSpec[]|null}>('/api/dashboard/widgets')]).then(([c,w])=>{if(!active)return;setCatalog(c);setWidgets(w.widgets??defaults);setReady(true);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[refresh]);
  const save=async(next:ChartSpec[])=>{setSaving(true);setError('');try{const r=await api<{widgets:ChartSpec[]}>('/api/dashboard/widgets',jsonRequest({widgets:next},'PUT'));setWidgets(r.widgets);setNotice('Dashboard saved.');return true;}catch(e){setError(e instanceof Error?e.message:'Could not save layout');return false;}finally{setSaving(false);}};
  useEffect(()=>{if(mode!=='dashboard')return;const pinned=(event:Event)=>{const spec=(event as CustomEvent<ChartSpec>).detail;setEditing({...spec,id:crypto.randomUUID()});};window.addEventListener('pin-chart',pinned);return()=>window.removeEventListener('pin-chart',pinned);},[mode]);
  const items = catalog ? [...catalog.metrics,...catalog.activity_fields] : [];
  const visible=mode==='health'?[{id:'health-vo2',metric:'vo2_cycling',kind:'dial',title:'VO₂ max · cycling'} as ChartSpec,{id:'health-running',metric:'vo2_running',kind:'dial',title:'VO₂ max · running'} as ChartSpec,{id:'health-weight',metric:'weight',kind:'line',title:'Weight history',size:'full'} as ChartSpec]:widgets;
  const move=(id:string,target:number)=>{const next=[...widgets];const index=next.findIndex(w=>w.id===id);if(index<0)return;const [item]=next.splice(index,1);next.splice(target,0,item);void save(next);};
  return <section className="graph-canvas" aria-label={mode==='health'?'Health graphs':'Customizable graph dashboard'}>
    <div className="section-heading"><div><p>{mode==='health'?'Health history':'Modular canvas'}</p><h2>{mode==='health'?'Your health, over time':'Your graphs. Your layout.'}</h2><span className="graph-meta">{mode==='health'?'Recorded Garmin measurements and manual weight entries.':'Add or replace any graph. Drag to rearrange, or use the move buttons.'}</span></div>{mode==='dashboard' && <button className="primary-button" type="button" disabled={!ready||saving} onClick={()=>setEditing({id:crypto.randomUUID(),metric:items.find(i=>i.id==='weight')?.id??items[0]?.id??'vo2_cycling',kind:'line',size:'half'})}>＋ Add graph</button>}</div>
    {error&&<p role="alert">{error}</p>}<p className="canvas-status" role="status">{saving?'Saving layout…':notice}</p>
    {editing&&<form className="graph-builder" onSubmit={e=>{e.preventDefault();const index=widgets.findIndex(w=>w.id===editing.id);const next=[...widgets];if(index<0)next.push(editing);else next[index]=editing;void save(next).then(saved=>{if(saved)setEditing(null);});}}>
      <div className="graph-heading"><h3>{widgets.some(w=>w.id===editing.id)?'Replace or configure graph':'Add a graph'}</h3><button type="button" onClick={()=>setEditing(null)}>Cancel</button></div>
      {editing.gps_reference_id && <p className="graph-meta">This graph uses GPS-matched rides for the selected reference. <button type="button" onClick={() => { const {gps_reference_id, ...unscoped} = editing; void gps_reference_id; setEditing(unscoped); }}>Use all activities instead</button></p>}
      <div className="builder-fields"><label>Title<input maxLength={100} value={editing.title??''} placeholder="Name this graph" onChange={e=>setEditing({...editing,title:e.target.value})}/></label><label>Chart type<select value={editing.kind} onChange={e=>{const kind=e.target.value as ChartSpec['kind'];setEditing({...editing,...(kind==='dial'?{trend_line:false,correlation:false,reference_lines:[]}:{}),kind,x_metric:kind==='scatter'?(editing.metric.startsWith('activity_')?'activity_power':'resting_heart_rate'):undefined});}}><option value="line">Line history</option><option value="bar">Bars</option><option value="scatter">Scatter comparison</option><option value="dial">Latest value / dial</option></select></label><label>{editing.kind==='scatter'?'Y metric':'Metric'}<select value={editing.metric} onChange={e=>setEditing({...editing,metric:e.target.value,x_metric:editing.kind==='scatter'?e.target.value:undefined})}>{items.map(m=><option key={m.id} value={m.id}>{m.label} ({m.unit})</option>)}</select></label>{editing.kind==='scatter'&&<label>X metric<select required value={editing.x_metric??''} onChange={e=>setEditing({...editing,x_metric:e.target.value})}>{items.filter(m=>m.id.startsWith('activity_')===editing.metric.startsWith('activity_')).map(m=><option key={m.id} value={m.id}>{m.label} ({m.unit})</option>)}</select></label>}<label>From<input type="date" value={editing.start??''} max={editing.end||undefined} onChange={e=>setEditing({...editing,start:e.target.value})}/></label><label>To<input type="date" value={editing.end??''} min={editing.start||undefined} onChange={e=>setEditing({...editing,end:e.target.value})}/></label><label>Activity filter<select value={editing.sport??'all'} onChange={e=>setEditing({...editing,sport:e.target.value})}><option value="all">All activities</option><option value="cycling">Cycling</option><option value="running">Running</option><option value="indoor_cycling">Indoor cycling</option></select></label><label>Width<select value={editing.size??'half'} onChange={e=>setEditing({...editing,size:e.target.value as 'half'|'full'})}><option value="half">Half canvas</option><option value="full">Full canvas</option></select></label></div><button className="primary-button" disabled={saving} type="submit">{saving?'Saving…':'Save graph'}</button>
    </form>}
    <div className="graph-grid">{visible.map((spec,index)=><div className={`graph-slot ${spec.size==='full'?'graph-slot--full':''}`} key={spec.id} draggable={mode==='dashboard'&&!saving} onDragStart={()=>setDragId(spec.id!)} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(dragId&&!saving)move(dragId,index);setDragId(null);}}><ChartCard spec={spec} profile={profile} refresh={refresh} actions={mode==='dashboard'?<>{spec.kind!=='dial' && <button type="button" disabled={saving} aria-pressed={!!spec.trend_line} onClick={() => void save(widgets.map(w => w.id===spec.id ? {...w,trend_line:!w.trend_line} : w))}>{spec.trend_line?'Remove trend line':'Add trend line'}</button>}<button type="button" disabled={saving} onClick={()=>setEditing({...spec})}>Replace / edit</button><button type="button" disabled={saving||index===0} aria-label={`Move ${spec.title??spec.metric} up`} onClick={()=>move(spec.id!,index-1)}>↑</button><button type="button" disabled={saving||index===widgets.length-1} aria-label={`Move ${spec.title??spec.metric} down`} onClick={()=>move(spec.id!,index+1)}>↓</button><button type="button" disabled={saving} onClick={()=>void save([...widgets,{...spec,id:crypto.randomUUID()}])}>Duplicate</button><button type="button" disabled={saving} onClick={()=>void save(widgets.filter(w=>w.id!==spec.id))}>Remove</button></>:undefined}/></div>)}</div>
    {ready&&mode==='dashboard'&&!widgets.length&&<p className="graph-empty">Your canvas is empty. Add any graph to get started.</p>}
  </section>;
}

export function AssistantPlots({ plots, profile }: {plots:ChartResult[];profile?:Profile|null}) {
  const [page,setPage]=useState(0),[notice,setNotice]=useState('');
  const total=Math.ceil(plots.length/4);
  useEffect(()=>setPage(Math.max(0,total-1)),[plots.length]);
  if(!plots.length)return null;
  return <section id="assistant-plots" className="assistant-plots" aria-label="Assistant plot workspace"><div className="section-heading"><div><p>Assistant plot workspace</p><h2>Explore the evidence</h2></div>{total>1&&<div><button disabled={!page} onClick={()=>setPage(page-1)}>Previous plots</button><span> {page+1} / {total} </span><button disabled={page>=total-1} onClick={()=>setPage(page+1)}>Next plots</button></div>}</div><div className="graph-grid">{plots.slice(page*4,page*4+4).map((result,i)=><ChartCard key={`${page}-${i}`} spec={result.spec} initial={result} profile={profile} actions={<button type="button" onClick={()=>{window.dispatchEvent(new CustomEvent('pin-chart',{detail:result.spec}));window.location.hash='dashboard';setNotice('Review the graph in the dashboard builder and save it.');}}>Pin to dashboard</button>}/>)}</div><p role="status">{notice}</p></section>;
}

export function WeightEntry({ onSaved, unit='kg' }: {onSaved:()=>void;unit?:'kg'|'lb'}) {
  const [day,setDay]=useState(localDate()),[value,setValue]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  return <form id="weight-entry" className="weight-entry" onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api('/api/weight',jsonRequest({date:day,value:Number(value),unit}));setValue('');setMessage('Weight measurement saved.');onSaved();}catch(error){setMessage(error instanceof Error?error.message:'Could not save weight');}finally{setBusy(false);}}}><h3>Log a weight measurement</h3><p>Dated entries appear alongside Garmin measurements in your graphs.</p><div className="builder-fields"><label>Date<input type="date" required value={day} max={localDate()} onChange={e=>setDay(e.target.value)}/></label><label>Weight ({unit})<input type="number" required step="0.1" min="1" value={value} onChange={e=>setValue(e.target.value)}/></label></div><button className="primary-button" disabled={busy}>{busy?'Saving…':'Save measurement'}</button><p role="status">{message}</p></form>;
}
