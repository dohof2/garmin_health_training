import SortableCards from './SortableCards';
import {coalescedFetch} from './request';
import {GarminPublicationHistory} from './GarminWorkoutPublish';
import PlanDeleteButton from './PlanDeleteButton';
import TrainingScheduleEditor,{VolumeEstimates,type ScheduleDay,type WeeklyCaps,type VolumeEstimate,type TrainingSport,trainingSports} from './TrainingScheduleEditor';
import {displayPower,workoutEffortText} from './workoutPower';
import {workoutLabel} from './trainingCalendar';
import TodayWorkout from './TodayWorkout';
import StrengthPerformanceEntry from './StrengthPerformanceEntry';
import ActiveTrainingPlan from './ActiveTrainingPlan';
import { useEffect, useState } from "react";
import TrainingCoachPanel from "./TrainingCoachPanel";

type Sport = TrainingSport;
type Answers = {
  week_schedule:ScheduleDay[];weekly_caps:WeeklyCaps;
  sports: Sport[]; priority: string; availability: Array<{ weekday: number; start_time: string|null; minutes: number }>;
  experience: Record<string, string>; equipment: string[]; weekly_minutes: Record<string, number>;
  blocked_sports: Sport[]; blocked_movements: string[]; restrictions_notes: string; pain_or_illness: boolean | null;
};
type Context = {volume_estimates?:Record<string,VolumeEstimate>; revision: number; answers: Partial<Answers>; missing: string[]; stale: string[]; ready: boolean; blockers: string[]; questions: Array<{ field: string; question: string; reason: string }> };
type Definition = {scheduled_date?:string;time_unspecified?:boolean; title: string; template_id: string; duration_minutes: number; rationale: string[]; effort_target: { description: string }; steps?: Array<{ type: string; duration_seconds: number; effort: string }>; exercises?: Array<{ id:string; name: string; sets: number; repetitions: number; load: string; rest_seconds: number }> };
type Workout = {root_plan_id?:string|null; id: string; training_plan_id: string; title: string; sport: string; scheduled_for: string; definition: Definition; revision: number; completion_status: string; suggested_revision: string | null; feedback: null | { effort: number | null; soreness: number | null; pain_or_illness: boolean; notes: string | null; activity_id: string | null } };
type History = { plans: Array<{ id: string; name: string; status: string; plan_revision?:number; root_plan_id?:string; context: {program_id?:string; rationale: string[]; readiness_context?: { date: string; status: string; score: number | null; note: string }; recorded_history?: { start: string; end: string; note: string; sports: Array<{ activity_type: string; activity_count: number; recorded_minutes: number }> }; preferences?: { goals?: Array<{ title: string }> } } }>; workouts: Workout[] };

