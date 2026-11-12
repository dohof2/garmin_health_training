import {useState} from 'react';
import TrainingAdjustmentProposal, {type Adjustment} from './TrainingAdjustmentProposal';

export type DurationSetting={sport:string;workout_type:string;minutes:number;slot_id?:string;scope?:string};
type Workout={id:string;title:string;definition:{duration_minutes:number;duration_setting?:DurationSetting}};
export default function WorkoutDurationSettings({settings,selected,today,disabled}:{settings:DurationSetting[];selected?:Workout;today:string;disabled:boolean}) {
  const [scope,setScope]=useState('plan'),[sport,setSport]=useState('all'),[kind,setKind]=useState('all'),[minutes,setMinutes]=useState(60),[day,setDay]=useState(today);
  const [proposal,setProposal]=useState<Adjustment|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  return <details className="journal-duration-settings"><summary><strong>Workout time settings</strong><span className="settings-current-value">{settings.length?`${settings.length} saved time preferences`:"Review time allowances"}</span></summary>
    {settings.length>0&&<ul>{settings.map((setting,index)=><li key={index}>{setting.sport==='all'?'All activities':setting.sport} · {setting.slot_id?`Schedule slot ${setting.slot_id}`:setting.workout_type==='all'?'All workout types':setting.workout_type.replaceAll('_',' ')}: {setting.minutes} minutes · Rest of plan</li>)}</ul>}
    {selected?.definition.duration_setting?.scope==='once'&&<p>{selected.title}: {selected.definition.duration_setting.minutes} minutes · One time</p>}
    <form onSubmit={async event=>{event.preventDefault();setBusy(true);setError('');setProposal(null);try{
      const args={scope:scope==='plan'?'plan':'once',minutes,sport,workout_type:kind,...(scope==='selected'?{workout_id:selected?.id}:scope==='date'?{date:day}:{})};
      const response=await fetch('/api/training/active/duration/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(args)});
      const result=await response.json();if(!response.ok)throw new Error(result.detail||'Could not review workout time');setProposal(result);
    }catch(error){setError(error instanceof Error?error.message:'Could not review workout time');}finally{setBusy(false);}}}>
      <label>Apply time to<select value={scope} onChange={event=>{setScope(event.target.value);setProposal(null);}}><option value="plan">Rest of plan</option><option value="date">One date</option><option value="selected" disabled={!selected}>Selected workout{selected?`: ${selected.title}`:''}</option></select></label>
      {scope==='date'&&<label>Date<input type="date" required min={today} value={day} onChange={event=>{setDay(event.target.value);setProposal(null);}}/></label>}
      <label>Activity<select value={sport} onChange={event=>{setSport(event.target.value);setKind('all');setProposal(null);}}>{['all','cycling','running','strength','hiking','other'].map(value=><option key={value} value={value}>{value==='all'?'All activities':value}</option>)}</select></label>
      <label>Workout type<select value={kind} onChange={event=>{setKind(event.target.value);setProposal(null);}}><option value="all">All workout types</option>{(sport==='strength'?['cycling_support','general_fitness','strength_development']:sport==='cycling'||sport==='running'?['recovery','endurance','long_endurance','tempo','threshold','vo2','sprint','anaerobic']:[]).map(value=><option key={value} value={value}>{value.replaceAll('_',' ')}</option>)}</select></label>
      <label>Time allowance (minutes)<input type="number" required min={sport==='strength'?20:10} max={720} step={1} value={minutes} onChange={event=>{setMinutes(Number(event.target.value));setProposal(null);}}/></label>
      <p>Updates matching scheduled workouts. Rest-of-plan settings also apply to future workouts. Strength uses the time as a budget. Completed workouts and fixed events are preserved.</p>
      <button type="submit" disabled={disabled||busy||scope==='selected'&&!selected}>{busy?'Preparing review…':'Review time change'}</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {proposal&&<TrainingAdjustmentProposal key={proposal.fingerprint} proposal={proposal}/>}
  </details>;
}
