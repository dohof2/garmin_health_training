import {useEffect,useState} from 'react';
import {api,Plot,type ChartResult} from './GraphCanvas';
import JournalDialog from './JournalDialog';

type Night={date:string;score:number|null;qualifier:string|null;overnight_hrv:number|null;sleep_start:string|null;sleep_end:string|null;metrics:{label:string;value:number;unit:string}[];plot:ChartResult};
const duration=(seconds:number)=>{const minutes=Math.round(seconds/60);return `${Math.floor(minutes/60)}h ${minutes%60}m`;};
const stages=[['Deep sleep','deep'],['Light sleep','light'],['REM sleep','rem'],['Awake','awake']] as const;
export default function DashboardNight({view,today,timezone,onClose}:{view:'hrv'|'sleep'|null;today:string;timezone:string;onClose:()=>void}) {
  const [night,setNight]=useState<Night|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  useEffect(()=>{
    if(!view)return;
    const controller=new AbortController();setNight(null);setError('');
    void api<Night>(`/api/health/sleep?day=${today}&timezone=${encodeURIComponent(timezone)}`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setNight(value);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[view,today,timezone,retry]);
  const clock=(value:string)=>new Date(value).toLocaleTimeString(undefined,{timeZone:timezone,hour:'2-digit',minute:'2-digit'});
  const recorded=stages.flatMap(([label,colour])=>{const metric=night?.metrics.find(m=>m.label===label&&m.unit==='s');return metric?[{...metric,colour}]:[];});
  const total=recorded.reduce((sum,m)=>sum+m.value,0);
  return <JournalDialog open={view!==null} title={view==='hrv'?"Last night’s HRV":"Last night’s sleep"} onClose={onClose}>
    <p className="graph-meta">Night ending {today} · {timezone}</p>
    {error?<p role="alert">{error} <button type="button" onClick={()=>setRetry(v=>v+1)}>Retry night</button></p>:!night?<p role="status">Loading recorded night…</p>:<>
      <p className="journal-night-window">{night.sleep_start&&night.sleep_end?`${clock(night.sleep_start)} → ${clock(night.sleep_end)}`:'Sleep window not recorded'}</p>
      {view==='hrv'?<><p className="journal-detail-value">{night.overnight_hrv===null?'Unavailable':`${night.overnight_hrv.toLocaleString(undefined,{maximumFractionDigits:1})} ms`}<small>Overnight average</small></p>{night.plot.points.length?<Plot result={{...night.plot,spec:{...night.plot.spec,timezone}}} height={280}/>:<p>No overnight HRV samples were recorded for this night.</p>}</>:<>
        <div className="journal-sleep-score"><strong>{night.score??'—'}<small> / 100</small></strong><span>{night.qualifier?.replaceAll('_',' ')??'Score rating not recorded'}</span></div>
        {total>0&&<div className="journal-sleep-stages" aria-label="Proportion of recorded sleep stages">{recorded.map(m=><span key={m.label} className={`sleep-stage--${m.colour}`} style={{flexGrow:m.value}} title={`${m.label}: ${duration(m.value)}`}/>)}</div>}
        <dl className="journal-night-metrics">{stages.map(([label,colour])=>{const metric=recorded.find(m=>m.label===label);return <div key={label}><dt><i className={`sleep-stage--${colour}`}/>{label}</dt><dd>{metric?duration(metric.value):'Not recorded'}</dd></div>;})}{night.metrics.filter(m=>m.label==='Total sleep').map(m=><div key={m.label}><dt>Total sleep</dt><dd>{duration(m.value)}</dd></div>)}</dl>
        <p className="graph-meta">Recorded stage totals for this night.</p>
      </>}
    </>}
  </JournalDialog>;
}
