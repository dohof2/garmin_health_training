import MuscleDiagram from './MuscleDiagram';
import {combinedMuscles,muscleProfile} from './exerciseMuscles';
export default function WorkoutMuscles({exercises}:{exercises:{id?:string;name:string}[]}) {
 const profile=combinedMuscles(exercises);
 const unmapped=exercises.filter(e=>!muscleProfile(e.id,e.name));
 return <section className="workout-muscle-summary" aria-label="Whole workout muscle summary"><h3>Muscles worked · whole workout</h3>
  {profile?<MuscleDiagram name="Whole strength workout" profile={profile}/>:<p>Muscle references are not available for the recorded exercises yet.</p>}
  {unmapped.length>0&&<p className="graph-meta">Not included in the illustration: {unmapped.map(e=>e.name).join(', ')}.</p>}
 </section>;
}
