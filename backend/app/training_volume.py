"""Shared sport-specific completed-volume estimates. Product heuristics, not fitness tests."""
import json
from datetime import date,datetime,timedelta,timezone
from statistics import median, mean
from pathlib import Path
from zoneinfo import ZoneInfo
from .training_constraints import SPORTS,capacity,optional_cap,resolve
POLICY_VERSION='sport-volume-v4-week-reference'
CYCLING_GROWTH_LIMIT=.20
PROVISIONAL={'cycling':180,'running':90,'strength':90,'hiking':120,'other':60}
REDUCTIONS={'elevated':.7,'recovery':.7,'easy':.85}

def sport_of(kind):
 kind=kind.lower()
 if 'cycl' in kind or 'bik' in kind:return 'cycling'
 if 'run' in kind:return 'running'
 if 'hik' in kind:return 'hiking'
 if 'strength' in kind or 'weight_training' in kind:return 'strength'
 return 'other'

def weekly_reference(records,today,coverage,provisional):
 """Four completed rolling weeks; missing coverage is not a zero-training week."""
 weeks=[]
 for offset in range(4):
  end=today-timedelta(days=offset*7+1);start=end-timedelta(days=6)
  values=[row['minutes'] for row in records if start.isoformat()<=row['date']<=end.isoformat()]
  known=(coverage.get('coverage_start') or '9999')<=start.isoformat() and (coverage.get('coverage_end') or '')>=end.isoformat()
  weeks.append({'starts_on':start.isoformat(),'ends_on':end.isoformat(),'minutes':round(sum(values),1) if values or known else None,'coverage':'covered' if known else 'partial' if values else 'unknown'})
 observed=[week['minutes'] for week in weeks if week['minutes'] is not None]
 baseline=mean(observed) if len(observed)>=2 else min(observed[0],provisional) if observed else provisional
 return {'baseline_minutes':baseline,'weeks':weeks,'weeks_used':len(observed),'method':'mean_of_last_four_completed_weeks','provisional':len(observed)<2,'coverage_complete':all(week['coverage']=='covered' for week in weeks)}

def cycling_increment(baseline,observed_weeks,tolerated_sessions,adverse,load_status,rising,recovery_week=False):
 # A ceiling conditional on recorded tolerance, never a calendar-driven promise of improvement.
 if recovery_week or observed_weeks<2 or tolerated_sessions<2 or adverse or rising or load_status not in ('normal',):return 0
 return baseline*CYCLING_GROWTH_LIMIT

