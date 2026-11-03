"""Reviewed, explicit set-count changes across the active strength programme."""
import copy,hashlib,json,math,re
from datetime import datetime
from zoneinfo import ZoneInfo
from .database import connect
from .training import _context,_preferences,encoded
from .training_constraints import optional_cap,day_limit


def sets_request(message):
 text=message.lower()
 count=re.search(r'\b(\d+)\s+sets?\b',text)
 broad=re.search(r'\b(all|every|each)\b|from each|of each',text)
 if not count or not broad or not re.search(r'\b(strength|strengh|strntgh|exercises?|workout)\b',text):return None
 if re.search(r"\b(don't|do not|without|what (?:is|are|does))\b",text):return None
 return int(count[1])


def apply_policy(definition,policy,phase=None):
 result=copy.deepcopy(definition)
 if result.get('sport')!='strength' or phase in ('Recovery / review','Race week','Freshen up','Post-event recovery'):return result
 for exercise in result.get('exercises',[]):exercise['sets']=max(exercise['sets'],policy['sets'])
 if policy.get('reference_total_sets') and {e['id']:e['repetitions'] for e in result.get('exercises',[])}==policy.get('reference_repetitions'):
  result['duration_minutes']=max(1,math.ceil(policy['duration_reference_minutes']*sum(e['sets'] for e in result['exercises'])/policy['reference_total_sets']))
 result.update(user_adjusted=True,strength_set_policy=policy)
 return result


