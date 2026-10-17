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
    brief={**brief,'program_start':plan['starts_on']}
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
            for row in c.execute(f"SELECT m.metric_type,m.value,m.unit,a.started_at,a.id AS activity_id FROM activity_metrics m JOIN activities a ON a.id=m.activity_id WHERE a.id IN ({','.join('?' for _ in ids)}) ORDER BY a.started_at",ids):
                if row['metric_type'] in ('aerobic_training_effect','anaerobic_training_effect','normalized_power','average_power','exercise_load','intensity_factor','threshold_power','average_heart_rate','maximum_heart_rate'):
                    measures.setdefault(row['metric_type'],[]).append(dict(row))
        biological={}
        for row in c.execute("SELECT metric_type,value,unit,recorded_at FROM metric_readings WHERE source_name!='synthetic_fixture' AND recorded_at>=? ORDER BY recorded_at",((today-timedelta(days=7)).isoformat(),)):
            if row['recorded_at'][:10]>today.isoformat():continue
            if row['metric_type'] in ('sleep_score','hrv_last_night_average','hrv_nightly_average','hrv','resting_heart_rate','stress','stress_average','body_battery','body_battery_latest','vo2_cycling','vo2_running'):
                biological[row['metric_type']]=dict(row)
    with connect(path) as c:
        for row in c.execute("SELECT metric_type,value,unit,recorded_at FROM metric_readings WHERE source_name!='synthetic_fixture' AND metric_type IN ('vo2_cycling','vo2_running') AND substr(recorded_at,1,10)<=? ORDER BY recorded_at",(today.isoformat(),)):
            biological[row['metric_type']]=dict(row)
    sports=[]
    for sport in ('cycling','running','strength'):
        selected=[a for a in activities if (('cycl' in a['activity_type'].lower() or 'bik' in a['activity_type'].lower()) if sport=='cycling' else sport.removesuffix('ning') in a['activity_type'].lower())]
        selected_ids={a['id'] for a in selected};by_activity={identifier:{} for identifier in selected_ids}
        for metric,observations in measures.items():
            for observation in observations:
                if observation['activity_id'] in by_activity:by_activity[observation['activity_id']][metric]=observation['value']
        demanding=[]
        for a in selected:
            m=by_activity[a['id']];reasons=[]
            if m.get('intensity_factor',0)>=.9:reasons.append('Recorded intensity factor at least 0.90')
            if m.get('aerobic_training_effect',0)>=4:reasons.append('Recorded aerobic effect at least 4')
            if m.get('anaerobic_training_effect',0)>=2.5:reasons.append('Recorded anaerobic effect at least 2.5')
            if reasons:demanding.append({'activity_id':a['id'],'date':datetime.fromisoformat(a['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date().isoformat(),'reasons':reasons})
        def values(metric):return [m[metric] for m in by_activity.values() if metric in m]
        difficulty={'metric_coverage':sum(bool(m) for m in by_activity.values()),'demanding_sessions':demanding,'mean_intensity_factor':sum(values('intensity_factor'))/len(values('intensity_factor')) if values('intensity_factor') else None,'recorded_load_total':sum(values('exercise_load')) if values('exercise_load') else None,'mean_recorded_heart_rate':sum(values('average_heart_rate'))/len(values('average_heart_rate')) if values('average_heart_rate') else None,'note':'Recorded relative-intensity/load indicators guide conservative planning, not a physiological capacity test or proof of intent.'}
        sports.append({'difficulty':difficulty,'sport':sport,'activity_count':len(selected),'weekly_minutes':round(sum(a['duration_seconds'] or 0 for a in selected)/360),'longest_minutes':round(max((a['duration_seconds'] or 0 for a in selected),default=0)/60)})
    duration=sum(r['duration_seconds'] or 0 for r in activities)/60
    return {'sports':sports,'period_start':start.isoformat(),'period_end':today.isoformat(),'activity_count':len(activities),
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
    anchor=date.fromisoformat(state['starts_on'])
    first=anchor+timedelta(weeks=max(0,(today-anchor).days//7))
    last=anchor+timedelta(weeks=max(0,((today+timedelta(days=6))-anchor).days//7))
    for monday in sorted({first,last}):
        if monday.isoformat()>state['ends_on']:continue
        # The preview includes current workouts and fixed commitments in its volume limits.
        brief={**state['brief'],'fixed_events':[e for e in state['brief']['fixed_events'] if e['date']>=today.isoformat() and not any(w['scheduled_for'][:10]==e['date'] and json.loads(w['definition_json']).get('fixed_commitment') for w in _program_workouts(c,program))]}
        p=_preview(c,brief,monday,state['timezone'],now,None,resolve_ftp=False)
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
            wid='workout-'+str(uuid.uuid4())
            c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',(wid,child,session['sport'],definition['title'],session['scheduled_for'],encoded(definition)))
            _revision(c,_snapshot(c,wid))
    return list(dict.fromkeys(warnings))


def _reconcile_events(c,program,state,today,now):
    from .training_coach import _preview
    from .training_prescriptions import endurance
    notes=[];changes=[]
    linked={r[0] for r in c.execute('SELECT activity_id FROM training_feedback WHERE activity_id IS NOT NULL')}
    for w in _program_workouts(c,program):
        planned_start=datetime.fromisoformat(w['scheduled_for'])
        if w['completion_status']!='planned' or planned_start>=now:continue
        d=json.loads(w['definition_json']);candidates=[]
        if d.get('time_unspecified'):continue
        for a in c.execute("SELECT id,activity_type,started_at,duration_seconds FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND started_at>=?",((planned_start-timedelta(days=1)).date().isoformat(),)):
            if a['id'] in linked or a['duration_seconds'] is None:continue
            started=datetime.fromisoformat(a['started_at'].replace('Z','+00:00'))
            if started>=now or abs((started-planned_start).total_seconds())>3600:continue
            sport='cycling' if any(k in a['activity_type'].lower() for k in ('cycl','bik')) else 'running' if 'run' in a['activity_type'].lower() else 'strength' if 'strength' in a['activity_type'].lower() else None
            if sport==w['sport'] and abs(a['duration_seconds']/60-d['duration_minutes'])<=max(5,d['duration_minutes']*.15):candidates.append(a['id'])
        if len(candidates)==1:
            c.execute("UPDATE planned_workouts SET completion_status='completed',revision=revision+1 WHERE id=?",(w['id'],))
            c.execute('INSERT INTO training_feedback(workout_id,pain_or_illness,activity_id,updated_at) VALUES(?,0,?,?) ON CONFLICT(workout_id) DO UPDATE SET activity_id=excluded.activity_id,updated_at=excluded.updated_at',(w['id'],candidates[0],now.isoformat()));_revision(c,_snapshot(c,w['id']));linked.add(candidates[0])
            changes.append({'workout_id':w['id'],'title':w['title'],'action':'Matched completed activity','reason':'A unique same-sport recording matches the planned time and duration.'})
        elif len(candidates)>1:notes.append('Several recordings match '+w['title']+'; confirm its activity link before completion is recorded.')
    events=state['brief']['fixed_events'];ids={e['id'] for e in events if e.get('id')}
    rows=_program_workouts(c,program)
    for w in rows:
        d=json.loads(w['definition_json'])
        if w['completion_status']=='planned' and d.get('event_id') and d['event_id'] not in ids and w['publish_status']=='local' and datetime.fromisoformat(w['scheduled_for'])>=now:
            c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
            changes.append({'workout_id':w['id'],'title':w['title'],'action':'Cancelled removed event','reason':'The event was removed from the current program.'})
    for e in events:
        event_day=date.fromisoformat(e['date'])
        if event_day<today or event_day>today+timedelta(days=7):continue
        anchor=date.fromisoformat(state['starts_on'])
        week=anchor+timedelta(weeks=max(0,(event_day-anchor).days//7))
        p=_preview(c,state['brief'],week,state['timezone'],now,None,resolve_ftp=False)
        fixed=next((s for s in p['sessions'] if s['definition'].get('event_id')==e['id']),None)
        if not fixed:
            notes.extend(p['questions']);continue
        scheduled=datetime.fromisoformat(fixed['scheduled_for']);ending=scheduled+timedelta(minutes=fixed['definition']['duration_minutes'])
        if scheduled<now and not fixed['definition'].get('time_unspecified'):continue
        demanding=e.get('is_race') or e['effort'] in ('hard','unknown') or fixed['definition']['duration_minutes']>=90 or (e.get('elevation_gain_meters') or 0)>=1000
        protected=2 if e.get('is_race') else 1
        existing=None;blocked=False
        for w in _program_workouts(c,program):
            d=json.loads(w['definition_json']);begin=datetime.fromisoformat(w['scheduled_for']);day=begin.astimezone(ZoneInfo(state['timezone'])).date()
            if d.get('event_id')==e['id']:
                existing=w;continue
            if w['completion_status']!='planned' or (begin.astimezone(ZoneInfo(state['timezone'])).date()<today if d.get('time_unspecified') else begin<now):continue
            overlap=not (fixed['definition'].get('time_unspecified') or d.get('time_unspecified')) and scheduled<begin+timedelta(minutes=d['duration_minutes']) and begin<ending
            if overlap and (d.get('fixed_commitment') or w['publish_status']!='local'):
                notes.append('Event '+e['title']+' conflicts with another fixed/published session; choose a time or event priority.');blocked=True;continue
            if overlap:
                c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
                changes.append({'workout_id':w['id'],'title':w['title'],'action':'Replaced by upcoming event','reason':e['title']})
            elif demanding and abs((day-event_day).days)<=protected and (d['duration_minutes']>=60 or d.get('workout_kind') in ('tempo','threshold','vo2','short_efforts')):
                if d.get('fixed_commitment') or w['publish_status']!='local':notes.append('Review fixed session '+w['title']+' near '+e['title']);continue
                if w['sport']=='strength':
                    c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
                    action='Rest around event'
                else:
                    replacement=endurance('recovery',min(30,d['duration_minutes']),state['brief'],w['sport'],today=today)
                    replacement.update({key:d[key] for key in ('scheduled_date','time_unspecified','schedule_timezone') if key in d})
                    replacement['rationale'].append('Recovery around '+e['title'])
                    c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(replacement['title'],encoded(replacement),w['id']));_revision(c,_snapshot(c,w['id']));action='Recovery around event'
                changes.append({'workout_id':w['id'],'title':w['title'],'action':action,'reason':e['title']})
        if blocked:continue
        definition=fixed['definition']
        if existing:
            if existing['completion_status']!='planned':continue
            if existing['publish_status']!='local':notes.append('Published event needs manual review: '+e['title']);continue
            if definition!=json.loads(existing['definition_json']) or existing['scheduled_for']!=fixed['scheduled_for']:
                c.execute('UPDATE planned_workouts SET title=?,scheduled_for=?,definition_json=?,revision=revision+1 WHERE id=?',(fixed['title'],fixed['scheduled_for'],encoded(definition),existing['id']));_revision(c,_snapshot(c,existing['id']))
        else:
            wid='workout-'+str(uuid.uuid4());c.execute('INSERT INTO planned_workouts(id,training_plan_id,sport,title,scheduled_for,definition_json) VALUES(?,?,?,?,?,?)',(wid,program,fixed['sport'],fixed['title'],fixed['scheduled_for'],encoded(definition)));_revision(c,_snapshot(c,wid))
            changes.append({'workout_id':wid,'title':fixed['title'],'action':'Scheduled upcoming event','reason':'Preserved its stated demands.'})
    quality_assigned=any(json.loads(w['definition_json']).get('workout_kind') in ('tempo','threshold','vo2','short_efforts','long_tempo') or json.loads(w['definition_json']).get('fixed_commitment') and 'hard' in json.loads(w['definition_json']).get('effort_target',{}).get('description','') for w in _program_workouts(c,program) if w['completion_status']=='planned')
    for w in _program_workouts(c,program):
        d=json.loads(w['definition_json'])
        if w['completion_status']!='planned' or w['publish_status']!='local' or d.get('fixed_commitment') or datetime.fromisoformat(w['scheduled_for'])<now:continue
        if w['sport']=='cycling' and d.get('workout_kind') and (d.get('program_ftp')!=state['brief'].get('ftp_watts') or d.get('program_goal')!=state['brief'].get('goal') or d.get('calibration')!=state['brief'].get('calibration') or d.get('workout_location')!=state['brief'].get('workout_location','outdoor')):
            kind=d['workout_kind'];minutes=d['duration_minutes']
            if d.get('program_goal')!=state['brief'].get('goal'):
                if state['brief']['goal']=='ftp' and not quality_assigned and minutes>=45:kind='threshold';minutes=min(minutes,60);quality_assigned=True
                elif state['brief']['goal']!='ftp' and kind in ('threshold','vo2'):kind='endurance'
            replacement=endurance(kind,minutes,state['brief'],today=today)
            c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(replacement['title'],encoded(replacement),w['id']));_revision(c,_snapshot(c,w['id']))
            changes.append({'workout_id':w['id'],'title':replacement['title'],'action':'Updated targets','reason':'Use the current program direction and confirmed calibration.'})
    answers=_context(c,now)['answers']
    rows=_program_workouts(c,program)
    anchor=date.fromisoformat(state['starts_on'])
    for week,sport in {(anchor+timedelta(weeks=(datetime.fromisoformat(w['scheduled_for']).date()-anchor).days//7),w['sport']) for w in rows if w['completion_status'] in ('planned','completed')}:
        selected=[w for w in rows if w['sport']==sport and w['completion_status'] in ('planned','completed') and week<=datetime.fromisoformat(w['scheduled_for']).date()<=week+timedelta(days=6)]
        total=sum(json.loads(w['definition_json'])['duration_minutes'] for w in selected);budget=answers.get('weekly_minutes',{}).get(sport,0);excess=total-budget
        for w in sorted(selected,key=lambda w:json.loads(w['definition_json'])['duration_minutes'],reverse=True):
            if excess<=0:break
            d=json.loads(w['definition_json'])
            if w['completion_status']!='planned' or d.get('fixed_commitment') or w['publish_status']!='local' or datetime.fromisoformat(w['scheduled_for'])<now:continue
            old=d['duration_minutes'];new=old-excess;minimum=20 if sport!='running' else 15
            if new<minimum or sport=='strength':
                c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));excess-=old
            else:
                replacement=endurance('endurance',int(new),state['brief'],sport,today=today)
                c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(replacement['title'],encoded(replacement),w['id']));excess-=old-new
            _revision(c,_snapshot(c,w['id']));changes.append({'workout_id':w['id'],'title':w['title'],'action':'Adjusted weekly volume','reason':'Fit the event while preserving the confirmed weekly budget.'})
        if excess>0:notes.append(f'{sport}: fixed/completed work exceeds the weekly budget by {excess:g} minutes. Review volume or event priority; no fixed event was shortened.')
    return changes,list(dict.fromkeys(notes))


def review(path=None,timezone_name='UTC',now=None):
    timezone_info(timezone_name);now=now or datetime.now(timezone.utc)
    with connect(path) as c:
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
    if not program:return {'program':None,'workouts':[],'review':None}
    state=json.loads(program['state_json'])
    from .training_coach import validate_brief
    state['brief']=validate_brief(state['brief']);tz=state['timezone'];today=now.astimezone(ZoneInfo(tz)).date()
    capabilities=capability(path,today,tz)
    from .readiness import readiness_history
    readiness=readiness_history(today,1,tz,path,now=now)['latest']
    from .training_load_charts import daily_rows
    loads=[r for r in daily_rows(path) if (today-timedelta(days=2)).isoformat()<=r['date']<=today.isoformat()]
    load=loads[-1] if loads else None
    reasons=[]
    if readiness['score'] is not None and readiness['score']<50:reasons.append('Current readiness is in the recovery-focus band below 50; use recovery rather than a demanding session.')
    autonomic=next((g for g in readiness.get('groups',[]) if g['name']=='autonomic'),{})
    if autonomic.get('hrv_z') is not None and autonomic['hrv_z']<-1.5:reasons.append('Overnight HRV is substantially below its personal baseline.')
    if autonomic.get('rhr_z') is not None and autonomic['rhr_z']>1.5:reasons.append('Resting heart rate is elevated relative to its personal baseline.')
    if load and load['high'] is not None and load['acute']>load['high']:reasons.append('Garmin acute load is above its recorded optimal range.')
    if any(d['date']>=(today-timedelta(days=1)).isoformat() for sport in capabilities['sports'] for d in sport['difficulty']['demanding_sessions']):reasons.append('A demanding recorded session occurred today or yesterday; preserve recovery before more demanding work.')
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
        event_changes,event_warnings=_reconcile_events(c,program['plan_id'],state,today,now) if program['status']=='active' else ([],[])
        reviewed_today=any(json.loads(r[0]).get('date')==today.isoformat() and json.loads(r[0]).get('commitment_revision',0)==state.get('commitment_revision',0) for r in c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=?',(program['plan_id'],)))
        if program['status']=='active' and not reviewed_today:warnings=_fill(c,program['plan_id'],state,today,now)
        warnings.extend(event_warnings)
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
        report=json.loads(old[0]) if old else {'date':today.isoformat(),'commitment_revision':state.get('commitment_revision',0),'reasons':reasons,'changes':event_changes,'warnings':warnings,'capabilities':capabilities,'readiness':{'date':readiness['date'],'score':readiness['score'],'status':readiness['status']},'load':load}
        from .training_ftp import resolve
        latest_ftp=resolve(c,today)
        approved_ftp=state['brief'].get('ftp_watts')
        approved_date=state['brief'].get('calibration',{}).get('ftp_confirmed_on')
        report['ftp_progress']={'goal':state['brief'].get('goal'),'approved_watts':approved_ftp,'approved_measurement_date':approved_date,'latest_measurement':latest_ftp,'review_update_available':bool(latest_ftp.get('measurement_date') and (not approved_date or latest_ftp['measurement_date']>approved_date) and latest_ftp.get('watts')!=approved_ftp),'note':'Progress uses dated cycling FTP measurements only. A single ride does not establish FTP improvement. Updating approved targets requires plan preview and approval.'}
        report['current_block']=next((block for block in state['blocks'] if block['starts_on']<=today.isoformat()<=(date.fromisoformat(block['starts_on'])+timedelta(days=6)).isoformat()),None)
        if not old:
            for w in upcoming:
                definition=json.loads(w['definition_json']);schedule_metadata={key:definition[key] for key in ('scheduled_date','time_unspecified','schedule_timezone') if key in definition};training_block=definition.get('training_block');day=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()
                demanding=definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','long_tempo') or definition.get('template_id')=='cycling_controlled_intervals' or definition.get('duration_minutes',0)>=90 or 'hard' in definition.get('effort_target',{}).get('description','').lower()
                action='Kept';why='Consistent with the active plan; no current reduction signal.'
                if program['status']=='active' and (pain or (reasons and demanding and (day<=today+timedelta(days=1) or adverse))):
                    if pain or definition.get('fixed_commitment') or w['publish_status']!='local':
                        action='Review required';why='; '.join(reasons)
                        definition['review_hold']={'date':today.isoformat(),'reason':why}
                    else:
                        minutes=min(30,definition['duration_minutes'])
                        if w['sport']=='strength':definition=workout_definition('strength_foundation',max(20,minutes),_context(c,now)['answers'])
                        else:
                            from .training_prescriptions import endurance
                            definition=endurance('recovery',minutes,state['brief'],w['sport'],today=today)
                        definition.update(schedule_metadata)
                        if training_block:definition['training_block']=training_block
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
    if status not in ('active','paused','completed','cancelled'):raise ValueError('Invalid plan status')
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not p:raise ValueError('No active plan')
        if p['status']==status:return
        if p['status'] in ('completed','cancelled'):raise ValueError('This plan has ended; accept a new reviewed plan to start again')
        if status in ('completed','cancelled'):
            workouts=_program_workouts(c,p['plan_id'])
            for w in workouts:
                if w['completion_status']=='planned':
                    c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
            plan_ids={w['training_plan_id'] for w in workouts}|{p['plan_id']}
            for identifier in plan_ids:c.execute("UPDATE training_plans SET status='completed' WHERE id=?",(identifier,))
        c.execute("UPDATE active_training_program SET status=?,revision=revision+1 WHERE id=1",(status,))
        if c.execute('SELECT changes()').fetchone()[0]!=1:raise ValueError('No active plan')


def reschedule(identifier,scheduled_for,expected_revision,path=None,now=None,scheduled_date=None,start_time=None):
    now=now or datetime.now(timezone.utc)
    date_only=scheduled_date is not None and start_time is None or isinstance(scheduled_for,str) and len(scheduled_for)==10
    local=None if scheduled_date is not None or date_only else datetime.fromisoformat(scheduled_for.replace('Z','+00:00'))
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');row=_snapshot(c,identifier)
        if not row or row['revision']!=expected_revision:raise ValueError('Session changed; refresh first')
        if row['completion_status']!='planned' or row['publish_status']!='local' or row['garmin_workout_id']:raise ValueError('Only planned local sessions can be moved')
        program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if not program or identifier not in {w['id'] for w in _program_workouts(c,program['plan_id'])}:raise ValueError('Session does not belong to the active plan')
        state=json.loads(program['state_json']);tz=ZoneInfo(state['timezone'])
        if scheduled_date is not None or date_only:
            from .training_coach import _scheduled
            local=datetime.fromisoformat(_scheduled(scheduled_date or scheduled_for,start_time,state['timezone']))
        day=local.astimezone(tz).date()
        if not local.tzinfo or (day<now.astimezone(tz).date() if date_only else local<now):raise ValueError('Choose a current or future scheduled day')
        if not date.fromisoformat(state['starts_on'])<=day<=date.fromisoformat(state['ends_on']):raise ValueError('Choose a date within the active plan')
        if local.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=local.astimezone(tz).replace(tzinfo=None):raise ValueError('Choose a valid local time')
        definition=json.loads(row['definition_json']);end=local+timedelta(minutes=definition['duration_minutes'])
        definition.update(scheduled_date=day.isoformat(),time_unspecified=date_only,schedule_timezone=state['timezone'])
        day_total=definition['duration_minutes'];date_budget_required=date_only
        for other in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status='planned'",(identifier,)):
            start=datetime.fromisoformat(other['scheduled_for']);d=json.loads(other['definition_json'])
            if start.astimezone(tz).date()==day:
                day_total+=d['duration_minutes'];date_budget_required=date_budget_required or d.get('time_unspecified',False)
            if not(date_only or d.get('time_unspecified')) and local<start+timedelta(minutes=d['duration_minutes']) and start<end:raise ValueError('This overlaps another planned workout; move or cancel it first')
            if (definition['duration_minutes']>=90 or definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','long_tempo') or definition.get('template_id')=='cycling_controlled_intervals') and abs((start.astimezone(tz).date()-day).days)<=1 and (d['duration_minutes']>=90 or d.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','long_tempo') or d.get('template_id')=='cycling_controlled_intervals'):raise ValueError('Keep a recovery day between demanding sessions')
        if date_budget_required:
            slot=next((slot for slot in _context(c,now)['answers'].get('availability',[]) if slot['weekday']==day.weekday()),None)
            if not slot or day_total>slot['minutes']:raise ValueError('The scheduled day exceeds confirmed availability')
        c.execute('UPDATE planned_workouts SET scheduled_for=?,definition_json=?,revision=revision+1 WHERE id=?',(local.isoformat(),encoded(definition),identifier));_revision(c,_snapshot(c,identifier))
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
    future=[w for w in workouts if datetime.fromisoformat(w['scheduled_for'])>=now or w['definition'].get('time_unspecified') and w.get('scheduled_date',w['scheduled_for'][:10])>=today.isoformat()]
    if 'long' in text:future=[w for w in future if w['definition']['duration_minutes']>=90]
    if re.search(r'\b(ride|cycling|bike)\b',text):future=[w for w in future if w['sport']=='cycling']
    if not future:raise ValueError('No matching upcoming workout. Select a session below to edit.')
    workout=sorted(future,key=lambda w:w['scheduled_for'])[0]
    if re.search(r'\b(move|change|reschedule)\b',text):
        day=today if 'today' in text else today+timedelta(days=1) if 'tomorrow' in text else None
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
        if dates:day=date.fromisoformat(dates[-1])
        if day is None:
            for i,name in enumerate(('monday','tuesday','wednesday','thursday','friday','saturday','sunday')):
                if name in text:day=today+timedelta(days=(i-today.weekday())%7)
        if day is None:raise ValueError('Which day should the workout move to? Include today, tomorrow, a weekday or a date.')
        old=datetime.fromisoformat(workout['scheduled_for']).astimezone(ZoneInfo(tz));clock=re.search(r'\b(\d{1,2}:\d{2})\b',text)
        if workout['definition'].get('time_unspecified') and not clock:
            changes={'scheduled_date':day.isoformat(),'start_time':None,'timezone':tz}
            if apply:reschedule(workout['id'],None,workout['revision'],path,now,scheduled_date=day.isoformat(),start_time=None)
            return {'message':workout['title']+' → '+day.isoformat()+' (time optional)','workout_id':workout['id'],'expected_revision':workout['revision'],'changes':changes,'kind':'schedule','status':'saved' if apply else 'proposal'}
        scheduled=datetime.fromisoformat(f"{day}T{clock[1] if clock else old.strftime('%H:%M')}").replace(tzinfo=ZoneInfo(tz))
        if apply:reschedule(workout['id'],scheduled.isoformat(),workout['revision'],path,now)
        return {'message':f"{workout['title']} → {scheduled.strftime('%Y-%m-%d %H:%M')}",'workout_id':workout['id'],'expected_revision':workout['revision'],'changes':{'scheduled_for':scheduled.isoformat()},'kind':'schedule','status':'saved' if apply else 'proposal'}
    raise ValueError('For effort or soreness feedback, choose the session below and save your note there. To move a workout, say its type and new day/time.')


def propose_adjustment(arguments,path=None):
    if arguments.get('workout_id'):
        active=read_active({},path)
        if active['program'] is None:raise ValueError('Accept a training plan first')
        with connect(path) as c:w=next((w for w in _program_workouts(c,active['program']['plan_id']) if w['id']==arguments['workout_id']),None)
        if w is None:raise ValueError('Choose a session from the active program')
        changes=arguments.get('changes')
        allowed={'completion_status','effort','soreness','pain_or_illness','notes','activity_id','strength_sets'}
        if not isinstance(changes,dict) or not changes or set(changes)-allowed:raise ValueError('Provide explicit feedback/completion changes only')
        return {'tool':'propose_training_adjustment','workout_id':w['id'],'expected_revision':w['revision'],'changes':changes,'kind':'feedback','status':'proposal','message':'Review recorded feedback/completion for '+w['title']+'. Nothing is saved yet.'}
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
    sport_capacity=next((r for r in capacity.get('sports',[]) if r['sport']==sport),None)
    if sport_capacity and sport_capacity['activity_count']>=6 and sport_capacity['longest_minutes']>0:dose=min(dose,max(20,sport_capacity['longest_minutes']))
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
    if sport=='cycling':
        from .training_prescriptions import endurance
        from .training_coach import read_brief
        b=program['state']['brief'] if program and program['status']=='active' else read_brief(path)['brief']
        kind='recovery' if low else planned['definition'].get('workout_kind','endurance') if planned and readiness['score'] is not None else 'tempo' if 'tempo' in definition['title'].lower() else 'short_efforts' if 'acceleration' in definition['title'].lower() else 'endurance'
        definition=endurance(kind,definition['duration_minutes'],b,today=today)
    if planned and planned['definition'].get('review_hold'):return {**base,'status':'needs_review','questions':[planned['definition']['review_hold']['reason']],'session':None}
    return {**base,'status':'suggestion','session':definition,'reason':reason,'training_mix':mix,'questions':[],'warnings':['Recommendation only; your saved plan is unchanged.']+(['Readiness is incomplete; this suggestion stays easy.'] if readiness['score'] is None else [])}


def recent_mix(arguments,path=None):
    days=arguments.get('days',14)
    if type(days) is not int or not 7<=days<=42:raise ValueError('Choose a recent window of 7–42 days')
    tz=arguments.get('timezone') or 'UTC';timezone_info(tz)
    today=datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
    return {'tool':'get_recent_training_mix',**capability(path,today,tz,days)}
