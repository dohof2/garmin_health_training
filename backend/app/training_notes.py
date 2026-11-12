"""Small, revisioned user preferences shared by chat, UI and deterministic plans."""
import copy
import json
import math
import re
from datetime import datetime, timedelta, timezone

from .database import connect

MAX_NOTES=16
MAX_TEXT=160
MAX_TOTAL=1600
TYPES={'all':['all'],'cycling':['all','recovery','endurance','long_endurance','climbing_endurance','long_tempo','tempo','threshold','vo2','short_efforts','sprint','anaerobic'],
       'strength':['all','cycling_support','general_fitness','strength_development'],
       'running':['all','endurance','recovery','tempo','threshold','vo2'], 'hiking':['all'], 'other':['all']}


def rows(c):
    return [{**{k:r[k] for k in ('activity','workout_type','topic','text','revision')},'settings':json.loads(r['settings_json'])}
            for r in c.execute('SELECT * FROM training_notes ORDER BY activity,workout_type,topic')]


def read(path=None, activity=None, workout_type=None):
    with connect(path) as c:notes=rows(c)
    if activity:notes=[n for n in notes if n['activity'] in ('all',activity)]
    if workout_type:notes=[n for n in notes if n['workout_type'] in ('all',workout_type)]
    tree={}
    for note in notes:tree.setdefault(note['activity'],{}).setdefault(note['workout_type'],[]).append(note)
    return {'notes':notes,'tree':tree,'workout_types':TYPES,'limits':{'notes':MAX_NOTES,'per_note':MAX_TEXT,'total_characters':MAX_TOTAL}}


def validate(activity,workout_type,topic,text,settings):
    if activity not in TYPES or workout_type not in TYPES[activity]:raise ValueError('Choose a supported activity and workout type')
    if not isinstance(topic,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,23}',topic):raise ValueError('Use a short topic key such as sets or format')
    if not isinstance(text,str) or not 1<=len(text.strip())<=MAX_TEXT or '\n' in text.strip():raise ValueError('Keep each note to one line and at most 160 characters')
    if not isinstance(settings,dict) or set(settings)-{'sets','rest_seconds','continuous_endurance'}:raise ValueError('Unsupported planning settings')
    for key,high in (('sets',5),('rest_seconds',600)):
        if key in settings and (activity!='strength' or type(settings[key]) is not int or not (1 if key=='sets' else 0)<=settings[key]<=high):raise ValueError('Use 1–5 strength sets or 0–600 seconds of rest')
    if 'continuous_endurance' in settings and (activity!='cycling' or workout_type not in ('all','endurance','long_endurance','recovery') or settings['continuous_endurance'] is not True):raise ValueError('Use true for continuous easy cycling, or remove the setting to use the plan default')


