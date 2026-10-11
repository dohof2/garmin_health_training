import { useEffect, useState } from 'react';
import { api } from './GraphCanvas';

type Commitment = {date:string;title:string;sport:string;start_time:string|null;duration_minutes:number|null;effort:string};
export type CoachingBrief = {goal:string|null;goal_sport:string;horizon_weeks:number;target_date:string|null;event_name:string;ftp_watts:number|null;fixed_events:Commitment[]};
type Preview = {status:string;brief:CoachingBrief;week_start:string;timezone:string;questions:string[];warnings:string[];recognized?:string[];fingerprint:string;replace_plan_id:string|null;replaces_session_count:number;
  roadmap:{week:number;starts_on:string;phase:string;focus:string}[];sessions:{title:string;sport:string;scheduled_for:string;definition:{duration_minutes:number;effort_target:{description:string};rationale:string[]}}[];protected_days:{date:string;reason:string}[];weekly_minutes:Record<string,number>;advisory:string};
const empty:CoachingBrief={goal:null,goal_sport:'cycling',horizon_weeks:12,target_date:null,event_name:'',ftp_watts:null,fixed_events:[]};
const request=(body:unknown,method='POST')=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export default function TrainingCoachPanel({timezone,week,onWeekChange,onDraftSaved,plans}: {timezone:string;week:string;onWeekChange:(week:string)=>void;onDraftSaved:()=>void;plans:{id:string;name:string;status:string}[]}) {
  const [brief,setBrief]=useState(empty),[revision,setRevision]=useState(0),[prompt,setPrompt]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[replace,setReplace]=useState('');
  useEffect(()=>{let active=true;api<{brief:CoachingBrief;revision:number}>('/api/training/coach').then(r=>{if(active){setBrief(r.brief);setRevision(r.revision);}}).catch(e=>{if(active)setMessage(e.message);});return()=>{active=false;};},[]);
  useEffect(()=>{const receive=(event:Event)=>{const data=(event as CustomEvent<Preview>).detail;setBrief(data.brief);setPreview(data);onWeekChange(data.week_start);setReplace(data.replace_plan_id??'');setMessage('Assistant proposal loaded. Review the brief and weekly sessions.');};window.addEventListener('training-coach-proposal',receive);return()=>window.removeEventListener('training-coach-proposal',receive);},[onWeekChange]);
  const change=(next:CoachingBrief)=>{setBrief(next);setPreview(null);};
  const run=async(action:()=>Promise<void>)=>{setBusy(true);setMessage('');try{await action();}catch(e){setMessage(e instanceof Error?e.message:'Coaching request failed');}finally{setBusy(false);}};
  const updateEvent=(index:number,patch:Partial<Commitment>)=>change({...brief,fixed_events:brief.fixed_events.map((e,i)=>i===index?{...e,...patch}:e)});
  return <section className="coach-panel" aria-label="Training coach">
    <div className="section-heading"><div><p>Plan with your assistant</p><h2>A goal, a direction, a week that fits</h2></div></div>
    <p>Tell the coach what you want to improve and which sessions are fixed. Preview the surrounding week and a longer-term direction, then create a draft to review.</p>
    <form onSubmit={e=>{e.preventDefault();void run(async()=>{const p=await api<Preview>('/api/training/coach/preview',request({brief,week_start:week,timezone,message:prompt||null,replace_plan_id:replace||null}));setBrief(p.brief);setPreview(p);setPrompt('');});}}>
      <label>Tell your training coach<textarea maxLength={4000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="I want to increase FTP. On Wednesday I have a hard 3-hour trip starting at 08:00; adjust the rest of the week around it."/></label>
      <p className="graph-meta">Named weekdays refer to the week starting {week}. Missing trip details become questions; you can fill them below.</p>
      <div className="builder-fields">
        <label>Primary goal<select value={brief.goal??''} onChange={e=>change({...brief,goal:e.target.value||null})}><option value="">Choose a goal</option><option value="ftp">Increase FTP</option><option value="endurance">Build endurance</option><option value="race">Prepare for a race</option><option value="general">Stay in shape</option></select></label>
        {['race','endurance'].includes(brief.goal??'')&&<label>Goal sport<select value={brief.goal_sport} onChange={e=>change({...brief,goal_sport:e.target.value})}><option value="cycling">Cycling</option><option value="running">Running</option></select></label>}
        <label>Planning horizon (weeks)<input type="number" min="4" max="24" value={brief.horizon_weeks} onChange={e=>change({...brief,horizon_weeks:Number(e.target.value)})}/></label>
        <label>Coach week starts Monday<input type="date" required value={week} onChange={e=>{onWeekChange(e.target.value);setPreview(null);}}/></label>
        <label>Confirmed cycling FTP (W, optional)<input type="number" min="40" max="700" value={brief.ftp_watts??''} onChange={e=>change({...brief,ftp_watts:e.target.value?Number(e.target.value):null})}/></label>
        {brief.goal==='race'&&<><label>Race date<input type="date" value={brief.target_date??''} onChange={e=>change({...brief,target_date:e.target.value||null})}/></label><label>Event and demands<input maxLength={160} placeholder="e.g. 100 km hilly cycling race" value={brief.event_name} onChange={e=>change({...brief,event_name:e.target.value})}/></label></>}
        <label>Adjust an existing week<select value={replace} onChange={e=>{setReplace(e.target.value);setPreview(null);}}><option value="">Create a new draft; keep existing sessions</option>{plans.filter(p=>['draft','active'].includes(p.status)).map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
      </div>
      <div className="coach-commitments"><h3>Fixed trips and sessions</h3>{brief.fixed_events.map((event,i)=><fieldset key={i}><legend>Fixed commitment {i+1}</legend><div className="builder-fields">
        <label>Commitment title<input maxLength={160} required value={event.title} onChange={e=>updateEvent(i,{title:e.target.value})}/></label><label>Commitment date<input type="date" required value={event.date} onChange={e=>updateEvent(i,{date:e.target.value})}/></label>
        <label>Commitment sport<select value={event.sport} onChange={e=>updateEvent(i,{sport:e.target.value})}>{['cycling','running','strength'].map(s=><option key={s}>{s}</option>)}</select></label>
        <label>Commitment start time<input type="time" value={event.start_time??''} onChange={e=>updateEvent(i,{start_time:e.target.value||null})}/></label>
        <label>Expected minutes<input type="number" min="15" max="720" value={event.duration_minutes??''} onChange={e=>updateEvent(i,{duration_minutes:e.target.value?Number(e.target.value):null})}/></label>
        <label>Expected effort<select value={event.effort} onChange={e=>updateEvent(i,{effort:e.target.value})}><option value="unknown">Choose effort</option><option value="easy">Easy</option><option value="moderate">Moderate</option><option value="hard">Hard</option></select></label>
      </div><button type="button" onClick={()=>change({...brief,fixed_events:brief.fixed_events.filter((_,index)=>index!==i)})}>Remove commitment</button></fieldset>)}
      <button type="button" disabled={busy||brief.fixed_events.length>=20} onClick={()=>change({...brief,fixed_events:[...brief.fixed_events,{date:week,title:'Fixed trip',sport:'cycling',start_time:null,duration_minutes:null,effort:'unknown'}]})}>Add fixed trip or session</button></div>
      <div className="graph-actions"><button className="primary-button" disabled={busy} type="submit">{busy?'Working…':'Ask coach / preview plan'}</button><button type="button" disabled={busy} onClick={()=>void run(async()=>{const r=await api<{brief:CoachingBrief;revision:number}>('/api/training/coach',request({brief,expected_revision:revision},'PUT'));setBrief(r.brief);setRevision(r.revision);setMessage('Coaching brief saved for future conversations.');})}>Save coaching brief</button></div>
    </form>
    {message&&<p role="status">{message}</p>}
    {preview&&<div className="coach-preview">
      {preview.recognized?.map(line=><p key={line}>{line}</p>)}
      {preview.questions.length>0&&<div className="training-notice"><h3>Details needed</h3><ul>{preview.questions.map(q=><li key={q}>{q}</li>)}</ul></div>}
      {preview.warnings.map(w=><p key={w}>{w}</p>)}
      <h3>Your week · {preview.week_start}</h3><p>{Object.entries(preview.weekly_minutes).map(([s,n])=>`${s}: ${n} min`).join(' · ')}</p>
      <div className="training-fields">{preview.sessions.map((s,i)=><article className="training-workout" key={i}><h4>{s.title}</h4><p>{new Date(s.scheduled_for).toLocaleString([],{timeZone:timezone})} · {s.definition.duration_minutes} min</p><p>{s.definition.effort_target.description}</p><ul>{s.definition.rationale.map(r=><li key={r}>{r}</li>)}</ul></article>)}</div>
      {preview.protected_days.length>0&&<div className="training-notice"><h3>Protected recovery days</h3>{preview.protected_days.map(d=><p key={d.date}>{d.date}: {d.reason}</p>)}</div>}
      <details open><summary>Longer-term direction · {brief.horizon_weeks} weeks</summary><div className="coach-roadmap">{preview.roadmap.map(w=><article key={w.week}><strong>Week {w.week} · {w.starts_on} · {w.phase}</strong><p>{w.focus}</p></article>)}</div></details>
      <p className="graph-meta">{preview.advisory}</p>
      {preview.replace_plan_id&&<p className="training-notice">Creating this draft cancels {preview.replaces_session_count} uncompleted local sessions in the selected week and preserves their revision history. Completed or published sessions cannot be replaced.</p>}
      <button type="button" className="primary-button" disabled={busy||preview.status!=='ready'||preview.week_start!==week} onClick={()=>void run(async()=>{await api('/api/training/coach/draft',request({brief:preview.brief,week_start:preview.week_start,timezone:preview.timezone,fingerprint:preview.fingerprint,replace_plan_id:preview.replace_plan_id}));setPreview(null);onDraftSaved();setMessage('Coached draft created. Review the sessions below and accept the plan when ready.');})}>Create reviewed weekly draft</button>
    </div>}
  </section>;
}
