"""Reviewed, durable formatting preferences shared by current and future plans."""
import hashlib
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .training import encoded, _snapshot, _revision


def requested(message):
    text=message.lower().replace('-', ' ')
    return bool(re.search(r'warm\s*up|cool\s*down|continuous|single block',text) and
                re.search(r'endurance|edurance|steady',text) and
                re.search(r'no\b|without|remove|merge|continuous|single block|don.t need',text))


def propose(message,path=None,now=None):
    from .training_coach import read_brief
    from .active_training import _program_workouts
    from .training_prescriptions import endurance
    now=now or datetime.now(timezone.utc)
    brief=read_brief(path)
    changes=[]
    with connect(path) as c:
        program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if program:
            state=json.loads(program['state_json']);today=now.astimezone(ZoneInfo(state['timezone'])).date()
            for row in _program_workouts(c,program['plan_id']):
                old=json.loads(row['definition_json'])
                day=old.get('scheduled_date') or datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(state['timezone'])).date().isoformat()
                if row['sport']!='cycling' or row['completion_status']!='planned' or day<today.isoformat() or old.get('workout_kind') not in ('endurance','long_endurance') or old.get('fixed_commitment'):continue
                if row['publish_status'] not in ('local','published','update_needed'):
                    raise ValueError('A matching ride has an unfinished Garmin send. Reconcile it before editing its blocks.')
                new=endurance(old['workout_kind'],old['duration_minutes'],{**state['brief'],'continuous_endurance':True},today=today,indoor=old.get('workout_location')=='indoor')
                # Preserve scheduling, dose evidence and all unrelated metadata.
                updated={**old,**{key:new[key] for key in ('steps','effort_target')},'continuous_endurance':True,'user_adjusted':True}
                changes.append({'workout_id':row['id'],'expected_revision':row['revision'],'title':row['title'],'date':day,'changes':{'definition':updated}})
    result={'tool':'propose_training_adjustment','kind':'adaptation','format_preference':True,'status':'proposal','request':message,'root_plan_id':program['plan_id'] if program else None,'program_revision':program['revision'] if program else None,'brief_revision':brief['revision'],'adjustments':changes,'changes':{},'message':f'Review {len(changes)} upcoming easy endurance ride(s) as one continuous block, preserving total duration. Save also remembers this format for future plans. Published rides will show pending Garmin updates.'}
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
            if row['revision']!=item['expected_revision'] or row['completion_status']!='planned':raise ValueError('A workout changed. Review again.')
            c.execute("UPDATE planned_workouts SET definition_json=?,revision=revision+1,publish_status=CASE WHEN publish_status='local' THEN 'local' ELSE 'update_needed' END WHERE id=?",(encoded(item['changes']['definition']),row['id']))
            _revision(c,_snapshot(c,row['id']))
        _store_brief(c,{**brief['brief'],'continuous_endurance':True},brief['revision']+1)
        if root:
            state=json.loads(active['state_json']);state['brief']['continuous_endurance']=True
            c.execute('UPDATE active_training_program SET state_json=?,revision=revision+1 WHERE id=1',(encoded(state),))
            invalidate(c,root)
    return {'status':'saved','count':len(proposal['adjustments']),'continuous_endurance':True}


def resolve_followup(message,history):
    """Keep this narrow formatting request through scope/affirmation replies."""
    if not re.fullmatch(r'\s*(?:yes(?:[,. ]+apply it)?|also for (?:the )?(?:planning|pkanning) ahead|in general for cycling (?:endurance|edurance) steady)[.!? ]*',message,re.I):return message
    prior=[turn['content'] for turn in history[-8:] if turn['role']=='user']
    combined=' '.join(prior[-4:]+[message])
    return combined if requested(combined) else message
