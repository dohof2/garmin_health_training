import {useEffect,useState} from 'react';
import WorkoutMuscles from './WorkoutMuscles';
type RecordedExercise={id?:string;name:string;sets:number;repetitions:number;recorded_variants?:{id?:string;name:string}[]};
export default function RecordedStrengthMuscles({activityId}:{activityId:string}) {
 const [data,setData]=useState<{exercises:RecordedExercise[];source:string;warnings?:string[]}|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();
  fetch(`/api/activities/${encodeURIComponent(activityId)}/strength-exercises`,{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error('Could not load the recorded strength exercises.');return r.json();}).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
  return()=>controller.abort();
 },[activityId]);
 if(error)return <p role="status">{error}</p>;
 if(!data)return <p>Loading recorded strength exercises…</p>;
 if(!data.exercises.length)return <p className="graph-meta">This activity has no recorded exercise identities to build a muscle summary.</p>;
 return <section className="recorded-strength-muscles"><WorkoutMuscles exercises={data.exercises.flatMap(e=>e.recorded_variants?.length?e.recorded_variants:[e])}/><details><summary>Recorded exercises · {data.exercises.length}</summary>{data.exercises.map(e=><p key={e.id??e.name}><strong>{e.name}</strong> · {e.sets} sets · {e.repetitions} total repetitions{e.recorded_variants?.length?` · Recorded variants: ${e.recorded_variants.map(v=>v.name).join(', ')}`:''}</p>)}<p className="graph-meta">{data.source}</p>{data.warnings?.map(w=><p key={w} className="graph-meta">{w}</p>)}</details></section>;
}
