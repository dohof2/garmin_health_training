import {useEffect,useState} from 'react';
import {requestJson} from './request';
import JournalDialog from './JournalDialog';
import {ArrowRight,SportIcon} from './JournalIcons';
import {allRecentActivities,dailyRidingSummary,sevenDayRange,summarizeActivities,ridingTime,type RecordedActivity} from './recentActivitySummary';

export default function RecentTrainingSummary({today,timezone,active,refresh}:{today:string;timezone:string;active:boolean;refresh:string}) {
  const range=sevenDayRange(today),period=`${range.start}:${range.end}:${timezone}`;
  const [data,setData]=useState<{period:string;records:RecordedActivity[];summary:ReturnType<typeof summarizeActivities>}|null>(null);
  const [view,setView]=useState<'time'|'distance'|null>(null);
  const [error,setError]=useState(''),[revision,setRevision]=useState(0),[loading,setLoading]=useState(false);
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();setLoading(true);setError('');
    const query=new URLSearchParams({start_date:range.start,end_date:range.end,timezone,limit:'100'});
    void allRecentActivities(offset=>requestJson<RecordedActivity[]>(`/api/activities?${query}&offset=${offset}`,{signal:controller.signal}))
      .then(records=>{if(!controller.signal.aborted)setData({period,records,summary:summarizeActivities(records,range)});})
      .catch(error=>{if(!controller.signal.aborted)setError(error instanceof Error?error.message:'Could not load the last seven days.');})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[active,period,refresh,revision]);
  const summary=data?.period===period?data.summary:null;
  const date=(day:string)=>new Date(`${day}T12:00:00Z`).toLocaleDateString(undefined,{timeZone:'UTC',month:'short',day:'numeric'});
  const daily=data?.period===period?dailyRidingSummary(data.records,range):[];
  const values=daily.map(d=>view==='time'?d.ridingSeconds===null?null:d.ridingSeconds/3600:d.ridingKm);
  const maximum=Math.max(0,...values.filter((v):v is number=>v!==null));
  return <aside className="journal-availability journal-recent-summary" aria-labelledby="journal-recent-title">
    <h2 id="journal-recent-title">Last 7 days</h2><p>{date(range.start)}–{date(range.end)} · including today</p>
    {error?<p role="alert">{error} <button type="button" onClick={()=>setRevision(v=>v+1)}>Retry summary</button></p>:!summary?<p role="status">Loading your recent activities…</p>:<>
      <dl className="journal-seven-metrics">
        <div><dt><SportIcon sport="strength"/>Strength workouts</dt><dd>{summary.strength}</dd></div>
        <div><dt><SportIcon sport="cycling"/>Bike activities</dt><dd>{summary.rides}</dd></div>
        <div><dt>Time ridden</dt><dd><button type="button" className="journal-metric-action" aria-haspopup="dialog" onClick={()=>setView('time')}>{ridingTime(summary.ridingSeconds)}<small>Daily time ↗</small></button></dd>{summary.missingTime>0&&<small>{summary.missingTime} ride{summary.missingTime===1?'':'s'} missing duration{summary.ridingSeconds!==null?' · partial total':''}</small>}</div>
        <div><dt>Distance ridden</dt><dd><button type="button" className="journal-metric-action" aria-haspopup="dialog" onClick={()=>setView('distance')}>{summary.ridingKm===null?'—':<>{summary.ridingKm.toLocaleString(undefined,{maximumFractionDigits:1})}<span> km</span></>}<small>Daily distance ↗</small></button></dd>{summary.missingDistance>0&&<small>{summary.missingDistance} ride{summary.missingDistance===1?'':'s'} missing distance{summary.ridingKm!==null?' · partial total':''}</small>}</div>
      </dl>
      <p className="settings-hint">Recorded activities · indoor and virtual rides included.<br/>Dates use {timezone}.</p>
      {loading&&<p className="settings-hint" role="status">Refreshing recent activities…</p>}
    </>}
    <JournalDialog open={view!==null} title={view==='time'?'Time ridden · last 7 days':'Distance ridden · last 7 days'} onClose={()=>setView(null)}>
      <p className="graph-meta">{date(range.start)}–{date(range.end)} · {timezone}</p>
      <div className="journal-chart-switch" aria-label="Riding metric"><button type="button" aria-pressed={view==='time'} onClick={()=>setView('time')}>Time</button><button type="button" aria-pressed={view==='distance'} onClick={()=>setView('distance')}>Kilometres</button></div>
      <p className="graph-meta">{view==='time'?'Hours ridden':'Kilometres ridden'} per day</p>
      <div className="journal-daily-bars" role="img" aria-label={`Daily riding ${view==='time'?'time':'distance'}; exact values listed below`}>{daily.map((day,index)=><div className="journal-bar-column" key={day.date}><span className="journal-bar-value">{values[index]===null?'—':values[index]!.toLocaleString(undefined,{maximumFractionDigits:1})}</span><div className="journal-bar-track"><span style={{height:values[index]===null?'0%':`${maximum?values[index]!/maximum*100:0}%`}}/></div><small>{new Date(`${day.date}T12:00:00Z`).toLocaleDateString(undefined,{timeZone:'UTC',weekday:'short'})}</small><small>{date(day.date)}</small></div>)}</div>
      <table className="journal-day-totals"><caption>Recorded rides by day</caption><thead><tr><th>Day</th><th>Time</th><th>Distance</th></tr></thead><tbody>{daily.map(day=><tr key={day.date}><th scope="row">{date(day.date)}</th><td>{ridingTime(day.ridingSeconds)}{day.missingTime>0?' · missing duration':''}</td><td>{day.ridingKm===null?'—':`${day.ridingKm.toLocaleString(undefined,{maximumFractionDigits:1})} km`}{day.missingDistance>0?' · missing distance':''}</td></tr>)}</tbody></table><p className="graph-meta">Days without rides are zero. Missing recorded measurements are marked; available values may be partial totals.</p>
    </JournalDialog>
    <a href="#activities" className="journal-settings-link">Activity history <ArrowRight size={16}/></a>
  </aside>;
}
