import { useEffect, useRef, useState } from 'react';
import { api } from './GraphCanvas';
import { ReadinessCard, type ReadinessSignals } from './ReadinessCard';
import DashboardNutrition from './DashboardNutrition';
import DashboardActivity,{type DashboardActivityRecord} from './DashboardActivity';
import DashboardNight from './DashboardNight';
import RecentTrainingSummary from './RecentTrainingSummary';
import { ArrowRight, SportIcon, X } from './JournalIcons';
import { trainingDate, workoutDate, mergeWorkoutStatus } from './trainingCalendar';
import WorkoutLaps, { type Prescription } from './WorkoutLaps';

type Workout = { id: string; title: string; sport: string; scheduled_for: string; completion_status: string; definition: Prescription & { duration_minutes: number; effort_target?: { description: string } } };
type Plan = { program: { status: string } | null; workouts: Workout[]; completed_workouts?: Workout[] };
type LatestActivity = DashboardActivityRecord | null;

export default function JournalDashboard({ timezone, refresh, active, latestActivity, distanceUnit, onActivityDetails }: { timezone: string; refresh: string; active: boolean; latestActivity: LatestActivity; distanceUnit: 'km'|'mi'; onActivityDetails:(id:string)=>void }) {
  const [nightView,setNightView]=useState<'hrv'|'sleep'|null>(null);
  const [clock, setClock] = useState(() => Date.now());
  const [signals,setSignals] = useState<ReadinessSignals|null>(null);
  const [revision, setRevision] = useState(0);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState('');
  const [selected, setSelected] = useState<Workout | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const today = trainingDate(new Date(clock), timezone);
  useEffect(() => {
    const changed = () => { setRevision(v => v + 1); setClock(Date.now()); };
    const timer = window.setInterval(() => setClock(Date.now()), 60000);
    window.addEventListener('training-plan-changed', changed); window.addEventListener('focus', changed);
    return () => { clearInterval(timer); window.removeEventListener('training-plan-changed', changed); window.removeEventListener('focus', changed); };
  }, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setPlanError('');
    void api<Plan>(`/api/training/active?timezone=${encodeURIComponent(timezone)}`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setPlan(value); }).catch(e => { if (!controller.signal.aborted) setPlanError(e.message); });
    return () => controller.abort();
  }, [active, timezone, today, revision, refresh]);
  useEffect(() => { if (selected) dialog.current?.showModal(); else dialog.current?.close(); }, [selected]);
  const workouts = mergeWorkoutStatus(plan?.workouts ?? [], plan?.completed_workouts ?? []);
  const sessions = workouts.filter(w => workoutDate(w, timezone) === today && !['skipped', 'cancelled'].includes(w.completion_status));
  const workout = sessions.find(w => w.completion_status === 'planned') ?? sessions[0];
  const monday = new Date(`${today}T12:00:00Z`); monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
  const week = Array.from({ length: 7 }, (_, i) => { const date = new Date(monday); date.setUTCDate(date.getUTCDate() + i); return date.toISOString().slice(0, 10); });
  return <section className="journal-dashboard" aria-label="Your training today">
    <div className="journal-daily">
      <div className="journal-workout-overview">
        <section className="journal-today" aria-labelledby="journal-workout-title">
          <p className="journal-kicker">Today’s workout</p>
          {planError ? <p role="alert">{planError} <button type="button" onClick={() => setRevision(v => v + 1)}>Retry workouts</button></p> : !plan ? <p role="status">Loading your training…</p> : workout ? <>
            <div className="journal-workout-title"><SportIcon sport={workout.sport} size={42}/><h2 id="journal-workout-title">{workout.title}</h2></div>
            <p className="journal-workout-meta">{workout.definition.duration_minutes} min <span>·</span> {workout.sport.replaceAll('_', ' ')}{workout.completion_status === 'completed' ? ' · Completed' : ''}{plan.program?.status && plan.program.status !== 'active' ? ` · Plan ${plan.program.status}` : ''}</p>
            <button className="primary-button journal-view-workout" type="button" onClick={() => setSelected(workout)}>View workout <ArrowRight size={22}/></button>
            {sessions.length > 1 && <details className="journal-extra-sessions"><summary>{sessions.length - 1} more session{sessions.length > 2 ? 's' : ''} today</summary>{sessions.filter(w => w.id !== workout.id).map(w => <button type="button" key={w.id} onClick={() => setSelected(w)}>{w.title} · {w.definition.duration_minutes} min</button>)}</details>}
          </> : <><h2 id="journal-workout-title">Room to recover.</h2><p>{plan.program ? 'No workout scheduled for today.' : 'Your next chapter starts with a plan.'}</p><a href="#training" className="journal-text-action">{plan.program ? 'View training plan' : 'Set up your training'} <ArrowRight size={18}/></a></>}
        </section>
        <section className="journal-readiness-slot" aria-label="Today’s training readiness"><ReadinessCard timezone={timezone} refreshToken={refresh} compact onSignals={setSignals} /></section>
      </div>
      <div className="journal-support-band"><DashboardNutrition timezone={timezone} active={active} refresh={refresh} compact /><button type="button" className="journal-health-signal" aria-haspopup="dialog" onClick={()=>setNightView('hrv')} aria-label="View last night’s HRV plot"><h3>HRV</h3><p>{!signals?'Loading…':signals.date!==today?'Not current':signals.hrv===null?'Unavailable':`${signals.hrv.toLocaleString(undefined,{maximumFractionDigits:1})} ms`}</p><small>View last night’s plot ↗</small></button><button type="button" className="journal-health-signal" aria-haspopup="dialog" onClick={()=>setNightView('sleep')} aria-label="View last night’s sleep stages and score"><h3>Sleep</h3><p>{!signals?'Loading…':signals.date!==today?'Not current':signals.sleepScore===null?'Unavailable':`${signals.sleepScore} / 100`}</p><small>Sleep stages & score ↗</small></button></div>
      <DashboardActivity activity={latestActivity} timezone={timezone} active={active} refresh={refresh} distanceUnit={distanceUnit} onDetails={onActivityDetails}/>
      <section className="journal-week" aria-label="This week’s workouts"><div className="journal-week-heading"><h2>This week</h2><a href="#training">Full plan <ArrowRight size={16}/></a></div>
        <div className="journal-week-days">{week.map(day => { const date = new Date(`${day}T12:00:00Z`), items = workouts.filter(w => workoutDate(w, timezone) === day && !['cancelled', 'skipped'].includes(w.completion_status)); return <button type="button" className={day === today ? 'journal-day journal-day--today' : 'journal-day'} key={day} aria-label={`${date.toLocaleDateString(undefined, { timeZone: 'UTC', weekday: 'long', month: 'short', day: 'numeric' })}: ${items.length ? items.map(w => `${w.title}, ${w.completion_status}`).join('; ') : 'No session scheduled'}`} onClick={() => { if (items[0]) setSelected(items[0]); else window.location.hash = 'training'; }}><strong>{date.toLocaleDateString(undefined, { timeZone: 'UTC', weekday: 'short' })}</strong><small>{date.toLocaleDateString(undefined, { timeZone: 'UTC', month: 'short', day: 'numeric' })}</small><SportIcon sport={items[0]?.sport ?? 'rest'} size={23}/>{items.length > 1 && <small>{items.length} sessions</small>}</button>; })}</div>
        {planError && <p className="settings-hint">The week could not refresh. Retry workouts above.</p>}
      </section>
    </div>
    <DashboardNight view={nightView} today={today} timezone={timezone} onClose={()=>setNightView(null)}/>
    <RecentTrainingSummary today={today} timezone={timezone} active={active} refresh={`${refresh}:${revision}`} />
    <dialog ref={dialog} className="journal-workout-dialog" onClose={() => setSelected(null)} aria-labelledby="journal-workout-dialog-title"><div className="journal-dialog-heading"><div><p className="journal-kicker">Your saved workout</p><h2 id="journal-workout-dialog-title">{selected?.title}</h2></div><button type="button" aria-label="Close workout" onClick={() => setSelected(null)}><X size={22}/></button></div>{selected && <><p>{workoutDate(selected, timezone)} · {selected.definition.duration_minutes} min · {selected.completion_status}</p><p>{selected.definition.effort_target?.description}</p><WorkoutLaps definition={selected.definition}/><a className="journal-text-action" href="#training" onClick={() => setSelected(null)}>Open training for editing and feedback <ArrowRight size={18}/></a></>}</dialog>
  </section>;
}
