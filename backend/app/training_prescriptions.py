"""Validated, provider-neutral local workout prescriptions; no inferred calibration."""
import math
from datetime import date

KINDS=('recovery','endurance','long_endurance','climbing_endurance','long_tempo','tempo','threshold','vo2','short_efforts')
RATIOS={'recovery':(.35,.5),'endurance':(.55,.7),'long_endurance':(.6,.75),'climbing_endurance':(.65,.75),'long_tempo':(.76,.87),'tempo':(.76,.87),'threshold':(.9,.95),'vo2':(1.05,1.15),'short_efforts':(1.1,1.3)}
RPE={'recovery':(1,2),'endurance':(2,3),'long_endurance':(2,4),'climbing_endurance':(3,4),'long_tempo':(5,6),'tempo':(5,6),'threshold':(6,7),'vo2':(7,8),'short_efforts':(7,8)}

def validate_calibration(value):
 if value is None:value={}
 if not isinstance(value,dict) or set(value)-{'power_access','ftp_confirmed_on','ftp_source','hr_sensor','hr_zones','hr_confirmed_on','hr_source'}:raise ValueError('Unsupported calibration fields')
 v={'power_access':'unknown','ftp_confirmed_on':None,'ftp_source':'user_confirmed','hr_sensor':None,'hr_zones':{},'hr_confirmed_on':None,'hr_source':'user_confirmed_zones',**value}
 if v['power_access'] not in ('unknown','none','indoor','outdoor','both'):raise ValueError('Power access must be none, indoor, outdoor or both')
 if v['hr_sensor'] is not None and type(v['hr_sensor']) is not bool:raise ValueError('Confirm HR sensor availability')
 for key in ('ftp_confirmed_on','hr_confirmed_on'):
  if v[key] is not None:
   if not isinstance(v[key],str):raise ValueError('Calibration confirmation dates must be YYYY-MM-DD')
   date.fromisoformat(v[key])
 for key in ('ftp_source','hr_source'):
  if not isinstance(v[key],str) or len(v[key])>100:raise ValueError('Invalid calibration source')
 if not isinstance(v['hr_zones'],dict) or set(v['hr_zones'])-set(KINDS):raise ValueError('Use named workout HR zones')
 for limits in v['hr_zones'].values():
  if not isinstance(limits,list) or len(limits)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or not 30<=n<=230 for n in limits) or limits[0]>limits[1]:raise ValueError('HR zones need ordered lower/upper bpm bounds')
 return v

def questions(brief,sports):
 c=validate_calibration(brief.get('calibration'));q=[]
 if 'cycling' in sports and c['power_access']=='unknown':q.append('Can you use a power meter indoors, outdoors, both, or neither?')
 if c['power_access'] not in ('unknown','none') and not brief.get('ftp_watts'):q.append('What is your confirmed cycling FTP, and when was it measured or confirmed?')
 if brief.get('ftp_watts') and not c['ftp_confirmed_on']:q.append('When was your FTP last measured or confirmed?')
 if c['hr_sensor'] is None:q.append('Do you have an HR sensor available for these workouts? If you want HR targets, provide your confirmed sport-specific HR zones.')
 if c['power_access']=='indoor' and brief.get('workout_location','outdoor')=='outdoor':q.append('Power is available indoors only. Should the prescribed rides be indoor, or use an HR/effort target outdoors?')
 if c['hr_sensor'] and not c['hr_zones']:q.append('What are your confirmed sport-specific HR ranges? FTP does not determine HR zones.')
 return q

def target(kind,brief,sport,indoor=False,today=None):
 c=validate_calibration(brief.get('calibration'));today=today or date.today();ftp=brief.get('ftp_watts')
 confirmed=date.fromisoformat(c['ftp_confirmed_on']) if c['ftp_confirmed_on'] else None
 power=c['power_access'] in ('both','indoor' if indoor else 'outdoor')
 if sport=='cycling' and power and ftp and confirmed and 0<=(today-confirmed).days<=90:
  low,high=RATIOS[kind];return {'type':'power','lower':round(ftp*low,2),'upper':round(ftp*high,2),'unit':'W','ftp_watts':ftp,'confirmed_on':confirmed.isoformat(),'source':c['ftp_source']}
 hrdate=date.fromisoformat(c['hr_confirmed_on']) if c['hr_confirmed_on'] else None
 if c['hr_sensor'] and kind in c['hr_zones'] and hrdate and 0<=(today-hrdate).days<=180:
  low,high=c['hr_zones'][kind];return {'type':'heart_rate','lower':low,'upper':high,'unit':'bpm','confirmed_on':hrdate.isoformat(),'source':c['hr_source']}
 low,high=RPE[kind];return {'type':'perceived_effort','lower':low,'upper':high,'unit':'RPE / 10','source':'calibrated_sensor_unavailable','description':'Use conversational effort for easy work; do not chase an uncalibrated numeric sensor target.'}

