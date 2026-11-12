"""Reviewed, durable formatting preferences shared by current and future plans."""
import hashlib
import copy
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .training import encoded, _snapshot, _revision


def requested(message):
    text=message.lower().replace('-', ' ')
    from .training_replacements import requested as replacement_requested
    if replacement_requested(text):return False
    if re.search(r"do not remove|don.t remove|keep (?:the )?(?:warm\s*up|cool\s*down)",text):return False
    return bool(re.search(r'warm\s*up|cool\s*down|continuous|single block',text) and
                re.search(r'\b(endurance|edurance|steady|base|recovery|easy)\b',text) and
                re.search(r'no\b|without|remove|merge|continuous|single block|don.t need',text))


def continuous_definition(old):
    """Merge easy timed blocks without regenerating the saved main target."""
    from .training_prescriptions import validate_workout
    steps=old.get('steps',[])
    if not steps or any(s.get('termination','time')!='time' for s in steps):raise ValueError('This ride needs explicit timed blocks before its format can be changed.')
    main=[s for s in steps if not re.search(r'warm|cool',str(s.get('name') or s.get('type')),re.I)]
    if not main:raise ValueError('No steady main block was found; review this ride before merging its blocks.')
    if len(main)!=1:raise ValueError('This ride has several main blocks; review their targets rather than merging different instructions automatically.')
    step=copy.deepcopy(main[0]);step.update(duration_seconds=old['duration_minutes']*60,repetitions=1)
    updated={**old,'steps':[step],'effort_target':{'method':step.get('target',{}).get('type',old.get('effort_target',{}).get('method')),'description':f"{step.get('name') or step.get('type')}: {step['effort']}"},'continuous_endurance':True,'user_adjusted':True}
    # Legacy talk-test steps have no numeric target; preserve their guidance too.
    if step.get('target'):validate_workout(updated)
    return updated


def propose(message,path=None,now=None,*,selected_id=None):
    from .training_coach import read_brief
    from .active_training import _program_workouts
    now=now or datetime.now(timezone.utc)
    brief=read_brief(path)
    changes=[]
    with connect(path) as c:
        program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if program:
            state=json.loads(program['state_json']);today=now.astimezone(ZoneInfo(state['timezone'])).date()
            for row in _program_workouts(c,program['plan_id']):
                if selected_id and row['id']!=selected_id:continue
                old=json.loads(row['definition_json'])
                day=old.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(state['timezone'])).date().isoformat()
                kind=old.get('workout_kind') or ('endurance' if old.get('template_id')=='cycling_easy' else None)
                if row['sport']!='cycling' or row['completion_status']!='planned' or day<today.isoformat() or kind not in ('endurance','long_endurance','recovery') or old.get('fixed_commitment'):continue
                if old.get('continuous_endurance') and len(old.get('steps',[]))==1:continue
                if row['publish_status'] not in ('local','published','update_needed'):
                    raise ValueError('A matching ride has an unfinished Garmin send. Reconcile it before editing its blocks.')
                updated=continuous_definition(old)
                changes.append({'workout_id':row['id'],'expected_revision':row['revision'],'title':row['title'],'date':day,'changes':{'definition':updated}})
    result={'tool':'propose_training_adjustment','kind':'adaptation','format_preference':not selected_id,'status':'proposal' if changes or not selected_id else 'needs_input','request':message,'root_plan_id':program['plan_id'] if program else None,'program_revision':program['revision'] if program else None,'brief_revision':brief['revision'],'adjustments':changes,'changes':{},'message':f'Review {len(changes)} upcoming base/recovery ride(s) as one continuous block, preserving total duration and the main effort target. '+('Only the selected session changes; recurring preferences remain unchanged.' if selected_id else 'Save also remembers this format for future plans and suggestions.')+' Published rides will show pending Garmin updates.'}
    if selected_id and not changes:result['message']='The selected session has no eligible steady block to merge, or is already continuous. Its instructions were not changed.'
    result['fingerprint']=hashlib.sha256(encoded({k:result[k] for k in ('root_plan_id','program_revision','brief_revision','adjustments')}).encode()).hexdigest()
    return result


def save(arguments,path=None,now=None):
    from .training_coach import read_brief, _store_brief
    from .training_lifecycle import invalidate
    proposal=propose(arguments['message'],path,now)
    if proposal['fingerprint']!=arguments.get('fingerprint'):raise ValueError('Plan or preferences changed. Review a fresh proposal.')
    brief=read_brief(path)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT revision FROM training_coach_brief WHERE id=1').fetchone()
        if (row[0] if row else 0)!=proposal['brief_revision']:raise ValueError('Preferences changed. Review again.')
        active=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        root=active['plan_id'] if active and active['status']=='active' else None
        if root!=proposal['root_plan_id'] or root and active['revision']!=proposal['program_revision']:raise ValueError('Active plan changed. Review again.')
        for item in proposal['adjustments']:
            row=_snapshot(c,item['workout_id'])
            if row['revision']!=item['expected_revision'] or row['completion_status']!='planned' or row['publish_status'] not in ('local','published','update_needed'):raise ValueError('A workout changed. Review again.')
            c.execute("UPDATE planned_workouts SET definition_json=?,revision=revision+1,publish_status=CASE WHEN publish_status='local' THEN 'local' ELSE 'update_needed' END WHERE id=?",(encoded(item['changes']['definition']),row['id']))
            _revision(c,_snapshot(c,row['id']))
        _store_brief(c,{**brief['brief'],'continuous_endurance':True},brief['revision']+1)
        if root:
            state=json.loads(active['state_json']);state['brief']['continuous_endurance']=True
            c.execute('UPDATE active_training_program SET state_json=?,revision=revision+1 WHERE id=1',(encoded(state),))
            invalidate(c,root)
    return {'status':'saved','count':len(proposal['adjustments']),'continuous_endurance':True}