def propose(message,program,path,now,*,selected_id=None):
 count=sets_request(message)
 if count is None:return None
 base={'tool':'propose_training_adjustment','kind':'adaptation','status':'needs_input','changes':{},'adjustments':[],'request':message}
 def reject(reason):return {**base,'message':reason}
 if not 1<=count<=5:return reject('Choose 1–5 sets per exercise; larger changes need a separate progression review.')
 from .active_training import _program_workouts
 from .training_prescriptions import validate_workout
 tz=program['state']['timezone'];today=now.astimezone(ZoneInfo(tz)).date()
 with connect(path) as c:
  context=_context(c,now,timezone_name=tz);prefs=_preferences(c)
  rows=_program_workouts(c,program['plan_id'])
  completed=[]
  for row in rows:
   if row['sport']!='strength' or row['completion_status']!='completed':continue
   feedback=c.execute('SELECT activity_id,pain_or_illness,soreness FROM training_feedback WHERE workout_id=?',(row['id'],)).fetchone()
   if not feedback or feedback['pain_or_illness'] or (feedback['soreness'] or 0)>=5:continue
   activity=c.execute('SELECT duration_seconds FROM activities WHERE id=? AND deleted_at IS NULL',(feedback['activity_id'],)).fetchone()
   if activity and activity['duration_seconds']:completed.append((row,activity['duration_seconds']/60))
  selected=[]
  for row in rows:
   day=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()
   if row['sport']=='strength' and row['completion_status']=='planned' and day>=today and (not selected_id or row['id']==selected_id):selected.append(row)
  if not selected:return reject('There is no upcoming strength session in the active plan to adjust.')
  if context['answers'].get('pain_or_illness') or any(feedback.get('pain_or_illness') for feedback in context.get('recent_feedback',[])) or re.search(r'\b(pain|injured|fever|sick)\b',message,re.I):return reject('Record and review the pain or illness before increasing strength sets.')
  if not completed:return reject('Link a completed strength session first so this set increase has a recorded baseline.')
  previous,minutes=sorted(completed,key=lambda item:item[0]['scheduled_for'])[-1]
  old=json.loads(previous['definition_json']);old_sets=sum(e['sets'] for e in old.get('exercises',[]))
  changes=[]
  for row in selected:
   definition=json.loads(row['definition_json']);exercises=definition.get('exercises',[])
   if not exercises:return reject('The selected strength session has no exercise prescription to update.')
   if any(count>exercise['sets']+1 for exercise in exercises):return reject('Increase at most one set per exercise in this review; keep larger changes for recorded progression.')
   managed=c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND verified_hash IS NOT NULL',(row['id'],)).fetchone()
   if row['publish_status'] not in ('local','published','update_needed') or row['publish_status']!='local' and not managed or definition.get('review_hold') or definition.get('fixed_commitment'):
    return reject('An upcoming strength session has a review hold or unresolved Garmin send. Resolve it before changing its sets.')
   if datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()==today:
    from .readiness import readiness_history
    readiness=readiness_history(today,1,tz,path,now=now)['latest']
    if readiness['score'] is None or readiness['score']<50:return reject('Today is a recovery-focus day. This progression can start with the next future strength session after recovery.')
   replacement=copy.deepcopy(definition)
   for exercise in replacement['exercises']:exercise['sets']=count
   # Compare only the same exercise/repetition prescription, with unchanged loads.
   comparable=old_sets and {e['id']:e['repetitions'] for e in old.get('exercises',[])}=={e['id']:e['repetitions'] for e in exercises}
   estimate=max(1,math.ceil(minutes*sum(e['sets'] for e in replacement['exercises'])/old_sets)) if comparable else definition['duration_minutes']
   day=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()
   if estimate>day_limit(context['answers']['week_schedule'],day.weekday()):return reject(f'Two-set timing needs about {estimate} minutes, beyond the saved availability for {day}. Confirm more time for that day first.')
   replacement.update(duration_minutes=estimate,user_adjusted=True)
   if selected_id:replacement.pop('strength_set_policy',None)
   else:replacement['strength_set_policy']={'sets':count,'duration_reference_minutes':round(minutes,2),'reference_workout_id':previous['id'],'reference_total_sets':old_sets,'reference_repetitions':{e['id']:e['repetitions'] for e in old.get('exercises',[])}}
   validate_workout(replacement)
   changes.append({'workout_id':row['id'],'expected_revision':row['revision'],'title':row['title'],'date':day.isoformat(),
    'summary':[f"{e['name']}: {before['sets']} → {count} sets; reps, rest and load retained" for e,before in zip(replacement['exercises'],exercises)]+[f'Estimated duration: {estimate} minutes, using the recorded {minutes:.1f}-minute session as a timing reference.'],
    'changes':{'definition':replacement}})
  weeks={}
  for item in changes:
   day=datetime.fromisoformat(item['date']).date();week=day.toordinal()-day.weekday();weeks[week]=weeks.get(week,0)+item['changes']['definition']['duration_minutes']
  if selected_id:
   for peer in rows:
    if peer['id']==selected_id or peer['sport']!='strength' or peer['completion_status'] not in ('planned','completed'):continue
    day=datetime.fromisoformat(peer['scheduled_for']).astimezone(ZoneInfo(tz)).date();week=day.toordinal()-day.weekday()
    if week in weeks:weeks[week]+=json.loads(peer['definition_json'])['duration_minutes']
  cap,_=optional_cap(prefs['answers'],'strength')
  if cap is not None and max(weeks.values())>cap:return reject(f'This proposal needs up to {max(weeks.values())} strength minutes in a week, above your explicit {cap}-minute cap. Confirm the new cap before saving.')
 if not selected_id:
  for item in changes:item['changes']['definition']['strength_set_policy']['weekly_allowance_minutes']=max(weeks.values())
 proposal={**base,'status':'proposal','root_plan_id':program['plan_id'],'program_revision':program['revision'],'adjustments':changes,
  'message':f'Review {count} sets for every exercise, starting with the next planned strength session and continuing in this programme. Reps, lifting loads and rest stay unchanged. Timing is estimated from your recorded {minutes:.1f}-minute session, not the old planned duration; the historical weekly estimate is a reference, not an explicit cap. Readiness is rechecked before training. Save applies this progression locally; published sessions then need Garmin instruction updates.'}
 proposal['fingerprint']=hashlib.sha256(encoded({key:proposal[key] for key in ('root_plan_id','program_revision','adjustments')}).encode()).hexdigest()
 if selected_id:proposal['message']=f'Review {count} sets per exercise for this selected strength session only. Nothing is saved yet; the recurring progression remains unchanged.'
 return proposal
