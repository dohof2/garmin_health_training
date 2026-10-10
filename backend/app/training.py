"""Local reviewed planning with explicit constraints; no model-generated writes."""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .database import connect
from .time_utils import timezone_info

SPORTS = ('cycling', 'running', 'strength')
EQUIPMENT = ('bike', 'trainer', 'bodyweight', 'dumbbells', 'bands', 'gym', 'barbell', 'mat')
MOVEMENTS = ('squat', 'hinge', 'push', 'pull', 'core')
FIELDS = ('sports','priority','availability','experience','equipment','weekly_minutes','blocked_sports','blocked_movements','restrictions_notes','pain_or_illness')
QUESTIONS = {
    'sports':'Which sports should this plan include?', 'priority':'What is the immediate training priority? A long-term goal is optional.',
    'availability':'Which days, start times, and maximum session lengths are available?',
    'experience':'How experienced are you in each selected sport?', 'equipment':'What training equipment is available?',
    'weekly_minutes':'What weekly minutes have been manageable recently for each selected sport?',
    'blocked_sports':'Which sports must be excluded? Select none explicitly if there are no exclusions.',
    'blocked_movements':'Which strength movements must be excluded?',
    'restrictions_notes':'Are there other restrictions or clinician instructions? Free-text restrictions need manual review.',
    'pain_or_illness':'Are you currently experiencing pain or illness that affects training?',
}
RULE_VERSION = 'training-v1'
TEMPLATES = (
    {'id':'cycling_easy','sport':'cycling','title':'Easy endurance ride','equipment_any':['bike','trainer'],'minimum_minutes':20,'kind':'endurance'},
    {'id':'running_easy','sport':'running','title':'Easy conversational run','equipment_any':[],'minimum_minutes':15,'kind':'endurance'},
    {'id':'strength_foundation','sport':'strength','title':'Strength foundation','equipment_any':['bodyweight','dumbbells','bands','gym','barbell'],'minimum_minutes':20,'kind':'strength'},
)
EXERCISES = (
    {'id':'chair_squat','name':'Chair squat','movement':'squat','equipment':'bodyweight'},
    {'id':'bodyweight_hinge','name':'Hip hinge practice','movement':'hinge','equipment':'bodyweight'},
    {'id':'wall_pushup','name':'Wall push-up','movement':'push','equipment':'bodyweight'},
    {'id':'dead_bug','name':'Dead bug','movement':'core','equipment':'bodyweight'},
    {'id':'dumbbell_row','name':'Dumbbell row','movement':'pull','equipment':'dumbbells'},
    {'id':'band_row','name':'Band row','movement':'pull','equipment':'bands'},
    {'id':'machine_row','name':'Seated machine row','movement':'pull','equipment':'gym'},
    {'id':'dumbbell_squat','name':'Dumbbell squat','movement':'squat','equipment':'dumbbells'},
    {'id':'dumbbell_press','name':'Dumbbell floor press','movement':'push','equipment':'dumbbells'},
    {'id':'band_press','name':'Resistance-band press','movement':'push','equipment':'bands'},
    {'id':'machine_leg_press','name':'Machine leg press','movement':'squat','equipment':'gym'},
    {'id':'barbell_squat','name':'Barbell squat','movement':'squat','equipment':'barbell'},
    {'id':'barbell_row','name':'Barbell row','movement':'pull','equipment':'barbell'},
)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _number(value,field,low,high,integer=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high or (integer and type(value) is not int):
        raise ValueError(f'{field} must be '+('an integer ' if integer else '')+f'between {low} and {high}')
    return value


def _choices(value,allowed,field,nonempty=False):
    if not isinstance(value,list) or any(not isinstance(v,str) or v not in allowed for v in value) or len(set(value))!=len(value) or (nonempty and not value):
        raise ValueError(f'Invalid {field}')
    return value


def validate_answers(patch):
    if not isinstance(patch,dict) or set(patch)-set(FIELDS):raise ValueError('Unknown training preference')
    result={}
    for field,value in patch.items():
        if field=='sports':result[field]=_choices(value,SPORTS,field,True)
        elif field=='priority':
            if value not in ('general','endurance','strength','mixed'):raise ValueError('Invalid training priority')
            result[field]=value
        elif field in ('equipment','blocked_sports','blocked_movements'):
            result[field]=_choices(value,EQUIPMENT if field=='equipment' else SPORTS if field=='blocked_sports' else MOVEMENTS,field)
        elif field=='availability':
            if not isinstance(value,list) or not 1<=len(value)<=7:raise ValueError('Provide 1–7 available days')
            seen=set();slots=[]
            for slot in value:
                if not isinstance(slot,dict) or set(slot)!={'weekday','start_time','minutes'}:raise ValueError('Availability requires weekday, start_time and minutes')
                weekday=_number(slot['weekday'],'weekday',0,6,True)
                if weekday in seen:raise ValueError('Only one session slot per day is supported')
                seen.add(weekday)
                minutes=_number(slot['minutes'],'session minutes',15,180,True)
                try:
                    clock=datetime.strptime(slot['start_time'],'%H:%M')
                    if clock.strftime('%H:%M')!=slot['start_time']:raise ValueError()
                except (TypeError,ValueError):raise ValueError('Session start time must use HH:MM')
                if clock.hour*60+clock.minute+minutes>1440:raise ValueError('A session must finish on its scheduled day')
                slots.append({'weekday':weekday,'start_time':slot['start_time'],'minutes':minutes})
            result[field]=sorted(slots,key=lambda s:s['weekday'])
        elif field in ('experience','weekly_minutes'):
            if not isinstance(value,dict) or set(value)-set(SPORTS):raise ValueError(f'Invalid {field}')
            for sport,entry in value.items():
                if field=='experience' and entry not in ('new','regular','experienced'):raise ValueError('Invalid training experience')
                if field=='weekly_minutes':_number(entry,f'{sport} weekly minutes',0,1260,True)
            result[field]=value
        elif field=='pain_or_illness':
            if type(value) is not bool:raise ValueError('Pain/illness answer must be yes or no')
            result[field]=value
        else:
            if not isinstance(value,str) or len(value)>1500:raise ValueError('Restrictions must be text up to 1500 characters')
            result[field]=value.strip()
    return result


def _preferences(c):
    row=c.execute('SELECT * FROM training_preferences WHERE id=1').fetchone()
    return {'revision':row['revision'],'answers':json.loads(row['answers_json']),'confirmed_at':json.loads(row['confirmed_json'])} if row else {'revision':0,'answers':{},'confirmed_at':{}}


def _timestamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _context(c,now):
    prefs=_preferences(c);answers=prefs['answers'];missing=[];stale=[]
    for field in FIELDS:
        if field not in answers or (field in ('experience','weekly_minutes') and any(s not in answers[field] for s in answers.get('sports',[]))):missing.append(field)
        elif field in prefs['confirmed_at']:
            confirmed=datetime.fromisoformat(prefs['confirmed_at'][field])
            if (now-confirmed).days >= (30 if field in ('availability','pain_or_illness','blocked_sports','blocked_movements','restrictions_notes') else 90):stale.append(field)
    blockers=[]
    if answers.get('pain_or_illness'):blockers.append('Reported pain or illness: review before generating a plan.')
    pain_confirmed=prefs['confirmed_at'].get('pain_or_illness','')
    recent_feedback=[dict(r) for r in c.execute('SELECT f.*,w.sport,w.scheduled_for FROM training_feedback f JOIN planned_workouts w ON w.id=f.workout_id')
                     if _timestamp(r['updated_at']) >= now-timedelta(days=14)]
    if any(r['pain_or_illness'] and (not pain_confirmed or _timestamp(r['updated_at']) > _timestamp(pain_confirmed)) for r in recent_feedback):
        blockers.append('Recent session feedback reports pain or illness. Reconfirm the current training restrictions before generating another plan.')
    if answers.get('restrictions_notes'):blockers.append('Free-text restrictions need manual interpretation; automatic generation is blocked.')
    if any(s in answers.get('blocked_sports',[]) for s in answers.get('sports',[])):blockers.append('A selected sport is also excluded.')
    for template in TEMPLATES:
        if template['sport'] in answers.get('sports',[]) and template['equipment_any'] and not set(template['equipment_any']) & set(answers.get('equipment',[])):
            blockers.append(f"Equipment unavailable for {template['sport']}.")
    if 'strength' in answers.get('sports',[]):
        movements={e['movement'] for e in EXERCISES if e['equipment'] in answers.get('equipment',[]) and e['movement'] not in answers.get('blocked_movements',[])}
        if len(movements)<2:blockers.append('Equipment and exclusions leave fewer than two supported strength movements.')
    return {**prefs,'missing':missing,'stale':stale,'questions':[{'field':f,'question':QUESTIONS[f],'reason':'missing' if f in missing else 'stale'} for f in missing+stale],
            'blockers':blockers,'ready':not(missing or stale or blockers),'templates':list(TEMPLATES),'rule_version':RULE_VERSION,
            'goals':[dict(r) for r in c.execute("SELECT id,title,goal_type FROM goals WHERE status='active'")],
            'recent_feedback':recent_feedback}


def training_context(path:Path|None=None,now=None):
    with connect(path) as c:return _context(c,now or datetime.now(timezone.utc))


def save_preferences(answers,expected_revision,path:Path|None=None,now=None):
    patch=validate_answers(answers);now=now or datetime.now(timezone.utc)
    if type(expected_revision) is not int:raise ValueError('Training preference revision is required')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');current=_preferences(c)
        if current['revision']!=expected_revision:raise ValueError('Training preferences changed; reload before saving')
        merged={**current['answers'],**patch};confirmed={**current['confirmed_at'],**{k:now.isoformat() for k in patch}};revision=expected_revision+1
        c.execute('INSERT INTO training_preferences(id,revision,answers_json,confirmed_json) VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,answers_json=excluded.answers_json,confirmed_json=excluded.confirmed_json,updated_at=CURRENT_TIMESTAMP',(revision,encoded(merged),encoded(confirmed)))
        c.execute('INSERT INTO training_preference_revisions(revision,answers_json,confirmed_json) VALUES (?,?,?)',(revision,encoded(merged),encoded(confirmed)))
        return _context(c,now)


def workout_definition(template_id,minutes,answers):
    template=next((t for t in TEMPLATES if t['id']==template_id),None)
    if template is None:raise ValueError('Unknown workout template')
    _number(minutes,'workout minutes',template['minimum_minutes'],180,True)
    if template['sport'] not in answers['sports'] or template['sport'] in answers['blocked_sports']:raise ValueError('Workout sport violates stored preferences')
    if template['equipment_any'] and not set(template['equipment_any']) & set(answers['equipment']):raise ValueError('Required workout equipment is unavailable')
    result={'version':RULE_VERSION,'template_id':template_id,'sport':template['sport'],'title':template['title'],'duration_minutes':minutes,
            'effort_target':{'method':'talk_test','description':'Comfortable, conversational effort. No pace, power, or HR zones are inferred.'},'rationale':['Fits saved availability and selected sport.','Initial plans maintain manageable volume; increases require a reviewed proposal.']}
    if template['kind']=='endurance':
        warm=min(5,minutes//4);cool=warm
        result['steps']=[{'type':'warmup','duration_seconds':warm*60,'effort':'easy'}, {'type':'steady','duration_seconds':(minutes-warm-cool)*60,'effort':'conversational'}, {'type':'cooldown','duration_seconds':cool*60,'effort':'easy'}]
    else:
        exercises=[e for e in EXERCISES if e['equipment'] in answers['equipment'] and e['movement'] not in answers['blocked_movements']]
        chosen=[];seen=set()
        for e in exercises:
            if e['movement'] not in seen:chosen.append({**e,'sets':1 if answers['experience']['strength']=='new' else 2,'repetitions':8,'load':'Comfortable load; leave repetitions in reserve','rest_seconds':90});seen.add(e['movement'])
        if len(chosen)<2:raise ValueError('Restrictions/equipment leave fewer than two supported strength movements')
        # Budget warm-up and conservative two-minute work blocks plus stated rests.
        available=minutes*60-300
        selected=[];used=0
        for e in chosen:
            cost=e['sets']*(120+e['rest_seconds'])
            if used+cost<=available:selected.append(e);used+=cost
        if len(selected)<2:raise ValueError('Session length is too short for supported strength exercises')
        result['exercises']=selected;result['warmup_minutes']=5;result['effort_target']={'method':'self_selected','description':'Controlled repetitions with comfortable technique; no maximum load is inferred.'}
    return result


def _snapshot(c,identifier):
    row=c.execute('SELECT * FROM planned_workouts WHERE id=?',(identifier,)).fetchone()
    return dict(row) if row else None


def _revision(c,row):
    feedback=c.execute('SELECT * FROM training_feedback WHERE workout_id=?',(row['id'],)).fetchone()
    c.execute('INSERT INTO training_workout_revisions(workout_id,revision,snapshot_json) VALUES (?,?,?)',(row['id'],row['revision'],encoded({**row,'feedback':dict(feedback) if feedback else None})))


def draft_week(week_start,timezone_name,expected_preference_revision,path:Path|None=None,now=None):
    timezone_info(timezone_name);now=now or datetime.now(timezone.utc)
    if week_start.weekday()!=0:raise ValueError('Choose a Monday for the week start')
    if week_start<now.astimezone(ZoneInfo(timezone_name)).date():raise ValueError('New weekly drafts must start on a current or future Monday')
    # Today's estimate is context only: it cannot predict readiness on future plan dates.
    from .readiness import readiness_history
    current_day=now.astimezone(ZoneInfo(timezone_name)).date()
    readiness=readiness_history(current_day,1,timezone_name,path,now=now)['latest']
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');context=_context(c,now)
        if context['revision']!=expected_preference_revision:raise ValueError('Training preferences changed; reload first')
        if not context['ready']:raise ValueError('Complete or reconfirm the training questions and resolve restrictions first')
        answers=context['answers'];plan_id='plan-'+str(uuid.uuid4());sessions=[];allocated={s:0 for s in answers['sports']};last_strength=None
        for index,slot in enumerate(answers['availability']):
            if len(sessions)>=6:break  # Reserve at least one day without a generated workout.
            scheduled_day=week_start+timedelta(days=slot['weekday'])
            # Balanced rotation, capped by the user's explicitly confirmed manageable volume.
            candidates=sorted(answers['sports'],key=lambda s:(allocated[s]/max(1,answers['weekly_minutes'][s]),0 if (answers['priority']=='strength' and s=='strength') or (answers['priority']=='endurance' and s!='strength') else 1,answers['sports'].index(s)))
            for sport in candidates:
                if sport=='strength' and last_strength and (scheduled_day-last_strength).days<2:continue
                if sport=='strength' and any(abs((datetime.fromisoformat(r['scheduled_for'].replace('Z','+00:00')).astimezone(ZoneInfo(timezone_name)).date()-scheduled_day).days)<2 for r in c.execute("SELECT scheduled_for FROM planned_workouts WHERE sport='strength' AND completion_status NOT IN ('cancelled','skipped') AND scheduled_for IS NOT NULL")):continue
                remaining=answers['weekly_minutes'][sport]-allocated[sport]
                template=next(t for t in TEMPLATES if t['sport']==sport)
                minutes=min(slot['minutes'],remaining,30 if answers['experience'][sport]=='new' else 60)
                if minutes<template['minimum_minutes']:continue
                definition=workout_definition(template['id'],minutes,answers)
                local=datetime.fromisoformat(f"{scheduled_day}T{slot['start_time']}").replace(tzinfo=ZoneInfo(timezone_name))
                # Ambiguous/nonexistent wall times must be selected manually rather than guessed.
                if local.astimezone(timezone.utc).astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)!=local.replace(tzinfo=None) or local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset():raise ValueError('A scheduled time crosses a timezone clock change; choose another time')
                scheduled=local.isoformat();ending=local+timedelta(minutes=minutes)
                for existing in c.execute("SELECT scheduled_for,definition_json FROM planned_workouts WHERE completion_status NOT IN ('cancelled','skipped') AND scheduled_for IS NOT NULL"):
                    other=datetime.fromisoformat(existing['scheduled_for'].replace('Z','+00:00'))
                    if not other.tzinfo:raise ValueError('An existing workout has ambiguous timing; review it first')
                    other_minutes=json.loads(existing['definition_json']).get('duration_minutes')
                    if not _number(other_minutes,'existing workout duration',1,1440):continue
                    if local<other+timedelta(minutes=other_minutes) and other<ending:raise ValueError('The draft conflicts with an existing scheduled workout')
                sessions.append({'id':'workout-'+str(uuid.uuid4()),'sport':sport,'title':definition['title'],'scheduled_for':scheduled,'definition':definition})
                allocated[sport]+=minutes
                if sport=='strength':last_strength=scheduled_day
                break
        if not sessions:raise ValueError('No supported session fits the saved availability, volume and restrictions')
        rationale=['All sessions are easy/foundation; no automatic intensity increase.','Volume stays within confirmed manageable weekly minutes.','At least one calendar day separates strength sessions, including adjacent plans.','At most six sessions are generated, leaving a day without a new workout.','Immediate priority breaks ties in the balanced sport rotation.','Goals are optional context, not inferred workout targets.']
        recent_start=(current_day-timedelta(days=28)).isoformat()
        recorded=[dict(r) for r in c.execute("SELECT activity_type,COUNT(*) AS activity_count,SUM(duration_seconds)/60 AS recorded_minutes FROM activities WHERE deleted_at IS NULL AND substr(started_at,1,10)>=? AND substr(started_at,1,10)<? GROUP BY activity_type",(recent_start,current_day.isoformat()))]
        c.execute("INSERT INTO training_plans(id,name,status,starts_on,ends_on,context_json) VALUES (?,?,'draft',?,?,?)",(plan_id,'Training week '+week_start.isoformat(),week_start.isoformat(),(week_start+timedelta(days=6)).isoformat(),encoded({'rule_version':RULE_VERSION,'preferences':context,'timezone':timezone_name,'rationale':rationale,
            'readiness_context':{'date':readiness['date'],'status':readiness['status'],'score':readiness['score'],'score_range':readiness['score_range'],'calculation_id':readiness['calculation_id'],'note':'Current advisory context; not a forecast or a reason for automatic intensity increases.'},
            'recorded_history':{'start':recent_start,'end':(current_day-timedelta(days=1)).isoformat(),'sports':recorded,'note':'Recorded history may be incomplete; confirmed manageable volume determines this draft.'}})))
        for s in sessions:
            c.execute("INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES (?,?,?,?,?,?)",(s['id'],plan_id,s['sport'],s['title'],s['scheduled_for'],encoded(s['definition'])))
            _revision(c,_snapshot(c,s['id']))
    return list_training(path)


def list_training(path:Path|None=None):
    with connect(path) as c:
        plans=[{**dict(r),'context':json.loads(r['context_json'])} for r in c.execute('SELECT * FROM training_plans ORDER BY starts_on DESC,created_at DESC')]
        workouts=[]
        for row in c.execute('SELECT * FROM planned_workouts ORDER BY scheduled_for,id'):
            item={**dict(row),'definition':json.loads(row['definition_json'])}
            feedback=c.execute('SELECT * FROM training_feedback WHERE workout_id=?',(row['id'],)).fetchone();item['feedback']=dict(feedback) if feedback else None
            item['suggested_revision']='Review a reduction or rest; no schedule changed.' if feedback and (feedback['pain_or_illness'] or (feedback['soreness'] or 0)>=5 or (feedback['effort'] or 0)>=8) else 'Review the missed session; do not stack catch-up workouts.' if row['completion_status']=='skipped' else None
            workouts.append(item)
        return {'plans':plans,'workouts':workouts}


def progression_proposal(path:Path|None=None,now=None):
    """Explicit engineering defaults; a proposal cannot modify volume or the calendar."""
    now=now or datetime.now(timezone.utc)
    context=training_context(path,now);history=list_training(path);answers=context['answers']
    if not context['ready']:
        return {'status':'needs_review','message':'Complete/reconfirm preferences and resolve restrictions before progression.','changes':{},'rationale':context['blockers']}
    volumes=dict(answers['weekly_minutes']);reasons=[]
    recent=[p for p in history['plans'] if p['status']=='active' and p['ends_on']<now.date().isoformat()][:2]
    for sport in answers['sports']:
        sessions=[w for w in history['workouts'] if w['sport']==sport and w['training_plan_id'] in {p['id'] for p in recent}]
        adverse=any(w['completion_status']=='skipped' or (w['feedback'] and (w['feedback']['pain_or_illness'] or (w['feedback']['soreness'] or 0)>=5 or (w['feedback']['effort'] or 0)>=8)) for w in sessions)
        covered=len(recent)==2 and all(any(w['training_plan_id']==p['id'] for w in sessions) for p in recent)
        tolerated=covered and sessions and all(w['completion_status']=='completed' and w['feedback'] and w['feedback']['effort'] is not None and w['feedback']['effort']<=7 and w['feedback']['soreness'] is not None and w['feedback']['soreness']<=3 and not w['feedback']['pain_or_illness'] for w in sessions)
        if adverse:
            volumes[sport]=max(0,int(volumes[sport]*.8));reasons.append(f'{sport}: propose 20% less volume after missed or difficult sessions; review, do not stack catch-up work.')
        elif tolerated:
            increment=min(15,int(volumes[sport]*.05)) if volumes[sport]>0 else 0
            volumes[sport]=min(volumes[sport]+increment,sum(s['minutes'] for s in answers['availability']))
            reasons.append(f'{sport}: two completed weeks with low reported difficulty permit a reviewed volume increase up to 5% / 15 minutes. Intensity stays unchanged.')
        else:reasons.append(f'{sport}: maintain volume until two completed weeks with effort and soreness feedback are available.')
    # Shared availability is a total budget across sports, never a separate full budget per sport.
    capacity=sum(s['minutes'] for s in answers['availability'])
    if sum(volumes[s] for s in answers['sports'])>capacity and any(volumes[s]>answers['weekly_minutes'][s] for s in answers['sports']):
        volumes=dict(answers['weekly_minutes']);reasons.append('Shared availability leaves no room for an increase; maintain the confirmed limits.')
    return {'status':'proposal','expected_revision':context['revision'],'changes':{'weekly_minutes':volumes},'rationale':reasons,
            'rule_version':RULE_VERSION,'advisory':'5% / 15-minute increases and 20% reductions are provisional planning defaults, not validated universal safety thresholds. Save only after review.'}


def accept_plan(identifier,path:Path|None=None):
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM training_plans WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('Training plan not found')
        context=json.loads(row['context_json']);current=_context(c,datetime.now(timezone.utc))
        if not current['ready'] or current['revision']!=context['preferences']['revision']:raise ValueError('Preferences changed or need review; create a fresh draft')
        c.execute("UPDATE training_plans SET status='active',updated_at=CURRENT_TIMESTAMP WHERE id=?",(identifier,))
    return list_training(path)


def update_workout(identifier,expected_revision,changes,path:Path|None=None):
    allowed={'template_id','duration_minutes','completion_status','effort','soreness','pain_or_illness','notes','activity_id'}
    if not isinstance(changes,dict) or set(changes)-allowed:raise ValueError('Unknown workout change')
    if type(expected_revision) is not int:raise ValueError('Workout revision must be an integer')
    if 'pain_or_illness' in changes and type(changes['pain_or_illness']) is not bool:raise ValueError('Pain/illness feedback must be yes or no')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');row=_snapshot(c,identifier)
        if not row:raise ValueError('Workout not found')
        if row['revision']!=expected_revision:raise ValueError('Workout changed; reload before saving')
        if row['garmin_workout_id'] or row['publish_status']!='local':raise ValueError('Published workout edits require the T8 publication workflow')
        definition=json.loads(row['definition_json'])
        restoring=row['completion_status'] in ('cancelled','skipped') and changes.get('completion_status') in ('planned','completed')
        if 'template_id' in changes or 'duration_minutes' in changes or restoring:
            context=_context(c,datetime.now(timezone.utc))
            if not context['ready']:raise ValueError('Preferences require review before changing training')
            template=changes.get('template_id',definition['template_id']);minutes=changes.get('duration_minutes',definition['duration_minutes'])
            definition=workout_definition(template,minutes,context['answers'])
            local=datetime.fromisoformat(row['scheduled_for'])
            slots={s['weekday']:s for s in context['answers']['availability']};slot=slots.get(local.weekday())
            if not slot or local.strftime('%H:%M')!=slot['start_time'] or minutes>slot['minutes']:raise ValueError('Edit exceeds saved availability')
            for other in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status NOT IN ('cancelled','skipped')",(identifier,)):
                start=datetime.fromisoformat(other['scheduled_for']);other_def=json.loads(other['definition_json'])
                if local<start+timedelta(minutes=other_def['duration_minutes']) and start<local+timedelta(minutes=minutes):raise ValueError('Edit conflicts with another workout')
            weekly_total=minutes
            monday=local.date()-timedelta(days=local.weekday())
            for other in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND sport=? AND completion_status NOT IN ('cancelled','skipped')",(identifier,definition['sport'])):
                started=datetime.fromisoformat(other['scheduled_for'])
                if monday<=started.astimezone(local.tzinfo).date()<=monday+timedelta(days=6):weekly_total+=json.loads(other['definition_json'])['duration_minutes']
                if definition['sport']=='strength' and abs((started.astimezone(local.tzinfo).date()-local.date()).days)<2:raise ValueError('Strength sessions need a recovery day between them')
            if weekly_total>context['answers']['weekly_minutes'][definition['sport']]:raise ValueError('Edit exceeds confirmed manageable weekly volume')
        status=changes.get('completion_status',row['completion_status'])
        if status not in ('planned','completed','skipped','cancelled'):raise ValueError('Invalid completion status')
        old_feedback=c.execute('SELECT * FROM training_feedback WHERE workout_id=?',(identifier,)).fetchone()
        feedback={**(dict(old_feedback) if old_feedback else {'effort':None,'soreness':None,'pain_or_illness':False,'notes':None,'activity_id':None}),**{k:v for k,v in changes.items() if k in ('effort','soreness','pain_or_illness','notes','activity_id')}}
        for field in ('effort','soreness'):
            if feedback[field] is not None:_number(feedback[field],field,0,10)
        if type(feedback['pain_or_illness']) is not bool and feedback['pain_or_illness'] not in (0,1):raise ValueError('Pain/illness feedback must be yes or no')
        if feedback['notes'] is not None and (not isinstance(feedback['notes'],str) or len(feedback['notes'])>1500):raise ValueError('Feedback notes must be up to 1500 characters')
        if feedback['activity_id'] and not c.execute('SELECT 1 FROM activities WHERE id=? AND deleted_at IS NULL',(feedback['activity_id'],)).fetchone():raise ValueError('Linked Garmin activity was not found')
        c.execute('UPDATE planned_workouts SET sport=?,title=?,definition_json=?,completion_status=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(definition['sport'],definition['title'],encoded(definition),status,identifier))
        c.execute('INSERT INTO training_feedback(workout_id,effort,soreness,pain_or_illness,activity_id,notes,updated_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(workout_id) DO UPDATE SET effort=excluded.effort,soreness=excluded.soreness,pain_or_illness=excluded.pain_or_illness,activity_id=excluded.activity_id,notes=excluded.notes,updated_at=excluded.updated_at',(identifier,feedback['effort'],feedback['soreness'],int(feedback['pain_or_illness']),feedback['activity_id'],feedback['notes'],datetime.now(timezone.utc).isoformat()))
        _revision(c,_snapshot(c,identifier))
    return list_training(path)
