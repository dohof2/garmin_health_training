"""Persistent goal blocks, rolling local sessions and transparent recovery reviews."""
import hashlib
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .database import connect
from .training import _context, _revision, _snapshot, encoded, list_training, workout_definition
from .time_utils import timezone_info


def activate(c, plan):
    context=json.loads(plan['context_json'])
    brief=context.get('brief')
    if not brief:
        from .training_coach import DEFAULT
        brief={**DEFAULT,'goal':'general','horizon_weeks':4}
    from .training_coach import roadmap
    blocks=context.get('roadmap') or roadmap(brief,date.fromisoformat(plan['starts_on']),context['preferences']['answers'])
    state={'brief':brief,'blocks':blocks,'timezone':context.get('timezone','UTC'),
           'starts_on':plan['starts_on'],'ends_on':(date.fromisoformat(plan['starts_on'])+timedelta(weeks=len(blocks),days=-1)).isoformat()}
    previous=c.execute('SELECT plan_id FROM active_training_program WHERE id=1').fetchone()
    if previous and previous['plan_id']!=plan['id']:
        for old in c.execute("SELECT w.* FROM planned_workouts w JOIN training_plans p ON p.id=w.training_plan_id WHERE w.completion_status='planned' AND p.status='active' AND p.id!=?",(plan['id'],)).fetchall():
            c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(old['id'],))
            _revision(c,_snapshot(c,old['id']))
        c.execute("UPDATE training_plans SET status='superseded' WHERE status='active' AND id!=?",(plan['id'],))
    c.execute("INSERT INTO active_training_program(id,plan_id,status,state_json) VALUES(1,?,'active',?) ON CONFLICT(id) DO UPDATE SET plan_id=excluded.plan_id,status='active',state_json=excluded.state_json,revision=active_training_program.revision+1,updated_at=CURRENT_TIMESTAMP",(plan['id'],encoded(state)))


