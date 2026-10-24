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

from .training_constraints import SPORTS,SPORT_CATALOG,resolve as resolve_schedule,availability as schedule_availability,capacity as schedule_capacity,optional_cap,merge_answers,schedule as validate_schedule,caps as validate_caps
EQUIPMENT = ('bike', 'trainer', 'bodyweight', 'dumbbells', 'bands', 'gym', 'barbell', 'mat', 'pull_up_bar', 'dip_bars')
MOVEMENTS = ('squat', 'hinge', 'push', 'pull', 'core')
FIELDS = ('sports','priority','week_schedule','experience','equipment','blocked_sports','blocked_movements','restrictions_notes','pain_or_illness')
QUESTIONS = {
    'sports':'Which sports should this plan include?', 'priority':'What is the immediate training priority? A long-term goal is optional.',
    'week_schedule':'Which sports and duration limits are available on each unanswered weekday? Choose rest explicitly for a rest day.', 'availability':'Which days and maximum session lengths are available? Start times are optional.',
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
    {'id':'strength_foundation','sport':'strength','title':'Strength foundation','equipment_any':['bodyweight','dumbbells','bands','gym','barbell','pull_up_bar','dip_bars'],'minimum_minutes':20,'kind':'strength'},
    {'id':'hiking_easy','sport':'hiking','title':'Easy hike','equipment_any':[],'minimum_minutes':10,'kind':'duration'},
    {'id':'other_easy','sport':'other','title':'Easy activity','equipment_any':[],'minimum_minutes':10,'kind':'duration'},
)
EXERCISES = (
    {'id':'pullup_progression','name':'Pull-up progression','movement':'pull','equipment':'pull_up_bar'},
    {'id':'dip_progression','name':'Dip progression','movement':'push','equipment':'dip_bars'},
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
    if not isinstance(patch,dict) or set(patch)-set(FIELDS)-{'availability','weekly_minutes','weekly_caps'}:raise ValueError('Unknown training preference')
    result={}
    for field,value in patch.items():
        if field=='week_schedule':result[field]=validate_schedule(value)
        elif field=='weekly_caps':result[field]=validate_caps(value)
        elif field=='sports':result[field]=_choices(value,SPORTS,field,True)
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
                minutes=_number(slot['minutes'],'session minutes',15,720,True)
                if slot['start_time'] is None:
                    slots.append({'weekday':weekday,'start_time':None,'minutes':minutes});continue
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


def _context(c,now,candidate_answers=None,brief=None,timezone_name="UTC"):
    prefs=_preferences(c)
    if candidate_answers:
        patch=validate_answers(candidate_answers)
        prefs={**prefs,'answers':merge_answers(prefs['answers'],patch),'confirmed_at':{**prefs['confirmed_at'],**{key:now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat() for key in patch}}}
    raw_answers=prefs['answers'];answers=dict(raw_answers);missing=[];stale=[]
    if 'week_schedule' in answers:
        answers['sports']=list(dict.fromkeys(answers.get('sports',[])+[slot['sport'] for day in answers['week_schedule'] for slot in day['activities']]))
    brief_row=c.execute('SELECT brief_json FROM training_coach_brief WHERE id=1').fetchone()
    legacy_brief=brief or (json.loads(brief_row[0]) if brief_row else {})
    resolved=resolve_schedule(answers,legacy_brief)
    answers['week_schedule']=resolved['days'];answers['availability']=schedule_availability(resolved['days'])
    operational={}
    for sport in answers.get('sports',[]):
        cap,_=optional_cap(raw_answers,sport);operational[sport]=min(schedule_capacity(resolved['days'],sport),cap if cap is not None else 5040)
    from .training_volume import estimates
    volume_estimates=estimates(c,{**raw_answers,'week_schedule':resolved['days'],'sports':answers.get('sports',[])},legacy_brief,now.astimezone(ZoneInfo(timezone_name)).date(),timezone_name)
    operational={sport:value['effective_ceiling_minutes'] for sport,value in volume_estimates.items()}
    answers['weekly_minutes']=operational
    for field in FIELDS:
        if field not in answers or (field=='week_schedule' and (not resolved['days'] or not resolved['legacy'] and len(resolved['days'])!=7)) or (field=='experience' and any(s not in answers.get('experience',{}) for s in answers.get('sports',[]) if s in ('cycling','running','strength'))):missing.append(field)
        elif field in prefs['confirmed_at']:
            confirmed=datetime.fromisoformat(prefs['confirmed_at'][field])
            if (now-confirmed).days >= (30 if field in ('availability','pain_or_illness','blocked_sports','blocked_movements','restrictions_notes') else 90):stale.append(field)
    blockers=list(resolved['issues'])
    for sport in answers.get('sports',[]):
        cap,_=optional_cap(raw_answers,sport)
        if cap!=0 and schedule_capacity(resolved['days'],sport)==0:
            blockers.append(f'Which days and duration limits should I use for {sport}? It is selected but has no training slots. Or explicitly remove it from the plan.')
    if answers.get('pain_or_illness'):blockers.append('Reported pain or illness: review before generating a plan.')
    pain_confirmed=prefs['confirmed_at'].get('pain_or_illness','')
    recent_feedback=[dict(r) for r in c.execute('SELECT f.*,w.sport,w.scheduled_for,w.completion_status FROM training_feedback f JOIN planned_workouts w ON w.id=f.workout_id')
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
    return {**prefs,'answers':answers,'raw_answers':raw_answers,'sport_catalog':list(SPORT_CATALOG.values()),'legacy_schedule':resolved['legacy'],'unanswered_weekdays':sorted(set(range(7))-{day['weekday'] for day in resolved['days']}),'planning_limits':operational,'volume_estimates':volume_estimates,'missing':missing,'stale':stale,'questions':[{'field':f,'question':QUESTIONS[f],'reason':'missing' if f in missing else 'stale'} for f in missing+stale],
            'blockers':blockers,'ready':not(missing or stale or blockers),'templates':list(TEMPLATES),'rule_version':RULE_VERSION,
            'goals':[dict(r) for r in c.execute("SELECT id,title,goal_type FROM goals WHERE status='active'")],
            'recent_feedback':recent_feedback,'recent_strength_performance':[dict(r) for r in c.execute("SELECT s.*,w.title FROM training_strength_performance s JOIN planned_workouts w ON w.id=s.workout_id WHERE w.completion_status='completed' AND s.recorded_at>=? ORDER BY s.recorded_at DESC LIMIT 100",((now-timedelta(days=90)).isoformat(),))]}


def training_context(path:Path|None=None,now=None):
    with connect(path) as c:return _context(c,now or datetime.now(timezone.utc))


def save_preferences(answers,expected_revision,path:Path|None=None,now=None):
    patch=validate_answers(answers)
    if 'week_schedule' in patch:patch.pop('weekly_minutes',None)
    now=now or datetime.now(timezone.utc)
    if type(expected_revision) is not int:raise ValueError('Training preference revision is required')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');current=_preferences(c)
        if current['revision']!=expected_revision:raise ValueError('Training preferences changed; reload before saving')
        merged=merge_answers(current['answers'],patch)
        if 'week_schedule' in merged:merged['week_schedule']=validate_schedule(merged['week_schedule'],complete=True)
        confirmed={**current['confirmed_at'],**{k:now.isoformat() for k in patch}};revision=expected_revision+1
        c.execute('INSERT INTO training_preferences(id,revision,answers_json,confirmed_json) VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,answers_json=excluded.answers_json,confirmed_json=excluded.confirmed_json,updated_at=CURRENT_TIMESTAMP',(revision,encoded(merged),encoded(confirmed)))
        c.execute('INSERT INTO training_preference_revisions(revision,answers_json,confirmed_json) VALUES (?,?,?)',(revision,encoded(merged),encoded(confirmed)))
        c.execute('DELETE FROM training_review_gate')
        return _context(c,now)


def workout_definition(template_id,minutes,answers):
    template=next((t for t in TEMPLATES if t['id']==template_id),None)
    if template is None:raise ValueError('Unknown workout template')
    _number(minutes,'workout minutes',template['minimum_minutes'],720,True)
    if template['sport'] not in answers['sports'] or template['sport'] in answers['blocked_sports']:raise ValueError('Workout sport violates stored preferences')
    if template['equipment_any'] and not set(template['equipment_any']) & set(answers['equipment']):raise ValueError('Required workout equipment is unavailable')
    result={'version':RULE_VERSION,'template_id':template_id,'sport':template['sport'],'title':template['title'],'duration_minutes':minutes,
            'effort_target':{'method':'talk_test','description':'Comfortable, conversational effort. No pace, power, or HR zones are inferred.'},'rationale':['Fits saved availability and selected sport.','Initial plans maintain manageable volume; increases require a reviewed proposal.']}
    if template['kind'] in ('endurance','duration'):
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
    c.execute('INSERT INTO training_workout_revisions(workout_id,revision,snapshot_json) VALUES (?,?,?)',(row['id'],row['revision'],encoded({**row,'feedback':dict(feedback) if feedback else None,'strength_performance':[dict(r) for r in c.execute('SELECT * FROM training_strength_performance WHERE workout_id=?',(row['id'],))]})))


def draft_week(week_start,timezone_name,expected_preference_revision,path:Path|None=None,now=None):
    from .training_coach import read_brief,preview,create_draft
    now=now or datetime.now(timezone.utc)
    with connect(path) as c:
        if _preferences(c)['revision']!=expected_preference_revision:raise ValueError('Training preferences changed; reload first')
    brief=read_brief(path)['brief']
    proposal=preview(brief,week_start,timezone_name,path,now)
    return create_draft(brief,week_start,timezone_name,proposal['fingerprint'],path,now)


def list_training(path:Path|None=None, *, compact=False):
    with connect(path) as c:
        plans=[{**dict(r),'context':json.loads(r['context_json'])} for r in c.execute('SELECT * FROM training_plans WHERE deleted_at IS NULL ORDER BY starts_on DESC,created_at DESC')]
        for plan in plans:plan['status']=plan['context'].get('lifecycle_status',plan['status'])
        workouts=[]
        for row in c.execute('SELECT * FROM planned_workouts ORDER BY scheduled_for,id'):
            parent=c.execute('SELECT deleted_at FROM training_plans WHERE id=?',(row['training_plan_id'],)).fetchone()
            removed=bool(parent and parent['deleted_at'])
            if removed and row['completion_status']!='completed':continue
            item={**dict(row),'definition':json.loads(row['definition_json']),'plan_removed':removed}
            item['scheduled_date']=item['definition'].get('scheduled_date') or (row['scheduled_for'] or '')[:10]
            item['time_unspecified']=item['definition'].get('time_unspecified',False)
            feedback=c.execute('SELECT * FROM training_feedback WHERE workout_id=?',(row['id'],)).fetchone();item['feedback']=dict(feedback) if feedback else None
            item['strength_performance']=[dict(r) for r in c.execute('SELECT * FROM training_strength_performance WHERE workout_id=? ORDER BY exercise_id,set_index',(row['id'],))]
            item['suggested_revision']='Review a reduction or rest; no schedule changed.' if feedback and (feedback['pain_or_illness'] or (feedback['soreness'] or 0)>=5 or (feedback['effort'] or 0)>=8) else 'Review the missed session; do not stack catch-up workouts.' if row['completion_status']=='skipped' else None
            workouts.append(item)
        if compact:
            for plan in plans:
                plan.pop('context_json',None)
                context=plan['context']
                plan['context']={key:context[key] for key in ('program_id','rationale','readiness_context','recorded_history') if key in context}
                plan['context']['preferences']={'goals':context.get('preferences',{}).get('goals',[])}
            for workout in workouts:workout.pop('definition_json',None)
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
        from .active_training import activate
        activate(c,row)
    return list_training(path)


def update_workout(identifier,expected_revision,changes,path:Path|None=None):
    allowed={'template_id','duration_minutes','completion_status','effort','soreness','pain_or_illness','notes','activity_id','strength_sets'}
    if not isinstance(changes,dict) or set(changes)-allowed:raise ValueError('Unknown workout change')
    if type(expected_revision) is not int:raise ValueError('Workout revision must be an integer')
    if 'pain_or_illness' in changes and type(changes['pain_or_illness']) is not bool:raise ValueError('Pain/illness feedback must be yes or no')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');row=_snapshot(c,identifier)
        if not row:raise ValueError('Workout not found')
        owner=c.execute('SELECT deleted_at FROM training_plans WHERE id=?',(row['training_plan_id'],)).fetchone()
        if owner and owner['deleted_at'] and set(changes)-{'effort','soreness','pain_or_illness','notes','strength_sets'}:raise ValueError('This plan was removed; only historical feedback can be edited')
        if row['revision']!=expected_revision:raise ValueError('Workout changed; reload before saving')
        if row['garmin_workout_id'] or row['publish_status']!='local':raise ValueError('Published workout edits require the T8 publication workflow')
        definition=json.loads(row['definition_json'])
        schedule_metadata={key:definition[key] for key in ('scheduled_date','time_unspecified','schedule_timezone','schedule_slot_id','schedule_slot_label') if key in definition}
        restoring=row['completion_status'] in ('cancelled','skipped') and changes.get('completion_status') in ('planned','completed')
        if 'template_id' in changes or 'duration_minutes' in changes or restoring:
            context=_context(c,datetime.now(timezone.utc))
            if not context['ready']:raise ValueError('Preferences require review before changing training')
            if definition['template_id'] in ('fixed_commitment','cycling_controlled_intervals'): raise ValueError('Revise the coaching brief and preview a replacement week to change a coached session; feedback can be saved here.')
            template=changes.get('template_id',definition['template_id']);minutes=changes.get('duration_minutes',definition['duration_minutes'])
            if definition.get('workout_kind') and template==definition['template_id']:
                from .training_coach import read_brief
                from .training_prescriptions import endurance
                definition=endurance(definition['workout_kind'],minutes,read_brief(path)['brief'],definition['sport'])
            else:definition=workout_definition(template,minutes,context['answers'])
            definition.update(schedule_metadata)
            definition['user_adjusted']=True
            local=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(definition.get('schedule_timezone') or 'UTC'))
            from .training_constraints import assign_slot
            assigned=assign_slot(context['answers']['week_schedule'],local.weekday(),definition['sport'],minutes,definition.get('schedule_slot_id'))
            definition['schedule_slot_id']=assigned['slot_id']
            from .training_constraints import day_limit
            day_total=minutes
            for peer in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status IN ('planned','completed')",(identifier,)):
                if datetime.fromisoformat(peer['scheduled_for']).astimezone(local.tzinfo).date()==local.date():
                    peer_def=json.loads(peer['definition_json']);day_total+=peer_def['duration_minutes']
                    if peer_def.get('schedule_slot_id')==assigned['slot_id']:raise ValueError('This activity slot is already occupied')
            if day_total>day_limit(context['answers']['week_schedule'],local.weekday()):raise ValueError('Edit exceeds the shared day limit')
            for other in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status NOT IN ('cancelled','skipped')",(identifier,)):
                start=datetime.fromisoformat(other['scheduled_for']);other_def=json.loads(other['definition_json'])
                if not(definition.get('time_unspecified') or other_def.get('time_unspecified')) and local<start+timedelta(minutes=other_def['duration_minutes']) and start<local+timedelta(minutes=minutes):raise ValueError('Edit conflicts with another workout')
            weekly_total=minutes
            root_row=c.execute('SELECT starts_on,context_json FROM training_plans WHERE id=?',(row['training_plan_id'],)).fetchone()
            root_id=json.loads(root_row['context_json']).get('program_id',row['training_plan_id'])
            root=c.execute('SELECT starts_on FROM training_plans WHERE id=?',(root_id,)).fetchone()
            anchor=date.fromisoformat(root['starts_on'])
            monday=anchor+timedelta(weeks=(local.date()-anchor).days//7)
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
        if 'strength_sets' in changes:
            sets=changes['strength_sets']
            if row['sport']!='strength' or not isinstance(sets,list) or len(sets)>60:raise ValueError('Use up to 60 actual strength sets')
            allowed_ids={e['id'] for e in definition.get('exercises',[])};seen=set()
            for item in sets:
                if not isinstance(item,dict) or set(item)-{'exercise_id','set_index','load_kg','repetitions','repetitions_in_reserve'} or item.get('exercise_id') not in allowed_ids:raise ValueError('Choose an exercise from this session')
                _number(item.get('set_index'),'set number',1,20,True);_number(item.get('repetitions'),'actual repetitions',0,100,True)
                if item.get('load_kg') is not None:_number(item['load_kg'],'actual load kg',0,500)
                if item.get('repetitions_in_reserve') is not None:_number(item['repetitions_in_reserve'],'repetitions in reserve',0,10)
                key=(item['exercise_id'],item['set_index'])
                if key in seen:raise ValueError('Each actual set needs a unique exercise/set number')
                seen.add(key)
                c.execute('INSERT INTO training_strength_performance(workout_id,exercise_id,set_index,load_kg,repetitions,repetitions_in_reserve,recorded_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(workout_id,exercise_id,set_index) DO UPDATE SET load_kg=excluded.load_kg,repetitions=excluded.repetitions,repetitions_in_reserve=excluded.repetitions_in_reserve,recorded_at=excluded.recorded_at',(identifier,item['exercise_id'],item['set_index'],item.get('load_kg'),item['repetitions'],item.get('repetitions_in_reserve'),datetime.now(timezone.utc).isoformat()))
        _revision(c,_snapshot(c,identifier))
        owner_context=c.execute('SELECT context_json FROM training_plans WHERE id=?',(row['training_plan_id'],)).fetchone()
        root=json.loads(owner_context[0]).get('program_id',row['training_plan_id']) if owner_context else row['training_plan_id']
        from .training_lifecycle import invalidate
        invalidate(c,root)
    return list_training(path)
