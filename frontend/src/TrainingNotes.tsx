import {useEffect,useState} from 'react';
import {api} from './GraphCanvas';
type Settings={sets?:number;rest_seconds?:number;continuous_endurance?:boolean};
type Note={activity:string;workout_type:string;topic:string;text:string;revision:number;settings:Settings};
type Notes={notes:Note[];workout_types:Record<string,string[]>;limits:{per_note:number;total_characters:number;notes:number}};
const post=(body:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const label=(value:string)=>value==='all'?'All':value.replaceAll('_',' ');

export default function TrainingNotes({timezone}:{timezone:string}){
 const [data,setData]=useState<Notes|null>(null),[activity,setActivity]=useState('strength'),[kind,setKind]=useState('all');
 const [topic,setTopic]=useState('sets'),[text,setText]=useState(''),[revision,setRevision]=useState(0),[settings,setSettings]=useState<Settings>({});
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const refresh=()=>api<Notes>('/api/training/notes').then(next=>{setData(next);return next;});
 useEffect(()=>{void refresh().then(next=>{const note=next.notes.find(n=>n.activity==='strength'&&n.workout_type==='all'&&n.topic==='sets');if(note)edit(note);}).catch(e=>setError(e.message));const changed=()=>void refresh().catch(e=>setError(e.message));window.addEventListener('training-plan-changed',changed);return()=>window.removeEventListener('training-plan-changed',changed);},[]);
 function edit(note:Note){setActivity(note.activity);setKind(note.workout_type);setTopic(note.topic);setText(note.text);setRevision(note.revision);setSettings(note.settings);setMessage('');}
 function clear(){setRevision(0);setText('');setSettings({});}
 async function save(operation='upsert'){
  setBusy(true);setError('');setMessage('');
  try{const result=await api<{message:string}>('/api/training/notes',post({activity,workout_type:kind,topic,text,settings,expected_revision:revision,operation}));
   setMessage(result.message);const next=await api<Notes>('/api/training/notes');setData(next);
   const saved=next.notes.find(n=>n.activity===activity&&n.workout_type===kind&&n.topic===topic);if(saved){setRevision(saved.revision);}else clear();
   window.dispatchEvent(new Event('training-plan-changed'));
  }catch(e){setError(e instanceof Error?e.message:'Could not save note.');}finally{setBusy(false);}
 }
 return <details id="training-notes"><summary>Recurring training notes</summary><p>Short preferences for future plans and daily reviews. Chat can edit these too. Specific workout notes override activity defaults.</p>
 {data&&Object.entries(data.workout_types).filter(([sport])=>data.notes.some(n=>n.activity===sport)).map(([sport])=><details key={sport}><summary>{label(sport)}</summary>{[...new Set(data.notes.filter(n=>n.activity===sport).map(n=>n.workout_type))].map(type=><div key={type}><strong>{label(type)}</strong>{data.notes.filter(n=>n.activity===sport&&n.workout_type===type).map(n=><p key={n.topic}><button disabled={busy} type="button" onClick={()=>edit(n)}>{n.topic.replaceAll('_',' ')}</button> {n.text}</p>)}</div>)}</details>)}
 <form onSubmit={e=>{e.preventDefault();void save();}}><div className="builder-fields">
 <label>Activity<select disabled={busy} value={activity} onChange={e=>{setActivity(e.target.value);setKind('all');clear();}}>{Object.keys(data?.workout_types??{strength:[]}).map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label>
 <label>Workout type<select disabled={busy} value={kind} onChange={e=>{setKind(e.target.value);clear();}}>{(data?.workout_types[activity]??['all']).map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label>
 <label>Topic<input required disabled={busy||revision>0} value={topic} pattern="[a-z][a-z0-9_]{0,23}" maxLength={24} onChange={e=>setTopic(e.target.value)} placeholder="sets, format, terrain"/></label>
 <label>Preference<input required disabled={busy} value={text} maxLength={160} onChange={e=>setText(e.target.value)} placeholder="Use 2 sets per exercise, including recovery weeks."/><small>{text.length}/160 characters</small></label>
 {activity==='strength'&&<><label>Sets per exercise (optional)<input type="number" disabled={busy} min={1} max={5} value={settings.sets??''} onChange={e=>{const next={...settings};if(e.target.value)next.sets=Number(e.target.value);else delete next.sets;setSettings(next);}}/></label><label>Rest per set, seconds (optional)<input type="number" disabled={busy} min={0} max={600} value={settings.rest_seconds??''} onChange={e=>{const next={...settings};if(e.target.value)next.rest_seconds=Number(e.target.value);else delete next.rest_seconds;setSettings(next);}}/></label></>}
 {activity==='cycling'&&['all','endurance','long_endurance','recovery'].includes(kind)&&<label>Easy-ride format<select disabled={busy} value={settings.continuous_endurance==null?'':String(settings.continuous_endurance)} onChange={e=>{const next={...settings};if(e.target.value==='')delete next.continuous_endurance;else next.continuous_endurance=e.target.value==='true';setSettings(next);}}><option value="">Use plan default</option><option value="true">One continuous block</option></select></label>}
 </div><button disabled={busy} type="submit">{busy?'Saving…':'Save note'}</button>{revision>0&&<button disabled={busy} type="button" onClick={()=>void save('delete')}>Delete note</button>}<button disabled={busy} type="button" onClick={clear}>New note</button></form>
 <button disabled={busy} type="button" onClick={()=>{setBusy(true);setError('');void api<{message:string;warnings:string[]}>(`/api/training/notes/apply?timezone_name=${encodeURIComponent(timezone)}`,post({})).then(result=>{setMessage([result.message,...result.warnings].join(' '));window.dispatchEvent(new Event('training-plan-changed'));}).catch(e=>setError(e.message)).finally(()=>setBusy(false));}}>Apply notes to next seven days</button>
 {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}</details>;
}