def write(c,arguments,*,invalidate_plan=True):
    from .training import encoded
    activity=arguments.get('activity');kind=arguments.get('workout_type','all');topic=arguments.get('topic')
    text=arguments.get('text','')
    delete=arguments.get('operation','upsert')=='delete'
    if arguments.get('operation','upsert') not in ('upsert','delete'):raise ValueError('Choose upsert or delete')
    current=c.execute('SELECT revision,settings_json FROM training_notes WHERE activity=? AND workout_type=? AND topic=?',(activity,kind,topic)).fetchone()
    settings=arguments.get('settings',json.loads(current['settings_json']) if current else {})
    validate(activity,kind,topic,'Delete' if delete else text,settings)
    mentioned=re.search(r'\b(?:use|keep|do)\s+(\d+)\s+sets?\b',text,re.I)
    if not delete and mentioned and 'sets' in settings and int(mentioned[1])!=settings['sets']:raise ValueError('The note text and saved set count disagree. Update both together.')
    revision=current[0] if current else 0
    if type(arguments.get('expected_revision')) is not int or arguments['expected_revision']!=revision:raise ValueError('This note changed. Read its latest version before editing.')
    if delete:c.execute('DELETE FROM training_notes WHERE activity=? AND workout_type=? AND topic=?',(activity,kind,topic))
    else:
        for other in c.execute('SELECT topic,settings_json FROM training_notes WHERE activity=? AND workout_type=? AND topic!=?',(activity,kind,topic)):
            if set(json.loads(other['settings_json'])) & set(settings):raise ValueError('Edit the existing '+other['topic']+' note instead of duplicating its planning setting.')
        c.execute('''INSERT INTO training_notes(activity,workout_type,topic,text,settings_json) VALUES(?,?,?,?,?)
            ON CONFLICT(activity,workout_type,topic) DO UPDATE SET text=excluded.text,settings_json=excluded.settings_json,
            revision=training_notes.revision+1,updated_at=CURRENT_TIMESTAMP''',(activity,kind,topic,text.strip(),encoded(settings)))
        size=c.execute('SELECT count(*),sum(length(text)) FROM training_notes').fetchone()
        if size[0]>MAX_NOTES or size[1]>MAX_TOTAL:raise ValueError('Replace or remove an older note; keep at most 16 notes and 1,600 characters in total.')
    from .training_lifecycle import invalidate
    program=c.execute("SELECT plan_id FROM active_training_program WHERE id=1 AND status='active'").fetchone()
    if program and activity=='strength' and kind=='all':
        state=json.loads(c.execute('SELECT state_json FROM active_training_program WHERE id=1').fetchone()[0])
        policy=state.get('strength_set_policy',{})
        if not delete and 'sets' in settings:policy={**policy,'sets':settings['sets']}
        elif current and 'sets' in json.loads(current['settings_json']):policy={k:v for k,v in policy.items() if k!='sets'}
        if policy!=state.get('strength_set_policy',{}):
            state['strength_set_policy']=policy
            c.execute('UPDATE active_training_program SET state_json=?,revision=revision+1 WHERE id=1',(encoded(state),))
    if program and invalidate_plan:invalidate(c,program['plan_id'])
    return {'status':'deleted' if delete else 'saved','activity':activity,'workout_type':kind,'topic':topic,'revision':revision+1,
            'message':'Recurring training note '+('removed.' if delete else 'saved. It guides future plans and daily reviews; existing workouts change only when reviewed or applied.')}


def save(arguments,path=None):
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        return write(c,arguments)


def matching(notes,definition):
    sport=definition.get('sport')
    kind=definition.get('strength_purpose') if sport=='strength' else definition.get('workout_kind')
    return sorted([n for n in notes if n['activity'] in ('all',sport) and n['workout_type'] in ('all',kind)],
                  key=lambda n:(n['activity']!='all',n['workout_type']!='all',n['topic']))


def strength_timing(definition,policy=None):
    policy=policy or {}
    exercises=definition.get('exercises',[])
    sets=sum(e['sets'] for e in exercises)
    warmup=definition.get('warmup_minutes',0)*60
    rest=sum(e['sets']*e.get('rest_seconds',0) for e in exercises)
    # Rep-based work has no exact duration. Keep a visible estimate, accounting
    # for every exported rest and warm-up; use recorded timing when comparable.
    work=sum(e['sets']*e['repetitions']*3 for e in exercises)
    seconds=warmup+rest+work;method='3_seconds_per_rep'
    if policy.get('reference_total_sets') and policy.get('reference_repetitions')=={e['id']:e['repetitions'] for e in exercises}:
        seconds=max(seconds,policy['duration_reference_minutes']*60*sets/policy['reference_total_sets'])
        method='recorded_session_scaled_to_sets'
    definition.update(duration_minutes=max(10,math.ceil(seconds/60)),duration_estimated=True,
        strength_timing={'method':method,'sets':sets,'warmup_seconds':warmup,'rest_seconds':rest,'work_seconds_estimate':round(seconds-warmup-rest)})
    return definition


def strength_budget(notes,brief,policy,fallback):
    settings={}
    for note in matching(notes,{'sport':'strength','strength_purpose':brief.get('strength_purpose')}):settings.update(note['settings'])
    if settings.get('sets') and policy.get('reference_total_sets') and policy.get('reference_repetitions'):
        required=policy['duration_reference_minutes']*len(policy['reference_repetitions'])*settings['sets']/policy['reference_total_sets']
        return max(fallback,math.ceil(required))
    return fallback


def apply_definition(definition,notes,policy=None):
    selected=matching(notes,definition)
    if not selected:return definition
    result=copy.deepcopy(definition);settings={}
    for note in selected:settings.update(note['settings'])
    if result.get('sport')=='strength' and set(settings)&{'sets','rest_seconds'}:
        changed=False
        for exercise in result.get('exercises',[]):
            for key in ('sets','rest_seconds'):
                if key in settings:
                    changed|=exercise.get(key)!=settings[key]
                    exercise[key]=settings[key]
        if changed or not result.get('strength_timing'):strength_timing(result,policy or result.get('strength_set_policy'))
        result['recurring_notes_applied']=True
    elif settings.get('continuous_endurance') and result.get('workout_kind') in ('endurance','long_endurance','recovery'):
        from .workout_format import continuous_definition
        result=continuous_definition(result)
        if not definition.get('user_adjusted'):result.pop('user_adjusted',None)
    result['training_note_refs']=[f"{n['activity']}/{n['workout_type']}/{n['topic']}@{n['revision']}" for n in selected]
    return result