def capability(path, today, tz, mix_days=14):
    start=today-timedelta(days=42)
    with connect(path) as c:
        activities=[]
        for row in c.execute("SELECT id,activity_type,started_at,duration_seconds,distance_meters FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND started_at>=? ORDER BY started_at",(start.isoformat(),)):
            day=datetime.fromisoformat(row['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date()
            if start<=day<=today:activities.append(dict(row))
        from .ride_comparison import training_benefit
        mix={'endurance':[],'tempo':[],'short_hard_efforts':[]};classified=0;recent=0
        for activity in activities:
            day=datetime.fromisoformat(activity['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date()
            if day<today-timedelta(days=mix_days-1):continue
            recent+=1;benefit=training_benefit(c,activity['id']);source=benefit['source_label']
            category='endurance' if source=='AEROBIC_BASE' else 'tempo' if source in ('TEMPO','LACTATE_THRESHOLD','THRESHOLD') else 'short_hard_efforts' if source in ('SPRINT','SPEED','ANAEROBIC','ANAEROBIC_CAPACITY') else None
            if benefit['label']:classified+=1
            if category:mix[category].append({'id':activity['id'],'date':day.isoformat(),'benefit':benefit['label']})
        enough=recent>=3 and classified/recent>=.6
        gaps=[key for key,rows in mix.items() if not rows] if enough else []
        training_mix={'period_start':(today-timedelta(days=mix_days-1)).isoformat(),'period_end':today.isoformat(),'activity_count':recent,'classified_count':classified,'categories':{key:len(rows) for key,rows in mix.items()},'evidence':mix,'gaps':gaps,'coverage':'usable' if enough else 'limited','note':'Categories use recorded Garmin primary-benefit labels. No recent label is a possible training-mix gap, not proof of a physiological deficiency; short hard efforts are not verified sprint intervals.'}
        measures={}
        ids=[r['id'] for r in activities]
        if ids:
            for row in c.execute(f"SELECT m.metric_type,m.value,m.unit,a.started_at FROM activity_metrics m JOIN activities a ON a.id=m.activity_id WHERE a.id IN ({','.join('?' for _ in ids)}) ORDER BY a.started_at",ids):
                if row['metric_type'] in ('aerobic_training_effect','anaerobic_training_effect','normalized_power','average_power','exercise_load','intensity_factor','threshold_power'):
                    measures.setdefault(row['metric_type'],[]).append(dict(row))
        biological={}
        for row in c.execute("SELECT metric_type,value,unit,recorded_at FROM metric_readings WHERE source_name!='synthetic_fixture' AND recorded_at>=? ORDER BY recorded_at",((today-timedelta(days=7)).isoformat(),)):
            if row['recorded_at'][:10]>today.isoformat():continue
            if row['metric_type'] in ('sleep_score','hrv_last_night_average','hrv_nightly_average','hrv','resting_heart_rate','stress','body_battery','vo2_cycling','vo2_running'):
                biological[row['metric_type']]=dict(row)
    with connect(path) as c:
        for row in c.execute("SELECT metric_type,value,unit,recorded_at FROM metric_readings WHERE source_name!='synthetic_fixture' AND metric_type IN ('vo2_cycling','vo2_running') AND substr(recorded_at,1,10)<=? ORDER BY recorded_at",(today.isoformat(),)):
            biological[row['metric_type']]=dict(row)
    duration=sum(r['duration_seconds'] or 0 for r in activities)/60
    return {'period_start':start.isoformat(),'period_end':today.isoformat(),'activity_count':len(activities),
            'weekly_minutes':round(duration/6),'longest_minutes':round(max([r['duration_seconds'] or 0 for r in activities],default=0)/60),
            'aerobic_effect':_mean(measures.get('aerobic_training_effect',[])),
            'anaerobic_effect':_mean(measures.get('anaerobic_training_effect',[])),
            'latest_normalized_power':(measures.get('normalized_power') or [None])[-1],
            'training_mix':training_mix,'biological':biological,'note':'Recorded workload and training effects describe recent exposure; they do not measure a physiological ceiling or establish FTP.'}


def _mean(rows):return round(sum(r['value'] for r in rows)/len(rows),1) if rows else None


def _program_workouts(c, identifier):
    rows=[]
    for row in c.execute("SELECT w.*,p.context_json FROM planned_workouts w JOIN training_plans p ON p.id=w.training_plan_id WHERE p.status='active' ORDER BY w.scheduled_for"):
        context=json.loads(row['context_json'])
        if row['training_plan_id']==identifier or context.get('program_id')==identifier:
            rows.append(dict(row))
    return rows


def _fill(c,program,state,today,now):
    """Generate only the visible seven-day horizon using accepted constraints."""
    context=_context(c,now)
    if not context['ready']:return ['Upcoming generation needs current training answers: '+', '.join(context['missing']+context['stale'])]+context['blockers']
    from .training_coach import _preview
    warnings=[]
    for monday in sorted({today-timedelta(days=today.weekday()),(today+timedelta(days=6))-timedelta(days=(today+timedelta(days=6)).weekday())}):
        if monday.isoformat()>state['ends_on']:continue
        # The preview includes current workouts and fixed commitments in its volume limits.
        brief={**state['brief'],'fixed_events':[e for e in state['brief']['fixed_events'] if e['date']>=today.isoformat() and not any(w['scheduled_for'][:10]==e['date'] and json.loads(w['definition_json']).get('fixed_commitment') for w in _program_workouts(c,program))]}
        p=_preview(c,brief,monday,state['timezone'],now,None)
        if p['status']!='ready':
            if p['status']=='needs_input':warnings.extend(p['questions'])
            continue
        occupied={datetime.fromisoformat(w['scheduled_for']).date() for w in _program_workouts(c,program)}
        sessions=[s for s in p['sessions'] if datetime.fromisoformat(s['scheduled_for']).date() not in occupied and today<=datetime.fromisoformat(s['scheduled_for']).date()<=min(today+timedelta(days=6),date.fromisoformat(state['ends_on']))]
        if not sessions:continue
        child='plan-'+str(uuid.uuid4())
        stored={**p,'program_id':program,'preferences':context,'automatic_continuation':True}
        c.execute("INSERT INTO training_plans(id,name,status,starts_on,ends_on,context_json) VALUES(?,?,'active',?,?,?)",(child,'Active plan week · '+monday.isoformat(),monday.isoformat(),(monday+timedelta(days=6)).isoformat(),encoded(stored)))
        block=next((b for b in state['blocks'] if b['starts_on']==monday.isoformat()),None)
        for session in sessions:
            definition=session['definition']
            if block and block['phase'] in ('Recovery / review','Freshen up','Post-event recovery') and not definition.get('fixed_commitment'):
                minutes=max(20 if session['sport']!='running' else 15,round(definition['duration_minutes']*.7))
                definition=workout_definition({'cycling':'cycling_easy','running':'running_easy','strength':'strength_foundation'}[session['sport']],minutes,context['answers'])
                definition['rationale'].append('Reduced volume for the saved '+block['phase']+' building block.')
            wid='workout-'+str(uuid.uuid4())
            c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',(wid,child,session['sport'],definition['title'],session['scheduled_for'],encoded(definition)))
            _revision(c,_snapshot(c,wid))
    return list(dict.fromkeys(warnings))


def review(path=None,timezone_name='UTC',now=None):
    timezone_info(timezone_name);now=now or datetime.now(timezone.utc)
    with connect(path) as c:
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
    if not program:return {'program':None,'workouts':[],'review':None}
    state=json.loads(program['state_json']);tz=state['timezone'];today=now.astimezone(ZoneInfo(tz)).date()
    capabilities=capability(path,today,tz)
    from .readiness import readiness_history
    readiness=readiness_history(today,1,tz,path,now=now)['latest']
    from .training_load_charts import daily_rows
    loads=[r for r in daily_rows(path) if (today-timedelta(days=2)).isoformat()<=r['date']<=today.isoformat()]
    load=loads[-1] if loads else None
    reasons=[]
    if readiness['score'] is not None and readiness['score']<40:reasons.append('Current readiness is below 40; use recovery rather than a demanding session.')
    autonomic=next((g for g in readiness.get('groups',[]) if g['name']=='autonomic'),{})
    if autonomic.get('hrv_z') is not None and autonomic['hrv_z']<-1.5:reasons.append('Overnight HRV is substantially below its personal baseline.')
    if autonomic.get('rhr_z') is not None and autonomic['rhr_z']>1.5:reasons.append('Resting heart rate is elevated relative to its personal baseline.')
    if load and load['high'] is not None and load['acute']>load['high']:reasons.append('Garmin acute load is above its recorded optimal range.')
    sleep=capabilities['biological'].get('sleep_score')
    if sleep and sleep['recorded_at'][:10]>=(today-timedelta(days=1)).isoformat() and sleep['value']<50:reasons.append('The latest recorded sleep score is below 50.')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        # Serialize fills and re-read the active program to avoid applying stale reviews.
        fresh=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if fresh['plan_id']!=program['plan_id']:raise ValueError('Active plan changed; review again')
        warnings=[]
        if program['status']=='active' and today.isoformat()>state['ends_on']:
            c.execute("UPDATE active_training_program SET status='completed',revision=revision+1 WHERE id=1")
            program={**dict(program),'status':'completed'}
        reviewed_today=any(json.loads(r[0]).get('date')==today.isoformat() and json.loads(r[0]).get('commitment_revision',0)==state.get('commitment_revision',0) for r in c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=?',(program['plan_id'],)))
        if program['status']=='active' and not reviewed_today:warnings=_fill(c,program['plan_id'],state,today,now)
        if program['status']!='active':warnings.append('Plan '+program['status']+': automatic schedule changes are stopped.')
        feedback=[dict(r) for r in c.execute('SELECT f.*,w.training_plan_id FROM training_feedback f JOIN planned_workouts w ON w.id=f.workout_id WHERE f.updated_at>=?',((today-timedelta(days=7)).isoformat(),))]
        adverse=[f for f in feedback if f['pain_or_illness'] or (f['effort'] or 0)>=8 or (f['soreness'] or 0)>=5 or re.search(r'\b(too hard|exhausted|could not finish|couldn.t finish|too tired)\b',f['notes'] or '',re.I)]
        pain=bool(_context(c,now)['answers'].get('pain_or_illness')) or any(f['pain_or_illness'] for f in adverse)
        if adverse:reasons.append('Recent effort, soreness or session notes indicate difficulty; reduce upcoming demanding sessions.')
        if pain:reasons.append('Reported pain or illness: upcoming training is held for your review.')
        workouts=_program_workouts(c,program['plan_id'])
        upcoming=[w for w in workouts if w['completion_status']=='planned' and today<=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()<=today+timedelta(days=6)]
        state_key={'date':today.isoformat(),'program_revision':program['revision'],'readiness':readiness.get('score'),'load':load,'feedback':feedback,'capabilities':capabilities,'workouts':[(w['id'],w['revision']) for w in upcoming]}
        fingerprint=hashlib.sha256(encoded(state_key).encode()).hexdigest()
        old=c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=? AND fingerprint=?',(program['plan_id'],fingerprint)).fetchone()
        report=json.loads(old[0]) if old else {'date':today.isoformat(),'commitment_revision':state.get('commitment_revision',0),'reasons':reasons,'changes':[],'warnings':warnings,'capabilities':capabilities,'readiness':{'date':readiness['date'],'score':readiness['score'],'status':readiness['status']},'load':load}
        if not old:
            for w in upcoming:
                definition=json.loads(w['definition_json']);day=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()
                demanding=definition.get('template_id')=='cycling_controlled_intervals' or definition.get('duration_minutes',0)>=90 or 'hard' in definition.get('effort_target',{}).get('description','').lower()
                action='Kept';why='Consistent with the active plan; no current reduction signal.'
                if program['status']=='active' and (pain or (reasons and demanding and (day<=today+timedelta(days=1) or adverse))):
                    if pain or definition.get('fixed_commitment') or w['publish_status']!='local':
                        action='Review required';why='; '.join(reasons)
                        definition['review_hold']={'date':today.isoformat(),'reason':why}
                    else:
                        minutes=min(30,definition['duration_minutes'])
                        definition=workout_definition({'cycling':'cycling_easy','running':'running_easy','strength':'strength_foundation'}[w['sport']],minutes,_context(c,now)['answers'])
                        definition['rationale'].append('Automatic recovery review: '+'; '.join(reasons))
                        action='Changed to easy recovery';why='; '.join(reasons)
                    if definition==json.loads(w['definition_json']):
                        report['changes'].append({'workout_id':w['id'],'title':definition['title'],'action':action,'reason':why})
                        continue
                    c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(definition['title'],encoded(definition),w['id']))
                    _revision(c,_snapshot(c,w['id']))
                report['changes'].append({'workout_id':w['id'],'title':definition['title'],'action':action,'reason':why})
            if readiness['score'] is None:report['warnings'].append('A complete current readiness score is unavailable; no readiness-based increase is made.')
            report['warnings'].append('Review thresholds are provisional app rules. Garmin training effects describe recent stimulus, not aerobic or anaerobic capacity tests.')
            c.execute('INSERT INTO training_program_reviews(plan_id,fingerprint,review_json) VALUES(?,?,?)',(program['plan_id'],fingerprint,encoded(report)))
    history=list_training(path)
    by_id={w['id']:w for w in history['workouts']}
    return {'program':{'id':program['plan_id'],'status':program['status'],'revision':program['revision'],**state},
            'workouts':[by_id[w['id']] for w in upcoming],'review':report}


def read_active(arguments,path=None):
    # Assistant context is read-only: startup/UI performs the local review.
    with connect(path) as c:
        p=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not p:return {'tool':'get_active_training_plan','program':None,'workouts':[]}
        rows=_program_workouts(c,p['plan_id'])
        last=c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=? ORDER BY id DESC LIMIT 1',(p['plan_id'],)).fetchone()
    return {'tool':'get_active_training_plan','program':{**dict(p),'state':json.loads(p['state_json'])},'workouts':[{**w,'definition':json.loads(w['definition_json'])} for w in rows if w['completion_status']=='planned'],'latest_review':json.loads(last[0]) if last else None}


def set_status(status,path=None):
    if status not in ('active','paused','completed'):raise ValueError('Invalid plan status')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not p:raise ValueError('No active plan')
        if status=='completed':
            workouts=_program_workouts(c,p['plan_id'])
            for w in workouts:
                if w['completion_status']=='planned':
                    c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
            plan_ids={w['training_plan_id'] for w in workouts}|{p['plan_id']}
            for identifier in plan_ids:c.execute("UPDATE training_plans SET status='completed' WHERE id=?",(identifier,))
        c.execute("UPDATE active_training_program SET status=?,revision=revision+1 WHERE id=1",(status,))
        if c.execute('SELECT changes()').fetchone()[0]!=1:raise ValueError('No active plan')


def reschedule(identifier,scheduled_for,expected_revision,path=None,now=None):
    now=now or datetime.now(timezone.utc)
    local=datetime.fromisoformat(scheduled_for.replace('Z','+00:00'))
    if not local.tzinfo or local<now:raise ValueError('Choose a future date and time including its timezone')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');row=_snapshot(c,identifier)
        if not row or row['revision']!=expected_revision:raise ValueError('Session changed; refresh first')
        if row['completion_status']!='planned' or row['publish_status']!='local' or row['garmin_workout_id']:raise ValueError('Only planned local sessions can be moved')
        program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if not program or identifier not in {w['id'] for w in _program_workouts(c,program['plan_id'])}:raise ValueError('Session does not belong to the active plan')
        state=json.loads(program['state_json']);tz=ZoneInfo(state['timezone']);day=local.astimezone(tz).date()
        if not date.fromisoformat(state['starts_on'])<=day<=date.fromisoformat(state['ends_on']):raise ValueError('Choose a date within the active plan')
        if local.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=local.astimezone(tz).replace(tzinfo=None):raise ValueError('Choose a valid local time')
        definition=json.loads(row['definition_json']);end=local+timedelta(minutes=definition['duration_minutes'])
        for other in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status='planned'",(identifier,)):
            start=datetime.fromisoformat(other['scheduled_for']);d=json.loads(other['definition_json'])
            if local<start+timedelta(minutes=d['duration_minutes']) and start<end:raise ValueError('This overlaps another planned workout; move or cancel it first')
            if (definition['duration_minutes']>=90 or definition.get('template_id')=='cycling_controlled_intervals') and abs((start.astimezone(tz).date()-day).days)<=1 and (d['duration_minutes']>=90 or d.get('template_id')=='cycling_controlled_intervals'):raise ValueError('Keep a recovery day between demanding sessions')
        c.execute('UPDATE planned_workouts SET scheduled_for=?,revision=revision+1 WHERE id=?',(local.isoformat(),identifier));_revision(c,_snapshot(c,identifier))
        c.execute('UPDATE active_training_program SET revision=revision+1 WHERE id=1')
    return {'status':'saved'}


def request_change(message,timezone_name,path=None,now=None,apply=True):
    now=now or datetime.now(timezone.utc)
    if not isinstance(message,str) or not message.strip() or len(message)>1500:raise ValueError('Describe the requested change in up to 1,500 characters')
    active=read_active({},path)
    if active['program'] is None:raise ValueError('Accept a training plan first')
    workouts=active['workouts'];text=message.lower();tz=active['program']['state']['timezone'];today=now.astimezone(ZoneInfo(tz)).date()
    if re.search(r'\b(too hard|too easy|exhausted|too tired|sore|soreness|felt|feedback)\b',text) and not re.search(r'\b(move|reschedule)\b',text):
        with connect(path) as c: past=_program_workouts(c,active['program']['plan_id'])
        past=[w for w in past if datetime.fromisoformat(w['scheduled_for'])<=now and w['completion_status'] not in ('cancelled','skipped')]
        if 'long' in text:past=[w for w in past if json.loads(w['definition_json'])['duration_minutes']>=90]
        if re.search(r'\b(ride|cycling|bike)\b',text):past=[w for w in past if w['sport']=='cycling']
        if not past:raise ValueError('Which completed session is this feedback for? Choose Feedback / edit session below.')
        w=max(past,key=lambda w:w['scheduled_for'])
        changes={'notes':message}
        if apply:
            from .training import update_workout
            update_workout(w['id'],w['revision'],changes,path)
        return {'message':f"Feedback for {w['title']} on {w['scheduled_for'][:10]}.", 'workout_id':w['id'],'expected_revision':w['revision'],'changes':changes,'kind':'feedback','status':'saved' if apply else 'proposal'}
    future=[w for w in workouts if datetime.fromisoformat(w['scheduled_for'])>=now]
    if 'long' in text:future=[w for w in future if w['definition']['duration_minutes']>=90]
    if re.search(r'\b(ride|cycling|bike)\b',text):future=[w for w in future if w['sport']=='cycling']
    if not future:raise ValueError('No matching upcoming workout. Select a session below to edit.')
    workout=sorted(future,key=lambda w:w['scheduled_for'])[0]
    if re.search(r'\b(move|change|reschedule|today|tomorrow)\b',text):
        day=today if 'today' in text else today+timedelta(days=1) if 'tomorrow' in text else None
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
        if dates:day=date.fromisoformat(dates[-1])
        if day is None:
            for i,name in enumerate(('monday','tuesday','wednesday','thursday','friday','saturday','sunday')):
                if name in text:day=today+timedelta(days=(i-today.weekday())%7)
        if day is None:raise ValueError('Which day should the workout move to? Include today, tomorrow, a weekday or a date.')
        old=datetime.fromisoformat(workout['scheduled_for']).astimezone(ZoneInfo(tz));clock=re.search(r'\b(\d{1,2}:\d{2})\b',text)
        scheduled=datetime.fromisoformat(f"{day}T{clock[1] if clock else old.strftime('%H:%M')}").replace(tzinfo=ZoneInfo(tz))
        if apply:reschedule(workout['id'],scheduled.isoformat(),workout['revision'],path,now)
        return {'message':f"{workout['title']} → {scheduled.strftime('%Y-%m-%d %H:%M')}",'workout_id':workout['id'],'expected_revision':workout['revision'],'changes':{'scheduled_for':scheduled.isoformat()},'kind':'schedule','status':'saved' if apply else 'proposal'}
    raise ValueError('For effort or soreness feedback, choose the session below and save your note there. To move a workout, say its type and new day/time.')


def propose_adjustment(arguments,path=None):
    return {'tool':'propose_training_adjustment',**request_change(arguments.get('message'),arguments.get('timezone') or 'UTC',path,apply=False)}


def suggest_today(arguments,path=None,now=None):
    """A time-bounded recommendation; does not replace or save any session."""
    minutes=arguments.get('minutes')
    if type(minutes) is not int or not 10<=minutes<=360:raise ValueError('Available time must be 10–360 whole minutes')
    tz=arguments.get('timezone') or 'UTC';timezone_info(tz);now=now or datetime.now(timezone.utc);today=now.astimezone(ZoneInfo(tz)).date()
    active=read_active({},path);program=active['program'];sport=arguments.get('sport')
    if sport is not None and sport not in ('cycling','running','strength'):raise ValueError('Choose cycling, running or strength')
    current=[w for w in active['workouts'] if datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()==today]
    planned=current[0] if current and program and program['status']=='active' else None
    with connect(path) as c:context=_context(c,now)
    if not sport:sport=planned['sport'] if planned else (context['answers'].get('sports') or [None])[0]
    from .readiness import readiness_history
    readiness=readiness_history(today,1,tz,path,now=now)['latest']
    capacity=capability(path,today,tz)
    from .training_load_charts import daily_rows
    loads=[r for r in daily_rows(path) if (today-timedelta(days=2)).isoformat()<=r['date']<=today.isoformat()]
    load=loads[-1] if loads else None
    blockers=context['blockers']
    adverse=any(f['pain_or_illness'] or (f['effort'] or 0)>=8 or (f['soreness'] or 0)>=5 or re.search(r'\b(too hard|exhausted|too tired)\b',f['notes'] or '',re.I) for f in context['recent_feedback'])
    base={'tool':'suggest_today_workout','date':today.isoformat(),'available_minutes':minutes,'active_plan_id':program['plan_id'] if program and program['status']=='active' else None,'planned_workout_id':planned['id'] if planned else None,'capability_context':capacity,'readiness':{'score':readiness['score'],'status':readiness['status']},'saved':False}
    def rest(reason,questions=None,alternative=None):
        return {**base,'status':'suggestion','questions':questions or [],'session':{'sport':'rest','title':'Rest day','duration_minutes':0,'effort_target':{'description':'No structured training today. Prioritize sleep, food and hydration.'},'steps':[]},'reason':reason,'alternative':alternative,'training_mix':capacity['training_mix'],'warnings':['Recommendation only; your saved plan is unchanged.']}
    def recovery_ride(duration):
        return {'sport':'cycling','title':'Gentle recovery ride','duration_minutes':duration,'effort_target':{'description':'Very easy spinning, about 1–2/10. No intervals, hard climbs or power targets. Stop if you feel worse.'},'steps':[{'type':'Easy spin','duration_seconds':duration*60,'effort':'very easy 1–2/10'}]}
    pain=context['answers'].get('pain_or_illness') or any(f['pain_or_illness'] for f in context['recent_feedback'])
    if pain:return rest('Reported pain or illness favors rest; review your training restrictions before resuming.',blockers)
    if blockers:return rest('Rest while the recorded training restrictions are reviewed.',blockers)
    if readiness['score'] is not None and readiness['score']<=25:return rest('Current readiness is very low; rest takes priority over filling the available time or a training-mix gap.')
    rest_day=bool(program and program['status']=='active' and not planned)
    if rest_day:return rest('The active plan has no workout today. Keep the planned rest day.',alternative=recovery_ride(min(minutes,20)) if sport=='cycling' and not adverse and (readiness['score'] is None or readiness['score']>=40) else None)

    if not sport:return {**base,'status':'needs_input','questions':['Which activity can you do today: cycling, running or strength?'],'session':None}
    if sport in context['answers'].get('blocked_sports',[]):return {**base,'status':'needs_review','questions':['This sport is excluded in your training preferences. Choose an allowed sport.'],'session':None}
    low=(readiness['score'] is not None and readiness['score']<60) or adverse or bool(load and load['high'] is not None and load['acute']>load['high'])
    rest_day=bool(program and program['status']=='active' and not planned)
    reason='Use today’s saved workout within your available time.' if planned else 'Easy session based on your saved preferences and recent training.'
    if rest_day:reason='No session is scheduled today in the active plan. Keep it a recovery day; optional easy movement is not a replacement for the next planned workout.'
    dose=min(minutes,30) if low or rest_day else minutes
    if not planned: dose=min(dose,30 if context['answers'].get('experience',{}).get(sport)=='new' else 60)
    if capacity['activity_count']>=6 and capacity['longest_minutes']>0:dose=min(dose,max(20,capacity['longest_minutes']))
    if planned:dose=min(dose,planned['definition']['duration_minutes'])
    if sport=='strength':
        if not context['ready']:return {**base,'status':'needs_input','questions':['Complete equipment, experience and movement restrictions in Training before selecting strength exercises.'],'session':None}
        definition=workout_definition('strength_foundation',max(20,dose),context['answers']) if dose>=20 else None
        if definition is None:return {**base,'status':'needs_input','questions':['The supported strength session needs at least 20 minutes. Choose an easy cycling/running option or more time.'],'session':None}
    else:
        duration=max(10,dose);warm=min(10,max(3,round(duration*.15)));cool=min(5,max(2,round(duration*.1)));main=duration-warm-cool
        definition={'sport':sport,'title':'Easy '+('ride' if sport=='cycling' else 'run'),'duration_minutes':duration,'effort_target':{'description':'Easy conversational effort, about 2–3/10. Ease off or stop if you feel unwell.'},'steps':[{'type':'Warm-up','duration_seconds':warm*60,'effort':'very easy'},{'type':'Steady','duration_seconds':main*60,'effort':'conversational'},{'type':'Cool-down','duration_seconds':cool*60,'effort':'very easy'}]}
        if planned and readiness['score'] is not None and not low and not rest_day and planned['definition'].get('template_id')=='cycling_controlled_intervals' and dose>=26:
            definition={**planned['definition'],'duration_minutes':dose,'steps':[dict(step) for step in planned['definition']['steps']]}
            extra=dose*60-sum(s['duration_seconds'] for s in definition['steps']);definition['steps'][-1]['duration_seconds']+=extra
        elif planned and not low:definition['title']=planned['title']+' · time-limited version'
    mix=capacity['training_mix']
    if not planned and not low and not rest_day and readiness['score'] is not None and readiness['score']>=60 and context['answers'].get('experience',{}).get(sport) in ('regular','experienced') and sport in ('cycling','running') and dose>=40:
        gaps=mix['gaps']
        if 'endurance' in gaps:
            reason='No recorded endurance/base benefit in the recent 14-day mix. Use your available time for conversational endurance.'
        elif 'tempo' in gaps:
            definition.update(title='Controlled tempo '+('ride' if sport=='cycling' else 'run'),effort_target={'description':'Controlled tempo, about 5–6/10; never an all-out test.'},steps=[{'type':'Warm-up','duration_seconds':600,'effort':'easy'},{'type':'Tempo','duration_seconds':480,'effort':'controlled 5–6/10'},{'type':'Recovery','duration_seconds':240,'effort':'easy'},{'type':'Tempo','duration_seconds':480,'effort':'controlled 5–6/10'},{'type':'Easy finish','duration_seconds':(dose-30)*60,'effort':'easy'}])
            reason='No recorded tempo/threshold benefit in the recent 14-day mix; recovery permits a controlled tempo session.'
        elif 'short_hard_efforts' in gaps and readiness['score']>=70:
            steps=[{'type':'Warm-up','duration_seconds':900,'effort':'easy, gradually build'}]
            for _ in range(4):steps.extend([{'type':'Short acceleration','duration_seconds':15,'effort':'strong and controlled, about 7/10; not maximal'},{'type':'Recovery','duration_seconds':180,'effort':'very easy'}])
            steps.append({'type':'Easy finish','duration_seconds':(dose-28)*60,'effort':'easy'})
            definition.update(title='Short controlled accelerations',effort_target={'description':'Four 15-second controlled accelerations with full easy recoveries. Stop the efforts if technique deteriorates.'},steps=steps)
            reason='Recent endurance and tempo are represented but short-hard-effort benefit is absent; current recovery and saved experience permit a small controlled dose.'
    if planned and mix['gaps']:reason+=' Recent mix gaps: '+', '.join(g.replace('_',' ') for g in mix['gaps'])+'. The saved plan still governs today.'
    if low:
        reason='Current recovery/load or recent feedback favors recovery rather than a training session; leave unused time free.'
        if sport=='cycling':definition=recovery_ride(min(minutes,30))
        else:return rest(reason)
    if planned and planned['definition'].get('review_hold'):return {**base,'status':'needs_review','questions':[planned['definition']['review_hold']['reason']],'session':None}
    return {**base,'status':'suggestion','session':definition,'reason':reason,'training_mix':mix,'questions':[],'warnings':['Recommendation only; your saved plan is unchanged.']+(['Readiness is incomplete; this suggestion stays easy.'] if readiness['score'] is None else [])}


def recent_mix(arguments,path=None):
    days=arguments.get('days',14)
    if type(days) is not int or not 7<=days<=42:raise ValueError('Choose a recent window of 7–42 days')
    tz=arguments.get('timezone') or 'UTC';timezone_info(tz)
    today=datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
    return {'tool':'get_recent_training_mix',**capability(path,today,tz,days)}