def text(t):return f"{t['lower']:g}–{t['upper']:g} {t['unit']}"

def validate_workout(w):
 steps=w.get('steps',[])
 if not steps:return w
 total=0
 for step in steps:
  seconds=step.get('duration_seconds');repeat=step.get('repetitions',1)
  if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=0 or type(repeat) is not int or not 1<=repeat<=50:raise ValueError('Workout laps require positive time and valid repetition counts')
  t=step.get('target')
  if not isinstance(t,dict) or t.get('type') not in ('power','heart_rate','perceived_effort') or any(type(t.get(k)) not in (int,float) or not math.isfinite(t[k]) for k in ('lower','upper')) or t['lower']>t['upper']:raise ValueError('Invalid workout lap target')
  total+=seconds*repeat
 if abs(total-w['duration_minutes']*60)>.01:raise ValueError('Lap durations do not match the total workout duration')
 return w

def endurance(kind,minutes,brief,sport='cycling',indoor=None,today=None):
 if indoor is None:indoor=brief.get('workout_location','outdoor')=='indoor'
 if kind not in KINDS:raise ValueError('Unknown endurance prescription')
 if type(minutes) not in (int,float) or not math.isfinite(minutes) or not 10<=minutes<=720:raise ValueError('Workout duration must be 10–720 minutes')
 total=int(round(minutes*60));warm=min(600,total//5);cool=min(300,total//8);steps=[]
 def lap(name,seconds,zone):
  if seconds<=0:return
  t=target(zone,brief,sport,indoor,today);steps.append({'name':name,'type':name.lower().replace(' ','_'),'duration_seconds':seconds,'termination':'time','repetitions':1,'target':t,'effort':text(t)})
 lap('Warm-up',warm,'recovery');remaining=total-warm-cool
 if kind in ('tempo','long_tempo','climbing_endurance','threshold','vo2','short_efforts'):
  reps,work,recover={'tempo':(2,480,240),'long_tempo':(2,600,300),'climbing_endurance':(3,480,240),'threshold':(2,360,240),'vo2':(3,180,180),'short_efforts':(4,15,180)}[kind]
  if remaining<reps*work+(reps-1)*recover:kind='endurance'
  else:
   for i in range(reps):
    lap(f'Work lap {i+1}',work,kind);remaining-=work
    if i<reps-1:lap(f'Recovery {i+1}',recover,'recovery');remaining-=recover
 if remaining:lap('Steady endurance' if kind!='recovery' else 'Gentle recovery',remaining,'recovery' if kind=='recovery' else 'long_endurance' if kind=='long_endurance' else 'endurance')
 lap('Cool-down',cool,'recovery')
 titles={'recovery':'Gentle recovery ride','endurance':'Steady endurance','long_endurance':'Long endurance','climbing_endurance':'Climbing endurance','long_tempo':'Long endurance with tempo','tempo':'Tempo intervals','threshold':'Controlled threshold intervals','vo2':'VO₂ intervals','short_efforts':'Controlled short efforts'}
 return validate_workout({'version':'training-prescription-v2','template_id':'cycling_'+kind if sport=='cycling' else 'running_easy','workout_kind':kind,'sport':sport,'title':titles[kind] if sport=='cycling' else 'Easy conversational run','duration_minutes':total/60,'steps':steps,'effort_target':{'method':steps[0]['target']['type'],'description':'; '.join(f"{s['name']}: {s['effort']}" for s in steps)},'workout_location':'indoor' if indoor else 'outdoor','program_ftp':brief.get('ftp_watts'),'program_goal':brief.get('goal'),'calibration':validate_calibration(brief.get('calibration')),'rationale':['Targets use confirmed calibration when available; otherwise the explicit effort fallback applies.']})


def strength(base,brief,answers,week_index=0,tolerated=False):
 role=brief.get('strength_role') or ('primary' if answers.get('priority')=='strength' else 'secondary')
 purpose=brief.get('strength_purpose') or ('strength_development' if role=='primary' else 'general_fitness')
 result={**base,'version':'training-prescription-v2','strength_role':role,'strength_purpose':purpose,'exercises':[dict(e) for e in base['exercises']]}
 if not set(answers['equipment']) & {'bands','gym'}:
  from .training import EXERCISES
  supported=[];replaced=[]
  for exercise in result['exercises']:
   key={'pull_up_bar':'pull_up_reps','dip_bars':'dip_reps'}.get(exercise['equipment'])
   if key and brief.get('strength_capacity',{}).get(key)==0:
    replaced.append(exercise['name'])
    alternative=next((candidate for candidate in EXERCISES if candidate['movement']==exercise['movement'] and candidate['equipment'] in answers['equipment'] and candidate['equipment'] not in ('pull_up_bar','dip_bars') and candidate['movement'] not in answers.get('blocked_movements',[])),None)
    if alternative:supported.append(dict(alternative))
   else:supported.append(exercise)
  if replaced:
   result['exercises']=supported
   result['rationale']=list(result.get('rationale',[]))+['Unassisted capacity is zero for '+', '.join(replaced)+'. Use available supported alternatives; unsupported bar exercises are omitted without inventing assisted equipment.']
 for e in result['exercises']:
  if e['equipment'] in ('pull_up_bar','dip_bars'):
   key='pull_up_reps' if e['equipment']=='pull_up_bar' else 'dip_reps';capacity=brief.get('strength_capacity',{}).get(key)
   if capacity is None:raise ValueError('Confirm comfortable pull-up/dip repetitions before prescribing bar exercises')
   if capacity==0:
    if not set(answers['equipment']) & {'bands','gym'}:raise ValueError('Unassisted repetitions are zero; confirm assisted equipment or select an alternative movement')
    e['name']='Assisted '+('pull-ups' if key=='pull_up_reps' else 'dips');e['repetitions']=5
   else:e['repetitions']=max(1,min(5,capacity-2))
  else:e['repetitions']=6 if purpose=='strength_development' else 10 if purpose=='cycling_support' else 8
  e['sets']=1 if answers['experience']['strength']=='new' else 3 if role=='primary' else 2
  recorded=[r for r in brief.get('strength_performance',[]) if r['exercise_id']==e['id'] and r.get('repetitions_in_reserve') is not None and r['repetitions_in_reserve']>=2]
  if tolerated and week_index>0 and len(recorded)>=2:
   baseline=min(r['repetitions'] for r in recorded[-2:]);e['repetitions']=min(baseline+1,12) if e['equipment'] not in ('pull_up_bar','dip_bars') else min(e['repetitions'],baseline+1)
   e['last_recorded_load_kg']=recorded[-1]['load_kg']
   if recorded[-1]['load_kg'] is not None:e['load_target_kg']=recorded[-1]['load_kg']
  e['rest_seconds']=120 if role=='primary' else 90;e['load']='Self-selected load with 2–3 repetitions in reserve; record actual load/repetitions to guide progression'
 if purpose=='cycling_support':
  preferred=('squat','hinge','core','pull','push');result['exercises'].sort(key=lambda e:preferred.index(e['movement']))
 result['title']={'cycling_support':'Cycling-support strength','strength_development':'Primary strength development','general_fitness':'General-fitness strength'}[purpose]
 budget=result['duration_minutes']*60-300;selected=[]
 for exercise in result['exercises']:
  cost=exercise['sets']*(60+exercise['rest_seconds'])
  if sum(e['sets']*(60+e['rest_seconds']) for e in selected)+cost<=budget:selected.append(exercise)
 if len(selected)<2:raise ValueError('Increase strength session time to fit at least two movements and recovery')
 result['exercises']=selected;result['rationale']+=['Role: '+role+'; purpose: '+purpose+'.','Progression uses recorded completion, load/repetitions and effort; no maximal strength is inferred.']
 return result
