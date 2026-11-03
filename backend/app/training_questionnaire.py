"""Read saved candidate setup for the Training form; conversation lives in skill_agent."""
import json
from datetime import datetime, timezone, timedelta
from .database import connect
from .training_coach import read_brief
from .time_utils import timezone_info


def read(path=None):
    with connect(path) as c:
        row=c.execute('SELECT revision,state_json FROM training_questionnaire WHERE id=1').fetchone()
    return {'revision':row['revision'],'state':json.loads(row['state_json'])} if row else {'revision':0,'state':None}


def candidate_snapshot(path=None,tz='UTC',now=None):
    now=now or datetime.now(timezone.utc);today=now.astimezone(timezone_info(tz)).date()
    pending=read(path);saved=read_brief(path);state=pending['state'] or {}
    brief=state.get('brief') or saved['brief'];answers=state.get('answers',{})
    week=brief.get('program_start') or (today+timedelta(days=(7-today.weekday())%7)).isoformat()
    return {'brief':brief,'answers':answers,'candidate_answers':answers,'week_start':week,'questionnaire_revision':pending['revision'],'partial':state.get('partial',{}),'awaiting':state.get('awaiting'),'next_question':state.get('next_question'),'saved_brief_revision':saved['revision']}
