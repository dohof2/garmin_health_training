import {trainingWeek,workoutDate} from './trainingCalendar';
export type CalendarWorkout={id:string;title:string;sport:string;scheduled_for:string;completion_status:string;definition:{duration_minutes:number;scheduled_date?:string;time_unspecified?:boolean;variant_label?:string|null;is_race?:boolean;sport_label?:string;label?:string;duration_guidance?:{recovery_adjustment?:{allocated_minutes:number}}}};

export default function TrainingWeek({workouts,timezone,selectedWorkoutId,onSelect,now=new Date()}:{workouts:CalendarWorkout[];timezone:string;selectedWorkoutId:string|null;onSelect:(id:string)=>void;now?:Date}) {
 return <div className="training-week">{trainingWeek(now,timezone).map(day=>{
  const sessions=workouts.filter(w=>w.completion_status!=='cancelled'&&workoutDate(w,timezone)===day).sort((a,b)=>a.scheduled_for.localeCompare(b.scheduled_for)||a.id.localeCompare(b.id));
  const completed=sessions.filter(w=>w.completion_status==='completed').length;
  const date=new Date(`${day}T12:00:00Z`);
  return <div className="training-day-card" key={day}>
   <div className="training-day-heading"><strong>{date.toLocaleDateString([],{timeZone:'UTC',weekday:'long'})}</strong><time dateTime={day}>{date.toLocaleDateString([],{timeZone:'UTC',month:'short',day:'numeric'})}</time></div>
   {completed>0&&<span className="training-day-completion">{completed===sessions.length?<><CompletionIcon/> All sessions completed</>:`${completed} of ${sessions.length} sessions completed`}</span>}
   {sessions.length?sessions.map(w=>{
    const kind=workoutPresentation(w),done=w.completion_status==='completed';
    return <button type="button" key={w.id} className={`workout-day ${kind.kind}${done?' workout-day--completed':''}`} aria-expanded={selectedWorkoutId===w.id} aria-controls="selected-workout-detail" onClick={()=>onSelect(w.id)}>
     <span className="workout-day-type">{done?<CompletionIcon/>:<SportIcon sport={w.sport}/>}<span>{kind.label}</span></span>
     {done&&<span className="workout-completion-label">Completed</span>}
     <span className="workout-day-title">{w.title}</span>{w.definition.variant_label&&<span className="graph-meta">{w.definition.variant_label}</span>}<strong className="workout-day-duration">{formatWorkoutDuration(w.definition.duration_minutes)}</strong>
     {!done&&w.definition.duration_guidance?.recovery_adjustment&&w.definition.duration_guidance.recovery_adjustment.allocated_minutes>w.definition.duration_minutes&&<span className="graph-meta">Recovery-adjusted · planned {formatWorkoutDuration(w.definition.duration_guidance.recovery_adjustment.allocated_minutes)}</span>}
     <span className="workout-day-action">{selectedWorkoutId===w.id?'Hide workout details':'View workout details'} <span aria-hidden="true">{selectedWorkoutId===w.id?'−':'+'}</span></span>
    </button>;
   }):<div className="training-rest-day"><span aria-hidden="true">☾</span><strong>Rest day</strong><small>No session scheduled</small></div>}
  </div>;
 })}</div>;
}

function CompletionIcon(){return <svg className="workout-completion-icon" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="16" cy="16" r="13"/><path d="m9 16 5 5 9-10"/></svg>;}

function workoutPresentation(w:CalendarWorkout){const title=w.title.toLowerCase();if(w.definition.is_race)return {kind:'race',icon:'⚑',label:'Race / event'};if(w.sport==='strength')return {kind:'strength',icon:'◆',label:'Strength'};if(w.sport==='running')return {kind:'run',icon:'↗',label:'Run'};if(w.sport==='hiking')return {kind:'hiking',icon:'△',label:'Hiking'};if(w.sport!=='cycling')return {kind:'other',icon:'◇',label:w.definition.sport_label??w.definition.label??(w.sport==='other'?'Other activity':w.sport)};const kind=['recovery','anaerobic','endurance','tempo','threshold','sprint'].find(k=>title.includes(k))||(title.includes('vo2')||title.includes('vo₂')?'vo2':'cycling');return {kind,icon:'◉',label:({recovery:'Recovery',endurance:'Endurance',tempo:'Tempo',threshold:'Threshold',sprint:'Sprint',anaerobic:'Anaerobic',vo2:'VO₂ max',cycling:'Ride'} as Record<string,string>)[kind]};}


function formatWorkoutDuration(minutes:number){
  const total=Math.max(0,Math.round(minutes));
  if(total<60)return `${total}m`;
  const hours=Math.floor(total/60),remainder=total%60;
  return remainder?`${hours}h ${remainder}m`:`${hours}h`;
}


function SportIcon({sport}:{sport:string}){
  return <svg className="workout-sport-icon" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{sport==='strength'?<><path d="m9 23 14-14M6 17l9 9M3 20l9 9M17 6l9 9M20 3l9 9"/></>:sport==='running'?<><circle cx="21" cy="5" r="2.4"/><path d="m18 10-5 7 7 4-3 8M18 10l5 7 6 1M16 13l-6-2-5 5M13 17l-3 7-7 2"/></>:sport!=='cycling'?<><path d="m5 27 9-19 6 10 4-6 5 15H5Z"/></>:<><circle cx="8" cy="23" r="6"/><circle cx="25" cy="23" r="6"/><path d="m8 23 6-13 7 13H8l10-9M11 10h6M25 23l-5-17h-4"/></>}</svg>;
}