def estimates(c,answers,brief,today,tz):
 # Keep a week's completed-volume reference stable as its weekdays elapse.
 # Recovery/load and tolerance below still use current observations.
 anchor=date.fromisoformat(brief['program_start']) if brief.get('program_start') else today-timedelta(days=today.weekday())
 planning_day=date.fromisoformat(brief.get('_planning_day') or today.isoformat())
 week_start=anchor+timedelta(weeks=(planning_day-anchor).days//7)
 reference_day=min(anchor+timedelta(weeks=(today-anchor).days//7),week_start)
 days=resolve(answers,brief)['days'];begin=today-timedelta(days=42);records=[];activity_ids=set()
 for row in c.execute("SELECT id,activity_type,started_at,duration_seconds FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND started_at>=?",(begin.isoformat(),)):
  try:day=datetime.fromisoformat(row['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date()
  except (TypeError,ValueError):continue
  if begin<=day<=today and row['duration_seconds'] and row['duration_seconds']>0:
   records.append({'date':day.isoformat(),'sport':sport_of(row['activity_type']),'minutes':row['duration_seconds']/60,'source':'recorded_activity'});activity_ids.add(row['id'])
 completions=[dict(row) for row in c.execute("SELECT f.*,w.sport,w.completion_status,w.scheduled_for,w.definition_json FROM training_feedback f JOIN planned_workouts w ON w.id=f.workout_id WHERE w.scheduled_for>=?",(begin.isoformat(),))]
 feedback=[row for row in completions if str(row.get('updated_at',''))[:10]>=(today-timedelta(days=7)).isoformat() and str(row.get('updated_at',''))[:10]<=today.isoformat()]
 for row in completions:
  if row['completion_status']!='completed' or row.get('activity_id') in activity_ids:continue
  day=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat();minutes=json.loads(row['definition_json']).get('duration_minutes',0)
  if begin.isoformat()<=day<=today.isoformat() and not any(item['sport']==row['sport'] and item['date']==day and abs(item['minutes']-minutes)<=max(10,minutes*.15) for item in records):records.append({'date':day,'sport':row['sport'],'minutes':minutes,'source':'reported_completion'})
 coverage_row=c.execute("SELECT coverage_start,coverage_end FROM sync_checkpoints WHERE data_type='activities'").fetchone();coverage=dict(coverage_row) if coverage_row else {}
 from .training_load_charts import daily_rows
 path=Path(c.execute('PRAGMA database_list').fetchone()['file']);loads=[row for row in daily_rows(path) if (today-timedelta(days=14)).isoformat()<=row['date']<=today.isoformat()];latest=loads[-1] if loads else None
 fresh=bool(latest and latest['date']>=(today-timedelta(days=3)).isoformat())
 elevated=bool(fresh and latest.get('acute') is not None and latest.get('high') is not None and latest['acute']>latest['high'])
 rising=bool(fresh and len(loads)>=3 and latest.get('acute') is not None and loads[-3].get('acute') is not None and latest['acute']>loads[-3]['acute']*1.05)
 chronic_rising=bool(fresh and len(loads)>=3 and latest.get('chronic') is not None and loads[-3].get('chronic') is not None and latest['chronic']>loads[-3]['chronic'])
 load_status='missing' if not latest else 'stale' if not fresh else 'elevated' if elevated else 'rising' if rising else 'normal';result={}
 for sport in SPORTS:
  available=capacity(days,sport)
  if available<=0 and sport not in answers.get('sports',[]):continue
  selected=[row for row in records if row['sport']==sport]
  reference=weekly_reference(selected,reference_day,coverage,PROVISIONAL[sport]);reference['as_of']=reference_day.isoformat();weeks=reference['weeks']
  observed=[week['minutes'] for week in weeks if week['minutes'] is not None];baseline=reference['baseline_minutes']
  if sport=='strength' and not selected:baseline=PROVISIONAL[sport]
  tolerance=[row for row in feedback if row['sport']==sport and row['completion_status']=='completed' and row.get('effort') is not None and row['effort']<=6 and (row.get('soreness') or 0)<=3 and not row.get('pain_or_illness')]
  adverse=any(row['sport']==sport and (row.get('pain_or_illness') or (row.get('effort') or 0)>=8 or (row.get('soreness') or 0)>=5) for row in feedback)
  increment=min(5,baseline*.03) if sport=='running' and len(observed)>=3 and len(tolerance)>=3 and chronic_rising and not rising and not adverse and load_status not in ('stale','elevated') else 0
  recovery_week=False
  if brief.get('program_start'):
   from .training_coach import roadmap
   planning_day=date.fromisoformat(brief.get('_planning_day') or today.isoformat())
   block=next((row for row in roadmap(brief,date.fromisoformat(brief['program_start']),answers) if date.fromisoformat(row['starts_on'])<=planning_day<date.fromisoformat(row['starts_on'])+timedelta(days=7)),None)
   recovery_week=bool(block and block['phase'] in ('Recovery / review','Freshen up','Post-event recovery','Race week'))
  if sport=='cycling':increment=cycling_increment(baseline,len(observed),len(tolerance),adverse or answers.get('pain_or_illness',False),load_status,rising,recovery_week)
  estimate=max(20 if sport=='cycling' else 15,round((baseline+increment)*(REDUCTIONS['recovery'] if adverse or elevated else 1)))
  cap,cap_source=optional_cap(answers,sport);effective=min(available,cap if cap is not None else 5040,estimate)
  durations=[row['minutes'] for row in selected if row['date']>=(today-timedelta(days=28)).isoformat()];longs=[minutes for minutes in durations if minutes>=90] if sport=='cycling' else durations
  long_weeks={date.fromisoformat(row['date']).isocalendar()[:2] for row in selected if row['date']>=(today-timedelta(days=28)).isoformat() and row['minutes']>=90}
  long=min(estimate,round(median(longs) if len(longs)>=3 and (sport!='cycling' or len(long_weeks)>=2) else median(durations) if len(durations)>=3 else min(durations+[60 if sport=='cycling' else 30])))
  if sport=='strength' and not selected:long=min(30,estimate)
  result[sport]={'policy_version':POLICY_VERSION,'estimate_minutes':estimate,'effective_ceiling_minutes':effective,'availability_ceiling_minutes':available,'optional_cap_minutes':cap,'cap_source':cap_source,'baseline_minutes':baseline,'weekly_reference':reference,'increment_minutes':increment,'long_session_minutes':long,'evidence_window':{'start':begin.isoformat(),'end':today.isoformat()},'weeks':weeks,'recorded_activity_count':len(selected),'status':'history_based' if len(observed)>=2 else 'provisional','load':{'status':load_status,'latest':latest,'scope':'overall_mixed_sport','chronic_rising':chronic_rising,'note':'Recorded load is not converted into sport minutes or split between sports.'},'progression':{'maximum_increase_percent':20 if sport=='cycling' else None,'reference':'completed_four_week_average','recovery_week':recovery_week,'requires_recorded_tolerance':True},'factors':{'adverse_feedback':adverse,'tolerated_completions':len(tolerance),'reduction':REDUCTIONS['recovery'] if adverse or elevated else 1},'rationale':'Weekly baseline uses the average of up to four completed seven-day periods, excluding today; unknown weeks are not counted as zero. Available minutes and optional caps are ceilings. Completed sport-specific volume and tolerance determine this provisional estimate; Cycling can add up to 20% above this baseline only with tolerated completions and normal load, never in recovery/taper weeks; elapsed plan weeks alone do not cause growth.'}
 return result