def apply_current(c,root,now,tz,*,horizon_days=7):
    from .active_training import _program_workouts
    from .training import _context,encoded,_snapshot,_revision
    from .training_accounting import session_day,counts_toward_plan,completed_minutes
    from .training_constraints import assign_slot,day_limit
    from zoneinfo import ZoneInfo
    today=now.astimezone(ZoneInfo(tz)).date();context=_context(c,now,timezone_name=tz)
    if context['blockers']:return [],context['blockers']
    state=json.loads(c.execute('SELECT state_json FROM active_training_program WHERE id=1').fetchone()[0])
    policy=state.get('strength_set_policy',{});notes=rows(c)
    workouts=_program_workouts(c,root);changes=[];warnings=[]
    for row in workouts:
        day=session_day(row,tz);old=json.loads(row['definition_json'])
        if row['completion_status']!='planned' or day<today or (horizon_days is not None and day>=today+timedelta(days=horizon_days)) or old.get('fixed_commitment') or old.get('review_hold'):continue
        if row['publish_status'] not in ('local','published','update_needed'):continue
        if row['publish_status']!='local' and not c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=? AND verified_hash IS NOT NULL',(row['id'],row['garmin_workout_id'])).fetchone():continue
        new=apply_definition(old,notes,policy)
        if row['sport']=='strength' and policy.get('reference_repetitions') and not old.get('user_adjusted') and set(policy['reference_repetitions'])!={e['id'] for e in old.get('exercises',[])} and any(n['settings'].get('sets') for n in matching(notes,old)):
            from .training import workout_definition
            from .training_prescriptions import strength
            budget=strength_budget(notes,state['brief'],policy,old['duration_minutes'])
            rebuilt=strength(workout_definition('strength_foundation',budget,context['answers']),state['brief'],context['answers'],observed_at=now)
            rebuilt.update({k:v for k,v in old.items() if k.startswith('schedule_') or k in ('scheduled_date','time_unspecified','training_block')})
            new=apply_definition(rebuilt,notes,policy)
        if new==old:continue
        minutes=new['duration_minutes']
        try:
            # One-time sport swaps retain their reviewed destination allowance.
            if not old.get('schedule_override'):assign_slot(context['answers']['week_schedule'],day.weekday(),row['sport'],minutes,old.get('schedule_slot_id'))
            peers=[p for p in workouts if p['id']!=row['id'] and counts_toward_plan(p,today,tz)]
            if minutes+sum(json.loads(p['definition_json'])['duration_minutes'] for p in peers if session_day(p,tz)==day)>day_limit(context['answers']['week_schedule'],day.weekday()):raise ValueError('The requested prescription exceeds the shared day limit.')
            anchor=datetime.fromisoformat(state['starts_on']).date();week=anchor+timedelta(weeks=(day-anchor).days//7)
            estimate=_context(c,now,brief={**state['brief'],'_planning_day':week.isoformat()},timezone_name=tz)['volume_estimates'].get(row['sport'],{})
            used=completed_minutes(c,workouts,week,today,tz,row['sport'])+sum(json.loads(p['definition_json'])['duration_minutes'] for p in peers if p['sport']==row['sport'] and p['completion_status']=='planned' and week<=session_day(p,tz)<week+timedelta(days=7))
            if used+minutes>estimate.get('effective_ceiling_minutes',0):raise ValueError('The requested prescription exceeds this sport’s weekly allowance.')
        except ValueError as error:
            warnings.append(f"{day}: {error}");continue
        c.execute("UPDATE planned_workouts SET definition_json=?,revision=revision+1,publish_status=CASE WHEN publish_status='local' THEN 'local' ELSE 'update_needed' END WHERE id=?",(encoded(new),row['id']))
        _revision(c,_snapshot(c,row['id']));row['definition_json']=encoded(new)
        changes.append({'workout_id':row['id'],'title':row['title'],'action':'Applied recurring training notes','reason':'Use the saved activity/workout preference and recalculate the resulting duration.'})
    return changes,warnings
