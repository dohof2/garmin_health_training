"""Validated, provider-neutral local workout prescriptions; no inferred calibration."""
import math
from datetime import date

KINDS=('recovery','endurance','long_endurance','climbing_endurance','long_tempo','tempo','threshold','vo2','short_efforts','sprint','anaerobic')
RATIOS={'recovery':(.35,.5),'endurance':(.55,.7),'long_endurance':(.55,.7),'climbing_endurance':(.65,.75),'long_tempo':(.76,.87),'tempo':(.76,.87),'threshold':(.95,1.0),'vo2':(1.05,1.15),'short_efforts':(1.1,1.3)}
RPE={'recovery':(1,2),'endurance':(2,3),'long_endurance':(2,3),'climbing_endurance':(3,4),'long_tempo':(5,6),'tempo':(5,6),'threshold':(6,7),'vo2':(7,8),'short_efforts':(7,8),'sprint':(9,10),'anaerobic':(9,9)}

# Symmetric MTB tolerance in FTP fractions; the ERG midpoint stays unchanged.
POWER_HALF_WIDTH={'recovery':.15,'endurance':.15,'long_endurance':.15,'climbing_endurance':.125,'long_tempo':.10,'tempo':.10,'threshold':.075,'vo2':.075,'short_efforts':.10}

def power_range(kind, bounds):
 low,high=bounds;mid=(low+high)/2
 half=max((high-low)/2,POWER_HALF_WIDTH[kind])
 return (round(mid-half,6),round(mid+half,6))

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
 if kind in ('sprint','anaerobic'):
  low,high=RPE[kind];return {'type':'perceived_effort','lower':low,'upper':high,'unit':'RPE / 10','source':'effort_prescription','description':'Fast controlled acceleration; keep technique stable and end repetitions if quality drops.' if kind=='sprint' else 'Very hard repeatable effort for the prescribed duration; ease off if technique or repeatability deteriorates. No sprint watts or HR target is inferred from FTP.'}
 c=validate_calibration(brief.get('calibration'));today=today or date.today();ftp=brief.get('ftp_watts')
 confirmed=date.fromisoformat(c['ftp_confirmed_on']) if c['ftp_confirmed_on'] else None
 power=c['power_access'] in ('both','indoor' if indoor else 'outdoor')
 if sport=='cycling' and power and ftp and confirmed and 0<=(today-confirmed).days<=90:
  low,high=power_range(kind,RATIOS[kind]);return {'type':'power','lower':round(ftp*low,2),'upper':round(ftp*high,2),'unit':'W','ftp_watts':ftp,'confirmed_on':confirmed.isoformat(),'source':c['ftp_source']}
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

