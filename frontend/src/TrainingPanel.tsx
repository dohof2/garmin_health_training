import { useEffect, useState } from "react";

type Sport = "cycling" | "running" | "strength";
type Answers = {
  sports: Sport[]; priority: string; availability: Array<{ weekday: number; start_time: string; minutes: number }>;
  experience: Record<string, string>; equipment: string[]; weekly_minutes: Record<string, number>;
  blocked_sports: Sport[]; blocked_movements: string[]; restrictions_notes: string; pain_or_illness: boolean | null;
};
type Context = { revision: number; answers: Partial<Answers>; missing: string[]; stale: string[]; ready: boolean; blockers: string[]; questions: Array<{ field: string; question: string; reason: string }> };
type Definition = { title: string; template_id: string; duration_minutes: number; rationale: string[]; effort_target: { description: string }; steps?: Array<{ type: string; duration_seconds: number; effort: string }>; exercises?: Array<{ name: string; sets: number; repetitions: number; load: string; rest_seconds: number }> };
type Workout = { id: string; training_plan_id: string; title: string; sport: string; scheduled_for: string; definition: Definition; revision: number; completion_status: string; suggested_revision: string | null; feedback: null | { effort: number | null; soreness: number | null; pain_or_illness: boolean; notes: string | null; activity_id: string | null } };
type History = { plans: Array<{ id: string; name: string; status: string; context: { rationale: string[]; readiness_context?: { date: string; status: string; score: number | null; note: string }; recorded_history?: { start: string; end: string; note: string; sports: Array<{ activity_type: string; activity_count: number; recorded_minutes: number }> }; preferences?: { goals?: Array<{ title: string }> } } }>; workouts: Workout[] };
type Proposal = { status: string; message?: string; expected_revision: number; changes: { weekly_minutes?: Record<string, number> }; rationale: string[]; advisory?: string };
const sports: Sport[] = ["cycling", "running", "strength"];
const equipment = ["bike", "trainer", "bodyweight", "dumbbells", "bands", "gym", "barbell", "mat"];
const movements = ["squat", "hinge", "push", "pull", "core"];
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const initial: Answers = { sports: [], priority: "general", availability: [], experience: {}, equipment: [], weekly_minutes: {}, blocked_sports: [], blocked_movements: [], restrictions_notes: "", pain_or_illness: null };
async function api(url: string, body?: unknown, method = "POST") {
  const response = await fetch(url, body === undefined ? undefined : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [editing, setEditing] = useState<Workout | null>(null);
  const [edit, setEdit] = useState({ template_id: "", duration_minutes: 30, completion_status: "planned", effort: "", soreness: "", pain_or_illness: false, notes: "", activity_id: "" });
  useEffect(() => {
    let active = true;
    Promise.all([api("/api/training/context"), api("/api/training")]).then(([context, history]) => {
      if (active) { setContext(context); setAnswers({ ...initial, ...context.answers }); setHistory(history); }
    }).catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, []);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setMessage(null);
    try { await action(); } catch (error) { setMessage(error instanceof Error ? error.message : "Training change failed."); }
    finally { setBusy(false); }
  };
  const toggle = (field: "sports" | "equipment" | "blocked_sports" | "blocked_movements", value: string) => setAnswers(current => ({ ...current, [field]: (current[field] as string[]).includes(value) ? current[field].filter(item => item !== value) : [...current[field], value] }));
  const openEdit = (workout: Workout) => {
    setEditing(workout); setEdit({ template_id: workout.definition.template_id, duration_minutes: workout.definition.duration_minutes, completion_status: workout.completion_status, effort: workout.feedback?.effort?.toString() ?? "", soreness: workout.feedback?.soreness?.toString() ?? "", pain_or_illness: Boolean(workout.feedback?.pain_or_illness), notes: workout.feedback?.notes ?? "", activity_id: workout.feedback?.activity_id ?? "" });
  };
  return <section className="training-panel" id="training" aria-labelledby="training-title">
    <div className="section-heading"><div><p>Personal training</p><h2 id="training-title">Build a week that fits</h2></div></div>
    <p>Save your availability, experience and constraints once. Drafts remain local and require review before becoming your plan. Long-term goals are optional.</p>
    {message && <p role="status" className="training-message">{message}</p>}
    {context && <>
      {context.questions.length > 0 && <div className="training-notice"><strong>Questions to complete or reconfirm</strong><ul>{context.questions.map(question => <li key={question.field}>{question.question} ({question.reason})</li>)}</ul></div>}
      {context.blockers.map(blocker => <p key={blocker} className="training-notice">{blocker}</p>)}
      <details open={!context.ready}><summary>Training preferences · revision {context.revision}</summary>
        <form onSubmit={event => { event.preventDefault(); void perform(async () => { const saved = await api("/api/training/preferences", { answers, expected_revision: context.revision }, "PUT"); setContext(saved); setAnswers({ ...initial, ...saved.answers }); setMessage("Training answers saved locally."); }); }}>
          <fieldset><legend>Sports</legend>{sports.map(sport => <label key={sport}><input type="checkbox" checked={answers.sports.includes(sport)} onChange={() => toggle("sports", sport)} />{sport}</label>)}</fieldset>
          <label>Immediate priority<select value={answers.priority} onChange={event => setAnswers({ ...answers, priority: event.target.value })}>{["general", "endurance", "strength", "mixed"].map(value => <option key={value}>{value}</option>)}</select></label>
          <fieldset><legend>Available days and session limits ({timezone})</legend>{weekdays.map((day, index) => {
            const slot = answers.availability.find(slot => slot.weekday === index);
            return <div className="training-slot" key={day}><label><input type="checkbox" checked={Boolean(slot)} onChange={event => setAnswers({ ...answers, availability: event.target.checked ? [...answers.availability, { weekday: index, start_time: "18:00", minutes: 30 }] : answers.availability.filter(slot => slot.weekday !== index) })} />{day}</label>{slot && <><label>Start on {day}<input type="time" required value={slot.start_time} onChange={event => setAnswers({ ...answers, availability: answers.availability.map(item => item.weekday === index ? { ...item, start_time: event.target.value } : item) })} /></label><label>Maximum minutes on {day}<input type="number" min="15" max="180" required value={slot.minutes} onChange={event => setAnswers({ ...answers, availability: answers.availability.map(item => item.weekday === index ? { ...item, minutes: Number(event.target.value) } : item) })} /></label></>}</div>;
          })}</fieldset>
          <div className="training-fields">{answers.sports.map(sport => <fieldset key={sport}><legend>{sport}</legend><label>Experience in {sport}<select required value={answers.experience[sport] ?? ""} onChange={event => setAnswers({ ...answers, experience: { ...answers.experience, [sport]: event.target.value } })}><option value="">Choose experience</option>{["new", "regular", "experienced"].map(value => <option key={value}>{value}</option>)}</select></label><label>Manageable weekly minutes of {sport}<input type="number" min="0" max="1260" required value={answers.weekly_minutes[sport] ?? ""} onChange={event => setAnswers({ ...answers, weekly_minutes: { ...answers.weekly_minutes, [sport]: Number(event.target.value) } })} /></label></fieldset>)}</div>
          <fieldset><legend>Available equipment</legend>{equipment.map(item => <label key={item}><input type="checkbox" checked={answers.equipment.includes(item)} onChange={() => toggle("equipment", item)} />{item}</label>)}</fieldset>
          <fieldset><legend>Exclude sports (leave unchecked for none)</legend>{sports.map(item => <label key={item}><input type="checkbox" checked={answers.blocked_sports.includes(item)} onChange={() => toggle("blocked_sports", item)} />{item}</label>)}</fieldset>
          <fieldset><legend>Exclude strength movements (leave unchecked for none)</legend>{movements.map(item => <label key={item}><input type="checkbox" checked={answers.blocked_movements.includes(item)} onChange={() => toggle("blocked_movements", item)} />{item}</label>)}</fieldset>
          <label>Other restrictions or clinician instructions<textarea maxLength={1500} placeholder="Leave blank if none. Written restrictions block automatic generation until reviewed." value={answers.restrictions_notes} onChange={event => setAnswers({ ...answers, restrictions_notes: event.target.value })} /></label>
          <label>Current pain or illness affecting training<select required value={answers.pain_or_illness === null ? "" : answers.pain_or_illness ? "yes" : "no"} onChange={event => setAnswers({ ...answers, pain_or_illness: event.target.value === "" ? null : event.target.value === "yes" })}><option value="">Choose an answer</option><option value="no">No</option><option value="yes">Yes — review before planning</option></select></label>
          <button disabled={busy} type="submit">Save training answers</button>
        </form>
      </details>
      <div className="training-draft"><label>Week starting Monday<input type="date" required value={week} onChange={event => setWeek(event.target.value)} /></label><button type="button" disabled={busy || !context.ready} onClick={() => void perform(async () => { setHistory(await api("/api/training/draft", { week_start: week, timezone, expected_preference_revision: context.revision })); setMessage("Draft created. Review every session before accepting."); })}>Create weekly draft</button></div>
      <button type="button" disabled={busy} onClick={() => void perform(async () => setProposal(await api("/api/training/progression")))}>Review next-week volume</button>
      {proposal && <div className="training-notice"><h3>Proposed weekly volume</h3>{proposal.message && <p>{proposal.message}</p>}<ul>{proposal.rationale.map(reason => <li key={reason}>{reason}</li>)}</ul>{proposal.changes.weekly_minutes && <p>{Object.entries(proposal.changes.weekly_minutes).map(([sport, minutes]) => `${sport}: ${minutes} minutes`).join(" · ")}</p>}{proposal.advisory && <p>{proposal.advisory}</p>}{proposal.status === "proposal" && <button type="button" disabled={busy} onClick={() => void perform(async () => { const saved = await api("/api/training/preferences", { answers: proposal.changes, expected_revision: proposal.expected_revision }, "PUT"); setContext(saved); setAnswers({ ...initial, ...saved.answers }); setProposal(null); setMessage("Reviewed volume limits saved. The existing calendar was unchanged."); })}>Save reviewed volume limits</button>}<button type="button" onClick={() => setProposal(null)}>Dismiss proposal</button></div>}
    </>}
    {history.plans.map(plan => <article className="training-plan" key={plan.id}><h3>{plan.name} · {plan.status}</h3><ul>{plan.context.rationale?.map(line => <li key={line}>{line}</li>)}</ul>{plan.status === "draft" && <button type="button" disabled={busy} onClick={() => void perform(async () => { setHistory(await api(`/api/training/plans/${plan.id}/accept`, {})); setMessage("Plan accepted locally. Nothing was published to Garmin."); })}>Accept reviewed plan</button>}
      <details><summary>Context used for this draft</summary>{plan.context.readiness_context && <p>Readiness on {plan.context.readiness_context.date}: {plan.context.readiness_context.score ?? plan.context.readiness_context.status}. {plan.context.readiness_context.note}</p>}{plan.context.recorded_history && <><p>Recorded activity from {plan.context.recorded_history.start} to {plan.context.recorded_history.end}. {plan.context.recorded_history.note}</p><ul>{plan.context.recorded_history.sports.map(sport => <li key={sport.activity_type}>{sport.activity_type}: {Math.round(sport.recorded_minutes)} minutes across {sport.activity_count} activities</li>)}</ul></>}{Boolean(plan.context.preferences?.goals?.length) && <p>Saved goals: {plan.context.preferences?.goals?.map(goal => goal.title).join(" · ")}</p>}</details>
      <div className="training-fields">{history.workouts.filter(workout => workout.training_plan_id === plan.id).map(workout => <article className="training-workout" key={workout.id}><h4>{workout.title}</h4><p>{new Date(workout.scheduled_for).toLocaleString([], { timeZone: timezone })} · {workout.definition.duration_minutes} minutes · {workout.completion_status}</p><p>{workout.definition.effort_target.description}</p>{workout.definition.steps?.map((step, index) => <p key={index}>{step.type}: {step.duration_seconds / 60} minutes, {step.effort}</p>)}{workout.definition.exercises?.map(exercise => <p key={exercise.name}>{exercise.name}: {exercise.sets} × {exercise.repetitions}; rest {exercise.rest_seconds}s. {exercise.load}</p>)}{workout.suggested_revision && <p className="training-notice">{workout.suggested_revision}</p>}<button type="button" disabled={busy} onClick={() => openEdit(workout)}>Edit session / record feedback</button></article>)}</div>
    </article>)}
    {editing && <form className="training-editor" onSubmit={event => { event.preventDefault(); void perform(async () => { const changes: Record<string, unknown> = { completion_status: edit.completion_status, effort: edit.effort === "" ? null : Number(edit.effort), soreness: edit.soreness === "" ? null : Number(edit.soreness), pain_or_illness: edit.pain_or_illness, notes: edit.notes, activity_id: edit.activity_id || null }; if (edit.template_id !== editing.definition.template_id || edit.duration_minutes !== editing.definition.duration_minutes) Object.assign(changes, { template_id: edit.template_id, duration_minutes: edit.duration_minutes }); setHistory(await api(`/api/training/workouts/${editing.id}`, { expected_revision: editing.revision, changes }, "PATCH")); setEditing(null); setMessage("Session and feedback saved. Other sessions were unchanged."); }); }}>
      <h3>Edit {editing.title}</h3><label>Workout template<select value={edit.template_id} onChange={event => setEdit({ ...edit, template_id: event.target.value })}>{["cycling_easy", "running_easy", "strength_foundation"].map(value => <option key={value}>{value}</option>)}</select></label><label>Session minutes<input type="number" min="15" max="180" required value={edit.duration_minutes} onChange={event => setEdit({ ...edit, duration_minutes: Number(event.target.value) })} /></label><label>Session status<select value={edit.completion_status} onChange={event => setEdit({ ...edit, completion_status: event.target.value })}>{["planned", "completed", "skipped", "cancelled"].map(value => <option key={value}>{value}</option>)}</select></label><label>Perceived effort (0–10, optional)<input type="number" min="0" max="10" step="0.5" value={edit.effort} onChange={event => setEdit({ ...edit, effort: event.target.value })} /></label><label>Soreness (0–10, optional)<input type="number" min="0" max="10" step="0.5" value={edit.soreness} onChange={event => setEdit({ ...edit, soreness: event.target.value })} /></label><label><input type="checkbox" checked={edit.pain_or_illness} onChange={event => setEdit({ ...edit, pain_or_illness: event.target.checked })} />Pain or illness</label><label>Linked Garmin activity ID (optional)<input value={edit.activity_id} onChange={event => setEdit({ ...edit, activity_id: event.target.value })} /></label><label>Session notes<textarea maxLength={1500} value={edit.notes} onChange={event => setEdit({ ...edit, notes: event.target.value })} /></label><button disabled={busy} type="submit">Save session and feedback</button><button type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel edit</button>
    </form>}
    {!history.plans.length && <p>No training plans yet. Complete the saved questions to create your first draft.</p>}
  </section>;
}
