import {useEffect,useState} from 'react';
import StatusDial, {type DialBand} from './StatusDial';

type Recovery={remaining_hours:number;session_remaining_hours:number;load_settling_hours:number|null;coverage_complete:boolean;source:string;ratio:number|null;ratio_threshold:number;stable_baseline:boolean;range_hours:{low:number;high:number}};
const bands:DialBand[]=[{label:'0–12 h',color:'#39a582',end:12/72},{label:'12–24 h',color:'#468bd5',end:24/72},{label:'24–48 h',color:'#e79938',end:48/72},{label:'48+ h',color:'#dc545c',end:1}];

export default function RecoveryDial({timezone,refreshToken}:{timezone:string;refreshToken:string}) {
  const [tick,setTick]=useState(0),[recovery,setRecovery]=useState<Recovery|null>(null),[error,setError]=useState(''),[outdated,setOutdated]=useState(false);
  useEffect(()=>{const timer=window.setInterval(()=>{if(document.visibilityState==='visible')setTick(v=>v+1);},60000);return()=>window.clearInterval(timer);},[]);
  useEffect(()=>{
    const controller=new AbortController();setError('');
    void fetch(`/api/readiness?days=1&timezone=${encodeURIComponent(timezone)}`,{signal:controller.signal,cache:'no-store'})
      .then(async response=>{if(!response.ok)throw new Error('Recovery estimate could not be loaded.');return response.json() as Promise<{latest:{formula_version:string;inputs:{recovery?:Recovery}}}>;})
      .then(data=>{if(!controller.signal.aborted){setRecovery(data.latest.inputs.recovery??null);setOutdated(data.latest.formula_version!=='readiness-v5');}})
      .catch(error=>{if(!controller.signal.aborted){setRecovery(null);setError(error.message);}});
    return()=>controller.abort();
  },[timezone,refreshToken,tick]);
  const complete=recovery?.coverage_complete===true;
  if(outdated)return <section className="graph-card health-recovery-card"><h3>Recovery time</h3><p>Quit and reopen the app to enable the new recovery estimate.</p></section>;
  return <section className="graph-card health-recovery-card" aria-label="Recovery time estimate"><div className="graph-heading"><div><h3>Recovery time</h3><p>App estimate · updates every minute</p></div></div>
    <StatusDial value={recovery?`${complete?'':'≥'}${Math.ceil(recovery.remaining_hours)}`:'—'} unit="hours remaining" bands={bands}
      position={complete&&recovery?Math.min(1,recovery.remaining_hours/72):null}
      interpretation={complete?'Before another hard session':recovery?'Incomplete activity evidence: shown demand is a lower bound.':'Waiting for recovery evidence.'}/>
    {error&&<p role="alert">{error}</p>}
    {recovery&&<details className="graph-notes"><summary>What contributes?</summary><p>{recovery.source}. Counts down with actual elapsed time; completed sleep can adjust the estimate.</p>
      {complete&&<p>Heuristic range: {recovery.range_hours.low}–{recovery.range_hours.high} hours. This is not a calibrated confidence interval.</p>}
      <p>Individual sessions: {recovery.session_remaining_hours.toFixed(1)} hours. Load settling: {recovery.load_settling_hours==null?'unavailable':`${recovery.load_settling_hours.toFixed(1)} hours`}. The longer window applies.</p>
        <p>Load ratio: {recovery.stable_baseline?recovery.ratio?.toFixed(2)??'unavailable':'unavailable with a small baseline'}; soft threshold {recovery.ratio_threshold}. {!recovery.stable_baseline?' Individual session demand is used instead.':''}</p>
        <p>Experimental estimate, not Garmin's measured recovery countdown or proof of full recovery.</p></details>}
  </section>;
}