def endurance(kind,minutes,brief,sport='cycling',indoor=None,today=None,variant=None):
 if indoor is None:indoor=brief.get('workout_location','outdoor')=='indoor'
 if kind not in KINDS:raise ValueError('Unknown endurance prescription')
 if type(minutes) not in (int,float) or not math.isfinite(minutes) or not 10<=minutes<=720:raise ValueError('Workout duration must be 10–720 minutes')
 from .cycling_variants import options
 choices=options(kind);selected=next((v for v in choices if v['id']==variant),None) if variant else None
 if variant and selected is None:raise ValueError('Unknown variant for this workout category')
 requested_kind=kind
 if kind in ('sprint','anaerobic') and sport!='cycling':raise ValueError('Sprint and anaerobic prescriptions currently support cycling only')
 if kind in ('sprint','anaerobic') and minutes<45:kind='endurance'
 total=int(round(minutes*60));warm=900 if kind in ('sprint','anaerobic') else min(600,total//5);cool=600 if kind in ('sprint','anaerobic') else min(300,total//8);steps=[]
 def lap(name,seconds,zone):
  if seconds<=0:return
  t=target(zone,brief,sport,indoor,today)
  fractions=power_range(zone,RATIOS[zone]) if zone in RATIOS else None
  if selected and zone==kind and kind in ('recovery','endurance','long_endurance') and sport=='cycling':
   fractions=power_range(zone,selected['ratios'])
   if t['type']=='power':t={**t,'lower':round(brief['ftp_watts']*fractions[0],2),'upper':round(brief['ftp_watts']*fractions[1],2)}
   elif t['type']=='perceived_effort':t={**t,'lower':selected['rpe'][0],'upper':selected['rpe'][1]}
  steps.append({'power_reference_fractions':{'lower':fractions[0],'upper':fractions[1]} if sport=='cycling' and fractions else None,'name':name,'type':name.lower().replace(' ','_'),'duration_seconds':seconds,'termination':'time','repetitions':1,'target':t,'effort':text(t)+(' · '+t['description'] if zone in ('sprint','anaerobic') else '')})
 if sport=='cycling' and kind in ('endurance','long_endurance','recovery') and brief.get('continuous_endurance'):
  warm=cool=0
 lap('Warm-up',warm,'recovery');remaining=total-warm-cool
 if kind in ('tempo','long_tempo','climbing_endurance','threshold','vo2','short_efforts','sprint','anaerobic'):
  reps,work,recover={'tempo':(2,480,240),'long_tempo':(2,600,300),'climbing_endurance':(3,480,240),'threshold':(2,360,240),'vo2':(3,180,180),'short_efforts':(4,15,180),'sprint':(4,8,240),'anaerobic':(4,30,240)}[kind]
  if selected and selected.get('intervals'):reps,work,recover=selected['intervals']
  if remaining<reps*work+(reps-1)*recover:kind='endurance'
  else:
   for i in range(reps):
    lap(f"{'Sprint' if kind=='sprint' else 'Anaerobic effort' if kind=='anaerobic' else 'Work lap'} {i+1}",work,kind);remaining-=work
    if i<reps-1:lap(f'Recovery {i+1}',recover,'recovery');remaining-=recover
 if remaining:lap('Steady endurance' if kind!='recovery' else 'Gentle recovery',remaining,'recovery' if kind=='recovery' else 'long_endurance' if kind=='long_endurance' else 'endurance')
 lap('Cool-down',cool,'recovery')
 titles={'recovery':'Gentle recovery ride','endurance':'Steady endurance','long_endurance':'Long endurance','climbing_endurance':'Climbing endurance','long_tempo':'Long endurance with tempo','tempo':'Tempo intervals','threshold':'Controlled threshold intervals','vo2':'VO₂ intervals','short_efforts':'Controlled short efforts','sprint':'Sprint technique and power','anaerobic':'Anaerobic capacity intervals'}
 reference_date=validate_calibration(brief.get('calibration'))['ftp_confirmed_on'];reference_today=today or date.today()
 reference_status='undated' if not reference_date else 'future' if date.fromisoformat(reference_date)>reference_today else 'stale' if (reference_today-date.fromisoformat(reference_date)).days>90 else 'usable'
 reference_ftp={'watts':brief.get('ftp_watts'),'measurement_date':reference_date,'source':validate_calibration(brief.get('calibration'))['ftp_source'],'status':reference_status,'advisory_only':True} if sport=='cycling' and brief.get('ftp_watts') else None
 return validate_workout({'variant_id':selected['id'] if selected and kind==requested_kind else None,'variant_label':selected['label'] if selected and kind==requested_kind else None,'sources':[selected['source']] if selected else [],'reference_ftp':reference_ftp,'version':'training-prescription-v2','template_id':'cycling_'+kind if sport=='cycling' else 'running_easy','workout_kind':kind,'sport':sport,'title':titles[kind] if sport=='cycling' else 'Easy conversational run','duration_minutes':total/60,'steps':steps,'effort_target':{'method':steps[0]['target']['type'],'description':'; '.join(f"{s['name']}: {s['effort']}" for s in steps)},'workout_location':'indoor' if indoor else 'outdoor','program_ftp':brief.get('ftp_watts'),'program_goal':brief.get('goal'),'calibration':validate_calibration(brief.get('calibration')),'rationale':['Targets use confirmed calibration when available; otherwise the explicit effort fallback applies.']+(['Dedicated high-intensity work uses effort and repeatability, not watts inferred from FTP. Use a controlled traffic-free setting or suitable trainer; stop the efforts if technique or power quality deteriorates.'] if kind in ('sprint','anaerobic') else [])+(['Insufficient time for the full warm-up, efforts and recovery; replaced with easy endurance rather than compressing sprint/anaerobic recovery.'] if requested_kind in ('sprint','anaerobic') and requested_kind!=kind else [])})


def strength(base,brief,answers,week_index=0,tolerated=False,observed_at=None):
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
  # Two sets in one workout are one exposure, not two tolerated sessions.
  # Inspect the latest sessions before checking RIR so a recent difficult set
  # cannot be ignored in favor of older successful performances.
  from datetime import datetime,timedelta
  by_session={}
  for r in brief.get('strength_performance',[]):
   if r['exercise_id']!=e['id'] or not r.get('workout_id'):continue
   try:recorded_at=datetime.fromisoformat(r.get('recorded_at','').replace('Z','+00:00'))
   except (ValueError,TypeError):continue
   if not recorded_at.tzinfo:continue
   if observed_at and not observed_at-timedelta(days=90)<=recorded_at<=observed_at:continue
   by_session.setdefault(r['workout_id'],[]).append((recorded_at,r))
  recent=sorted(by_session.items(),key=lambda entry:max(at for at,_ in entry[1]))[-2:]
  recorded=[r for _,rows in recent for _,r in rows]
  ready=len(recent)==2 and all(r.get('repetitions_in_reserve') is not None and r['repetitions_in_reserve']>=2 for r in recorded)
  same_load=ready and len({r.get('load_kg') for r in recorded})==1 and (e['equipment'] in ('bodyweight','pull_up_bar','dip_bars') or all(r.get('load_kg') is not None for r in recorded))
  e['progression_evidence']={'completed_sessions':len(recent),'workout_ids':[identifier for identifier,_ in recent],
      'status':'eligible' if tolerated and week_index>0 and ready and same_load else 'hold',
      'reason':'Two recent distinct sessions at the same recorded load with at least two repetitions in reserve are required; recent hard/unknown sets or changed loads hold progression.'}
  if tolerated and week_index>0 and ready and same_load:
   baseline=min(r['repetitions'] for r in recorded);e['repetitions']=min(baseline+1,12) if e['equipment'] not in ('pull_up_bar','dip_bars') else min(e['repetitions'],baseline+1)
   e['last_recorded_load_kg']=recorded[-1].get('load_kg')
   if recorded[-1].get('load_kg') is not None:e['load_target_kg']=recorded[-1]['load_kg']
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


def cycling_dose(availability_minutes,capacity,feedback,today):
 """A conservative app heuristic, not a universal progression percentage or readiness test."""
 from statistics import median
 from datetime import timedelta
 sport=next((row for row in capacity.get('sports',[]) if row['sport']=='cycling'),{})
 recent=[row['minutes'] for row in sport.get('recent_durations',[]) if row['date']>=(today-timedelta(days=28)).isoformat() and row['date']<=today.isoformat() and row['minutes']>=10]
 longs=[minutes for minutes in recent if minutes>=90]
 long_weeks={row['date'][:4]+'-'+str((today-date.fromisoformat(row['date'])).days//7) for row in sport.get('recent_durations',[]) if row['date']>=(today-timedelta(days=28)).isoformat() and row['minutes']>=90}
 baseline=median(longs) if len(longs)>=3 and len(long_weeks)>=2 else median(recent) if len(recent)>=3 else min(recent+[60]) if recent else 60
 feedback=[row for row in feedback if not row.get('updated_at') or str(row['updated_at'])[:10]>=(today-timedelta(days=7)).isoformat()]
 import re
 adverse=any(row.get('pain_or_illness') or (row.get('effort') or 0)>=8 or (row.get('soreness') or 0)>=5 or re.search(r'\b(too hard|exhausted|too tired|could not finish)\b',row.get('notes') or '',re.I) for row in feedback)
 tolerated=[row for row in feedback if row.get('sport')=='cycling' and row.get('completion_status')=='completed' and row.get('effort') is not None and row['effort']<=6 and (row.get('soreness') or 0)<=3 and not row.get('pain_or_illness')]
 # Elapsed plan weeks alone never authorize growth. New recorded rides move this reference over time.
 increment=min(15,baseline*.05) if len(recent)>=3 and len(tolerated)>=2 and not adverse else 0
 target=min(availability_minutes,max(20,round(baseline+increment)))
 from .training_volume import weekly_reference
 reference=weekly_reference(sport.get('recent_durations',[]),today,capacity.get('activity_coverage',{}),180)
 weeks=[week['minutes'] for week in reference['weeks'] if week['minutes'] is not None]
 weekly_reference_minutes=reference['baseline_minutes']
 weekly_cap=max(20,round(weekly_reference_minutes+(min(15,weekly_reference_minutes*.05) if len(weeks)>=2 and len(tolerated)>=2 and not adverse else 0)))
 reason=(f'Recent repeatable cycling duration is about {baseline:g} minutes. '+(f'Tolerated completed cycling feedback permits a cautious {increment:g}-minute increase. ' if increment else 'No calendar-only increase is applied. ')) if recent else 'Recent cycling-duration evidence is limited; use a provisional 60-minute ceiling pending recorded tolerance or clarification. '
 return {'weekly_cap_minutes':weekly_cap,'weekly_reference_minutes':weekly_reference_minutes,'weekly_reference':reference,'recorded_nonempty_weeks':sum(value>0 for value in weeks),'reference_weeks':len(weeks),'minutes':target,'availability_cap_minutes':availability_minutes,'baseline_minutes':baseline,'recent_ride_count':len(recent),'increment_minutes':increment,'rule_version':'cycling-dose-v1','reason':reason+'Availability is a ceiling, not a prescribed ride length.','heuristic':True}


def recovery_policy(readiness,load,feedback,capacity,today):
 """Combine observations without treating a proprietary readiness score as a diagnosis."""
 from datetime import timedelta
 relevant=[row for row in feedback if not row.get('updated_at') or str(row['updated_at'])[:10]>=(today-timedelta(days=7)).isoformat()]
 pain=any(row.get('pain_or_illness') for row in relevant)
 import re
 adverse=any((row.get('effort') or 0)>=8 or (row.get('soreness') or 0)>=5 or re.search(r'\b(too hard|exhausted|too tired|could not finish)\b',row.get('notes') or '',re.I) for row in relevant)
 high_load=bool(load and load.get('high') is not None and load.get('acute') is not None and load['acute']>load['high'])
 current=not readiness.get('date') or readiness.get('date')==today.isoformat()
 if not current:readiness={'score':None,'groups':[]}
 autonomic=next((group for group in readiness.get('groups',[]) if group.get('name')=='autonomic'),{})
 physiology=bool(autonomic.get('hrv_z') is not None and autonomic['hrv_z']<-1.5 or autonomic.get('rhr_z') is not None and autonomic['rhr_z']>1.5)
 sleep=capacity.get('biological',{}).get('sleep_score')
 if sleep and str(sleep.get('recorded_at',''))[:10]>=(today-timedelta(days=1)).isoformat() and sleep.get('value') is not None and sleep['value']<50:physiology=True
 demanding=any(row['date']>=(today-timedelta(days=1)).isoformat() for sport in capacity.get('sports',[]) for row in sport.get('difficulty',{}).get('demanding_sessions',[]))
 score=readiness.get('score');reasons=[]
 if adverse:reasons.append('Recent reported effort or soreness indicates difficulty.')
 if high_load:reasons.append('Recent acute load exceeds its recorded reference range.')
 if physiology:reasons.append('Recent autonomic or sleep observations suggest reduced recovery.')
 if demanding:reasons.append('A demanding recorded session needs recovery space.')
 if score is not None and score<60:reasons.append('The readiness estimate is lower; use it as supporting context rather than an automatic rest rule.')
 level='hold' if pain else 'recovery' if adverse or high_load and physiology or demanding and physiology else 'easy' if high_load or physiology or demanding or score is not None and score<60 else 'normal'
 positive=sum(row.get('completion_status')=='completed' and row.get('effort') is not None and row['effort']<=6 and (row.get('soreness') or 0)<=3 and not row.get('pain_or_illness') for row in relevant)>=2
 history=next((sport for sport in capacity.get('sports',[]) if sport['sport']=='cycling'),{})
 consistent_weeks={date.fromisoformat(row['date']).isocalendar()[:2] for row in history.get('recent_durations',[]) if (today-timedelta(days=28)).isoformat()<=row['date']<=today.isoformat()}
 quality=level=='normal' and (score is not None or history.get('activity_count',0)>=6 and (len(consistent_weeks)>=3 or positive))
 return {'level':level,'quality_allowed':quality,'readiness_score':score,'readiness_missing':score is None,'adverse_feedback':adverse,'high_load':high_load,'physiology_concern':physiology,'recent_demanding':demanding,'reasons':reasons,'rule_version':'recovery-context-v1','note':'Provisional app guidance using recorded workload, tolerance and recovery together; no score alone proves readiness or illness.'}


def advanced_cycling_eligible(c,now,experience,week_index,phase,quality_allowed):
 # Category access follows recovery and the block, without calendar or feedback quotas.
 return quality_allowed and phase not in ('Recovery / review','Freshen up','Post-event recovery','Race week','Outside plan')

def cycling_mix(brief):
 import re
 goal=brief.get('goal');event=brief.get('event_name','').lower()
 short_power=goal=='race' and bool(re.search(r'\b(criterium|crit|cyclocross|xc|cross.country|short.power|repeated attacks|punchy)\b',event))
 focus='short_power' if short_power else 'endurance' if goal=='endurance' else 'sustained_power' if goal in ('ftp','race') else 'general'
 cycles={
  'sustained_power':('threshold','tempo','vo2','sprint','threshold','anaerobic'),
  'endurance':('tempo','threshold','tempo','sprint','vo2','anaerobic'),
  'short_power':('threshold','vo2','tempo','sprint','anaerobic','sprint','anaerobic'),
  'general':('tempo','threshold','vo2','sprint','tempo','anaerobic')}
 cycle=cycles[focus]
 return {'focus':focus,'quality_session_limit':2,'quality_rotation':list(cycle),'quality_session_weights':{kind:cycle.count(kind) for kind in dict.fromkeys(cycle)},'rotation_length':len(cycle),'note':'The mix emphasizes your goal while retaining base, sustained-power and short-power work across build weeks. These are starting guidelines, adjusted for completed training and recovery. Counts refer to quality sessions, not percentages of riding time. Aim for two interval rides and one base ride, plus an optional long ride when it fits per normal week. Recent completed riding, recovery, block and available time can reduce this target. Sprint and anaerobic work have no minimum programme week or completed-feedback quota; recovery/taper weeks omit intervals.'}

def cycling_quality_kind(week_index,advanced_ready,brief=None):
 cycle=cycling_mix(brief or {'goal':'ftp'})['quality_rotation']
 requested=cycle[(week_index-week_index//4)%len(cycle)]
 return requested if requested not in ('sprint','anaerobic') or advanced_ready else 'short_efforts'