const sports: Sport[] = trainingSports.map(s=>s.id);
const equipment = ["bike", "trainer", "bodyweight", "dumbbells", "bands", "gym", "barbell", "mat", "pull_up_bar", "dip_bars"];
const movements = ["squat", "hinge", "push", "pull", "core"];
const initial: Answers = { week_schedule:[],weekly_caps:{},sports: [], priority: "general", availability: [], experience: {}, equipment: [], weekly_minutes: {}, blocked_sports: [], blocked_movements: [], restrictions_notes: "", pain_or_illness: null };
async function api(url: string, body?: unknown, method = "POST") {
  const response = await coalescedFetch(url, body === undefined ? undefined : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The training request could not be completed.");
  return result;
}
function nextMonday(timezone: string) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: timezone }).format(new Date());
  const value = new Date(`${today}T12:00:00Z`); value.setUTCDate(value.getUTCDate() + ((8 - value.getUTCDay()) % 7));
  return value.toISOString().slice(0, 10);
}
export default function TrainingPanel({ timezone }: { timezone: string }) {
  const [context, setContext] = useState<Context | null>(null);
  const [answers, setAnswers] = useState<Answers>(initial);
  const [history, setHistory] = useState<History>({ plans: [], workouts: [] });
  const [week, setWeek] = useState(() => nextMonday(timezone));
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Workout | null>(null);
  const [edit, setEdit] = useState({ template_id: "", duration_minutes: 30, completion_status: "planned", effort: "", soreness: "", pain_or_illness: false, notes: "", activity_id: "" });
  useEffect(() => {
    let active = true;
    Promise.all([api("/api/training/context"), api("/api/training?compact=true")]).then(([context, history]) => {
      if (active) { setContext(context); setAnswers({ ...initial, ...context.answers }); setHistory(history); }
    }).catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, []);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setMessage(null);
    try { await action(); } catch (error) { setMessage(error instanceof Error ? error.message : "Training change failed."); }
    finally { setBusy(false); }
  };
  useEffect(()=>{const changed=()=>{void Promise.all([api('/api/training/context'),api('/api/training?compact=true')]).then(([c,h])=>{setContext(c);setAnswers({...initial,...c.answers});setHistory(h);}).catch(e=>setMessage(e.message));};window.addEventListener('training-plan-changed',changed);return()=>window.removeEventListener('training-plan-changed',changed);},[]);
  const toggle = (field: "sports" | "equipment" | "blocked_sports" | "blocked_movements", value: string) => setAnswers(current => ({ ...current, [field]: (current[field] as string[]).includes(value) ? current[field].filter(item => item !== value) : [...current[field], value] }));
  const openEdit = (workout: Workout) => {
    setEditing(workout); setEdit({ template_id: workout.definition.template_id, duration_minutes: workout.definition.duration_minutes, completion_status: workout.completion_status, effort: workout.feedback?.effort?.toString() ?? "", soreness: workout.feedback?.soreness?.toString() ?? "", pain_or_illness: Boolean(workout.feedback?.pain_or_illness), notes: workout.feedback?.notes ?? "", activity_id: workout.feedback?.activity_id ?? "" });
  };
  return <SortableCards id="training:cards" className="training-panel" pageSections>
    <ActiveTrainingPlan timezone={timezone} revision={JSON.stringify([history.plans.map(p=>[p.id,p.status]),history.workouts.map(w=>[w.id,w.revision])])} onChanged={()=>{void api('/api/training?compact=true').then(setHistory).catch(e=>setMessage(e.message));}} onEdit={id=>{void api('/api/training?compact=true').then((h:History)=>{setHistory(h);const workout=h.workouts.find(w=>w.id===id);if(workout){openEdit(workout);setTimeout(()=>document.getElementById('training-session-editor')?.scrollIntoView({behavior:'smooth',block:'start'}),0);}}).catch(e=>setMessage(e.message));}}/>
    <div className="section-heading"><div><p>Personal training</p><h2 id="training-title">Your training</h2></div></div>
    {message && <p role="status" className="training-message">{message}</p>}
    <TodayWorkout timezone={timezone}/><GarminPublicationHistory timezone={timezone}/>
    <TrainingCoachPanel timezone={timezone} week={week} onWeekChange={setWeek} plans={history.plans} onDraftSaved={() => { void api("/api/training?compact=true").then(setHistory).catch(e=>setMessage(e.message)); }} />
    {context && <>

      {context.blockers.map(blocker => <p key={blocker} className="training-notice">{blocker}</p>)}
      <details id="training-preferences"><summary>Training preferences</summary>
      {context.questions.length > 0 && <div className="training-notice"><strong>Saved preferences still to complete (your chat draft may contain newer answers)</strong><ul>{context.questions.map(question => <li key={question.field}>{question.question} ({question.reason})</li>)}</ul></div>}
        <form onSubmit={event => { event.preventDefault(); void perform(async () => { const saved = await api("/api/training/preferences", { answers:((({availability,weekly_minutes,...current})=>current)(answers)), expected_revision: context.revision }, "PUT"); setContext(saved); setAnswers({ ...initial, ...saved.answers }); setMessage("Training preferences saved locally. Active-plan changes require review and approval.");window.dispatchEvent(new Event('training-plan-changed')); }); }}>
          <fieldset><legend>Sports</legend>{sports.map(sport => <label key={sport}><input type="checkbox" checked={answers.sports.includes(sport)} onChange={() => toggle("sports", sport)} />{sport}</label>)}</fieldset>
          <label>Immediate priority<select value={answers.priority} onChange={event => setAnswers({ ...answers, priority: event.target.value })}>{["general", "endurance", "strength", "mixed"].map(value => <option key={value}>{value}</option>)}</select></label>
          <TrainingScheduleEditor schedule={answers.week_schedule} caps={answers.weekly_caps} sports={Array.from(new Set([...answers.sports,...Object.keys(answers.weekly_minutes)]))} onChange={week_schedule=>setAnswers({...answers,week_schedule})} onCapsChange={weekly_caps=>setAnswers({...answers,weekly_caps})}/>
          <VolumeEstimates estimates={context.volume_estimates}/>{Object.keys(answers.weekly_minutes).length>0&&<p className="graph-meta">Legacy weekly limits retained until explicitly replaced or cleared: {Object.entries(answers.weekly_minutes).map(([sport,minutes])=>`${sport}: ${minutes} min`).join(' · ')}. These are limits, not measured fitness.</p>}
          <div className="training-fields">{answers.sports.filter(sport=>['cycling','running','strength'].includes(sport)).map(sport=><label key={sport}>Experience in {sport}<select value={answers.experience[sport]??''} onChange={event=>setAnswers({...answers,experience:{...answers.experience,[sport]:event.target.value}})}><option value="">Use available history / ask if needed</option>{['new','regular','experienced'].map(value=><option key={value}>{value}</option>)}</select></label>)}</div>
          <fieldset><legend>Available equipment</legend>{equipment.map(item => <label key={item}><input type="checkbox" checked={answers.equipment.includes(item)} onChange={() => toggle("equipment", item)} />{item.replaceAll("_", " ")}</label>)}</fieldset>
          <fieldset><legend>Exclude sports (leave unchecked for none)</legend>{sports.map(item => <label key={item}><input type="checkbox" checked={answers.blocked_sports.includes(item)} onChange={() => toggle("blocked_sports", item)} />{item.replaceAll("_", " ")}</label>)}</fieldset>
          <fieldset><legend>Exclude strength movements (leave unchecked for none)</legend>{movements.map(item => <label key={item}><input type="checkbox" checked={answers.blocked_movements.includes(item)} onChange={() => toggle("blocked_movements", item)} />{item.replaceAll("_", " ")}</label>)}</fieldset>
          <label>Other restrictions or clinician instructions<textarea maxLength={1500} placeholder="Leave blank if none. Written restrictions block automatic generation until reviewed." value={answers.restrictions_notes} onChange={event => setAnswers({ ...answers, restrictions_notes: event.target.value })} /></label>
          <label>Current pain or illness affecting training<select required value={answers.pain_or_illness === null ? "" : answers.pain_or_illness ? "yes" : "no"} onChange={event => setAnswers({ ...answers, pain_or_illness: event.target.value === "" ? null : event.target.value === "yes" })}><option value="">Choose an answer</option><option value="no">No</option><option value="yes">Yes — review before planning</option></select></label>
          <button disabled={busy} type="submit">Save training answers</button>
        </form>
      </details>
    </>}
    <details className="training-history"><summary>Plan history and session feedback</summary>
    {history.plans.filter(plan=>!(plan.root_plan_id&&plan.root_plan_id!==plan.id)&&!plan.context.program_id).map(plan => <article className="training-plan" key={plan.id}><h3>{plan.name} · {plan.status}</h3><ul>{plan.context.rationale?.map(line => <li key={line}>{line}</li>)}</ul><PlanDeleteButton id={plan.id} name={plan.name} revision={plan.plan_revision} onDeleted={()=>{void api('/api/training?compact=true').then(setHistory).catch(e=>setMessage(e.message));}}/>
      <details><summary>Context used for this draft</summary>{plan.context.readiness_context && <p>Readiness on {plan.context.readiness_context.date}: {plan.context.readiness_context.score ?? plan.context.readiness_context.status}. {plan.context.readiness_context.note}</p>}{plan.context.recorded_history && <><p>Recorded activity from {plan.context.recorded_history.start} to {plan.context.recorded_history.end}. {plan.context.recorded_history.note}</p><ul>{plan.context.recorded_history.sports.map(sport => <li key={sport.activity_type}>{sport.activity_type}: {Math.round(sport.recorded_minutes)} minutes across {sport.activity_count} activities</li>)}</ul></>}{Boolean(plan.context.preferences?.goals?.length) && <p>Saved goals: {plan.context.preferences?.goals?.map(goal => goal.title).join(" · ")}</p>}</details>
      <div className="training-fields">{history.workouts.filter(workout => workout.training_plan_id === plan.id||workout.root_plan_id===plan.id||history.plans.some(child=>child.id===workout.training_plan_id&&child.context.program_id===plan.id)).map(workout => <article className="training-workout" key={workout.id}><h4>{workout.title}</h4><p>{workoutLabel(workout,timezone)} · {workout.definition.duration_minutes} minutes · {workout.completion_status}</p><p>{workoutEffortText(workout.definition)}</p>{displayPower(workout.definition).steps?.map((step, index) => <p key={index}>{step.type}: {step.duration_seconds / 60} minutes, {step.effort}</p>)}{workout.definition.exercises?.map(exercise => <p key={exercise.name}>{exercise.name}: {exercise.sets} × {exercise.repetitions}; rest {exercise.rest_seconds}s. {exercise.load}</p>)}{workout.suggested_revision && <p className="training-notice">{workout.suggested_revision}</p>}<button type="button" disabled={busy} onClick={() => openEdit(workout)}>Edit session / record feedback</button></article>)}</div>
    </article>)}
    {history.workouts.filter(workout=>workout.completion_status==='completed'&&!history.plans.some(plan=>plan.id===workout.training_plan_id)).map(workout=><article className="training-workout" key={workout.id}><h4>{workout.title} · Plan removed</h4><p>{workoutLabel(workout,timezone)} · completed</p><button type="button" onClick={()=>openEdit(workout)}>View session feedback</button></article>)}
    </details>
    {editing && <form id="training-session-editor" className="training-editor" onSubmit={event => { event.preventDefault(); void perform(async () => { const changes: Record<string, unknown> = { completion_status: edit.completion_status, effort: edit.effort === "" ? null : Number(edit.effort), soreness: edit.soreness === "" ? null : Number(edit.soreness), pain_or_illness: edit.pain_or_illness, notes: edit.notes, activity_id: edit.activity_id || null }; if (edit.template_id !== editing.definition.template_id || edit.duration_minutes !== editing.definition.duration_minutes) Object.assign(changes, { template_id: edit.template_id, duration_minutes: edit.duration_minutes }); setHistory(await api(`/api/training/workouts/${editing.id}`, { expected_revision: editing.revision, changes }, "PATCH")); setEditing(null); setMessage("Session and feedback saved. Upcoming sessions are reviewed against this feedback."); }); }}>
      <h3>Edit {editing.title}</h3>{editing.sport==='strength' && editing.definition.exercises && <StrengthPerformanceEntry key={editing.id} workoutId={editing.id} revision={editing.revision} exercises={editing.definition.exercises} onSaved={()=>{void api('/api/training?compact=true').then((h:History)=>{setHistory(h);setEditing(h.workouts.find(w=>w.id===editing.id)??null);}).catch(e=>setMessage(e.message));}}/>}<label>Workout template<select value={edit.template_id} onChange={event => setEdit({ ...edit, template_id: event.target.value })}>{!["cycling_easy", "running_easy", "strength_foundation"].includes(edit.template_id) && <option value={edit.template_id}>{edit.template_id.replaceAll("_"," ")}</option>}{({cycling:['cycling_easy'],running:['running_easy'],strength:['strength_foundation']} as Record<string,string[]>)[editing.sport]?.map(value => <option key={value}>{value}</option>)}</select></label><label>Session minutes<input type="number" min="15" max="720" required value={edit.duration_minutes} onChange={event => setEdit({ ...edit, duration_minutes: Number(event.target.value) })} /></label><label>Session status<select value={edit.completion_status} onChange={event => setEdit({ ...edit, completion_status: event.target.value })}>{["planned", "completed", "skipped", "cancelled"].map(value => <option key={value}>{value}</option>)}</select></label><label>Perceived effort (0–10, optional)<input type="number" min="0" max="10" step="0.5" value={edit.effort} onChange={event => setEdit({ ...edit, effort: event.target.value })} /></label><label>Soreness (0–10, optional)<input type="number" min="0" max="10" step="0.5" value={edit.soreness} onChange={event => setEdit({ ...edit, soreness: event.target.value })} /></label><label><input type="checkbox" checked={edit.pain_or_illness} onChange={event => setEdit({ ...edit, pain_or_illness: event.target.checked })} />Pain or illness</label><label>Linked Garmin activity ID (optional)<input value={edit.activity_id} onChange={event => setEdit({ ...edit, activity_id: event.target.value })} /></label><label>Session notes<textarea maxLength={1500} value={edit.notes} onChange={event => setEdit({ ...edit, notes: event.target.value })} /></label><button disabled={busy} type="submit">Save session and feedback</button><button type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel edit</button>
    </form>}
    {context && !history.plans.length && <p>No saved plans yet. Use the trainer to prepare and review your first plan.</p>}
  </SortableCards>;
}
