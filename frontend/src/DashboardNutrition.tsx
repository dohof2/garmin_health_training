import {useEffect, useState} from 'react';
import {api} from './GraphCanvas';
import InfoPopover from './InfoPopover';

type Nutrient='calories_kcal'|'protein_grams'|'carbohydrate_grams'|'fat_grams';
type Intake={date:string;totals:Record<Nutrient,{known_total:number;missing_items:number}>;target:Record<Nutrient,number|null>|null};
const macros=[['protein_grams','Protein'],['carbohydrate_grams','Carbs'],['fat_grams','Fat']] as const;
const dayIn=(timezone:string)=>new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const amount=(value:number)=>new Intl.NumberFormat(undefined,{maximumFractionDigits:0}).format(value);
const fraction=(value:number,target:number|null|undefined)=>target!=null&&target>0?Math.min(1,Math.max(0,value/target)):0;

export default function DashboardNutrition({timezone,refresh,active}:{timezone:string;refresh?:string|number;active:boolean}) {
  const [day,setDay]=useState(()=>dayIn(timezone));
  const [revision,setRevision]=useState(0);
  const [data,setData]=useState<Intake|null>(null),[error,setError]=useState('');
  useEffect(()=>{
    const changed=()=>setRevision(value=>value+1);
    const dateChanged=()=>setDay(dayIn(timezone));
    const focused=()=>{dateChanged();changed();};
    const timer=window.setInterval(()=>{dateChanged();if(active&&document.visibilityState!=='hidden')changed();},30000);dateChanged();
    window.addEventListener('nutrition-log-changed',changed);window.addEventListener('focus',focused);
    return()=>{window.clearInterval(timer);window.removeEventListener('nutrition-log-changed',changed);window.removeEventListener('focus',focused);};
  },[timezone,active]);
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();setError('');
    api<Intake>(`/api/nutrition/day?day=${day}&timezone=${encodeURIComponent(timezone)}`,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setData(result);})
      .catch(error=>{if(!controller.signal.aborted)setError(error instanceof Error?error.message:'Could not load nutrition');});
    return()=>controller.abort();
  },[day,timezone,refresh,revision,active]);
  const calories=data?.totals.calories_kcal, target=data?.target?.calories_kcal;
  const hasTarget=target!=null&&target>0;
  return <section className="dashboard-nutrition" aria-labelledby="dashboard-nutrition-title">
    <div className="dashboard-nutrition-heading"><h2 id="dashboard-nutrition-title">Nutrition <InfoPopover title="Today's nutrition"><p>Today's logged food compared with your saved daily targets. The calorie bar ends at the calorie target; any excess is stated separately. Missing nutrient values make totals partial. Goals and the meal log use the same Nutrition data.</p></InfoPopover></h2><a href="#nutrition">Open meal log →</a></div>
    {error?<p role="alert">{error} <button type="button" onClick={()=>setRevision(value=>value+1)}>Retry</button></p>:!data||data.date!==day?<p role="status">Loading today’s nutrition…</p>:<>
      <div className="nutrition-calorie-label"><strong>{calories?.missing_items?'At least ':''}{amount(calories?.known_total??0)} kcal</strong><span>{hasTarget?`of ${amount(target)} kcal`:'Calorie target not set'}</span></div>
      <div className="nutrition-calorie-track" role={hasTarget?'progressbar':'img'} aria-label="Today's calories" aria-valuemin={hasTarget?0:undefined} aria-valuemax={hasTarget?target:undefined} aria-valuenow={hasTarget?Math.min(target,calories?.known_total??0):undefined} aria-valuetext={`${calories?.missing_items?'At least ':''}${amount(calories?.known_total??0)} kcal consumed${hasTarget?` of ${amount(target)} kcal target`:'. No calorie target set'}`}><div style={{width:`${fraction(calories?.known_total??0,target)*100}%`}}/></div>
      {(calories?.missing_items??0)>0&&<p className="nutrition-summary-note">Partial total · some foods have no calorie value.</p>}
      {hasTarget&&(calories?.known_total??0)>target&&<p className="nutrition-summary-note">{amount((calories?.known_total??0)-target)} kcal above target{calories?.missing_items?' or more':''}</p>}
      <div className="nutrition-macro-dials">{macros.map(([key,label])=>{
        const total=data.totals[key], goal=data.target?.[key], hasGoal=goal!=null&&goal>0;
        return <div className="nutrition-mini-dial" key={key}>
          <svg viewBox="0 0 100 100" role="img" aria-label={`${label}: ${total.missing_items?'at least ':''}${amount(total.known_total)} grams${hasGoal?` of ${amount(goal)} grams target`:'. Target not set'}`}>
            <circle className="nutrition-dial-track" cx="50" cy="50" r="40"/>
            <circle className="nutrition-dial-value" cx="50" cy="50" r="40" pathLength="100" strokeDasharray={`${fraction(total.known_total,goal)*100} 100`} transform="rotate(-90 50 50)"/>
            <text x="50" y="54" textAnchor="middle">{total.missing_items?'≥':''}{amount(total.known_total)}<tspan className="nutrition-dial-unit"> g</tspan></text>
          </svg><strong>{label}</strong><span>{hasGoal?`/ ${amount(goal)} g`:'No target'}{total.missing_items?' · partial':''}</span>
        </div>;
      })}</div>
    </>}
  </section>;
}
