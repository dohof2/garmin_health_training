import {useEffect,useState} from 'react';
import {api,Plot,type ChartResult,type ChartSpec} from './GraphCanvas';
type Metric={label:string;value:number;unit:string;source:string};
type Component={label:string;value:number|null;unit:string;qualifier:string|null};
type Night={date:string;latest_date:string|null;available_dates:string[];score:number|null;qualifier:string|null;overnight_hrv?:number|null;sleep_start:string|null;sleep_end:string|null;metrics:Metric[];components:Component[];plot:ChartResult};
const timezone=Intl.DateTimeFormat().resolvedOptions().timeZone;
const localToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const format=(value:number,unit:string)=>unit==='s'?`${Math.floor(Math.round(value/60)/60)}h ${Math.round(value/60)%60}m`:`${value.toLocaleString(undefined,{maximumFractionDigits:1})} ${unit}`;
function presentation(qualifier:string|null){const label=qualifier?.replaceAll('_',' ').toLowerCase();if(!label)return {label:'Rating not recorded',kind:'unrated'};return {label:label.charAt(0).toUpperCase()+label.slice(1),kind:label.includes('excellent')?'excellent':label.includes('good')?'good':label.includes('fair')?'fair':label.includes('poor')?'poor':'unrated'};}
export default function SleepCard({spec,actions,refresh}:{spec:ChartSpec;actions?:React.ReactNode;refresh?:string|number}){
  const [today,setToday]=useState(localToday),[day,setDay]=useState<string|null>(null),[night,setNight]=useState<Night|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  useEffect(()=>{const timer=window.setInterval(()=>setToday(localToday()),60000);return()=>window.clearInterval(timer);},[]);
  const selected=day??today;
  useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');setNight(null);api<Night>(`/api/health/sleep?day=${encodeURIComponent(selected)}&timezone=${encodeURIComponent(timezone)}`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setNight(value);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[selected,refresh]);
  const dates=[...(night?.available_dates??[])].sort().reverse(),older=dates.find(d=>d<selected),newer=dates.filter(d=>d>selected&&d<=today).at(-1);
  const clock=(value:string)=>new Date(value).toLocaleTimeString([], {timeZone:timezone,hour:'2-digit',minute:'2-digit'});
  const rating=presentation(night?.qualifier??null),hrv=night?.overnight_hrv??night?.metrics.find(m=>/hrv/i.test(m.label)&&m.unit==='ms')?.value??null;
  return <article className="graph-card sleep-card" aria-label={spec.title||'Sleep and overnight HRV'}>
    <div className="graph-heading"><div><h3>{selected===today?"Last night's score":'Sleep score'}</h3><p>Night ending {selected} · {timezone}</p></div></div>
    {night&&!loading&&<div className={`sleep-score-latest sleep-rating--${rating.kind}`}><strong>{night.score??'—'}<span> / 100</span></strong><b>{night.score==null?'Score not recorded':rating.label}</b></div>}
    <div className="sleep-date-controls"><button type="button" aria-label="Previous sleep date" disabled={loading||!older} onClick={()=>setDay(older!)}>←</button><label>Sleep date<input type="date" value={selected} max={today} disabled={loading} onChange={e=>{if(e.target.value)setDay(e.target.value===today?null:e.target.value);}}/></label><button type="button" aria-label="Next sleep date" disabled={loading||!newer} onClick={()=>setDay(newer!)}>→</button><button type="button" disabled={loading||selected===today} onClick={()=>setDay(null)}>Last night</button></div>
    {error?<p role="alert">{error}</p>:loading?<p role="status">Loading recorded sleep…</p>:night&&<>
      <p className="graph-meta">{night.sleep_start&&night.sleep_end?`${clock(night.sleep_start)} → ${clock(night.sleep_end)} · ${timezone}`:'Sleep timing not recorded for this date.'}</p>
      <section className="sleep-night-plot" aria-label={`Sleep and HRV for night ending ${selected}`}><div className="sleep-plot-canvas">{night.plot.points.length?<Plot result={{...night.plot,spec:{...night.plot.spec,timezone}}} height={260}/>:<div className="graph-empty">No overnight HRV trace recorded for this night.</div>}<div className="sleep-hrv-annotation">Overnight HRV <strong>{hrv==null?'Not recorded':`${hrv.toLocaleString(undefined,{maximumFractionDigits:1})} ms`}</strong></div></div>{night.score==null&&<p className="graph-meta">{selected===today?"Last night's score is not available.":'Sleep score is not available for this night.'}</p>}</section>
      <details className="sleep-score-details"><summary>Sleep score metrics</summary><div className="sleep-metric-list">{night.metrics.map((m,i)=><div key={m.label+i}><span>{m.label}</span><strong>{format(m.value,m.unit)}</strong></div>)}</div>{night.components.length>0&&<><p>Score components</p><div className="sleep-metric-list">{night.components.map(c=><div key={c.label}><span>{c.label}</span><strong>{c.value!==null?`${c.value}${c.unit} · `:''}{c.qualifier?.replaceAll('_',' ').toLowerCase()??'No rating recorded'}</strong></div>)}</div></>}{!night.metrics.length&&!night.components.length&&<p>No sleep metrics recorded for this date.</p>}</details>
    </>}<div className="graph-actions">{actions}</div>
  </article>;
}
