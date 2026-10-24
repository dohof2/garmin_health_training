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
    if plan['deleted_at']:raise ValueError('A removed plan cannot be activated')
    context=json.loads(plan['context_json'])
    brief=context.get('brief')
    if not brief:
        from .training_coach import DEFAULT
        brief={**DEFAULT,'goal':'general','horizon_weeks':4}
    from .training_coach import roadmap
    blocks=context.get('roadmap') or roadmap(brief,date.fromisoformat(plan['starts_on']),context['preferences']['answers'])
    program_start=brief.get('program_start') or plan['starts_on']
    brief={**brief,'program_start':program_start}
    state={'brief':brief,'blocks':blocks,'timezone':context.get('timezone','UTC'),
           'starts_on':program_start,'ends_on':(date.fromisoformat(program_start)+timedelta(weeks=len(blocks),days=-1)).isoformat()}
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
        coverage_row=c.execute("SELECT coverage_start,coverage_end FROM sync_checkpoints WHERE data_type='activities'").fetchone()
        activity_coverage=dict(coverage_row) if coverage_row else {}
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
        sports.append({'recent_durations':[{'date':datetime.fromisoformat(a['started_at'].replace('Z','+00:00')).astimezone(ZoneInfo(tz)).date().isoformat(),'minutes':round(a['duration_seconds']/60,1)} for a in selected if a['duration_seconds']], 'difficulty':difficulty,'sport':sport,'activity_count':len(selected),'weekly_minutes':round(sum(a['duration_seconds'] or 0 for a in selected)/360),'longest_minutes':round(max((a['duration_seconds'] or 0 for a in selected),default=0)/60)})
    duration=sum(r['duration_seconds'] or 0 for r in activities)/60
    return {'activity_coverage':activity_coverage,'sports':sports,'period_start':start.isoformat(),'period_end':today.isoformat(),'activity_count':len(activities),
            'weekly_minutes':round(duration/6),'longest_minutes':round(max([r['duration_seconds'] or 0 for r in activities],default=0)/60),
            'aerobic_effect':_mean(measures.get('aerobic_training_effect',[])),
            'anaerobic_effect':_mean(measures.get('anaerobic_training_effect',[])),
            'latest_normalized_power':(measures.get('normalized_power') or [None])[-1],
            'training_mix':training_mix,'biological':biological,'note':'Recorded workload and training effects describe recent exposure; they do not measure a physiological ceiling or establish FTP.'}


def _mean(rows):return round(sum(r['value'] for r in rows)/len(rows),1) if rows else None


def _program_workouts(c,identifier):
    from .training_lifecycle import membership
    ids=membership(c,identifier);rows=[]
    for identity in ids:
        rows.extend(dict(row) for row in c.execute("SELECT w.*,p.context_json FROM planned_workouts w JOIN training_plans p ON p.id=w.training_plan_id WHERE p.id=? AND p.deleted_at IS NULL ORDER BY w.scheduled_for,w.id",(identity,)))
    return sorted(rows,key=lambda row:(row['scheduled_for'],row['id']))


def _fill(c,program,state,today,now):
    """Generate only the visible seven-day horizon using accepted constraints."""
    context=_context(c,now,brief=state['brief'],timezone_name=state['timezone'])
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
        occupied={(w['scheduled_for'][:10],json.loads(w['definition_json']).get('schedule_slot_id'),w['sport']) for w in _program_workouts(c,program)}
        sessions=[s for s in p['sessions'] if (s['scheduled_for'][:10],s['definition'].get('schedule_slot_id'),s['sport']) not in occupied and today<=datetime.fromisoformat(s['scheduled_for']).date()<=min(today+timedelta(days=6),date.fromisoformat(state['ends_on']))]
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
    from .training_completion import reconcile
    changes,notes=reconcile(c,_program_workouts(c,program),state['timezone'],now)
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
            if overlap and (d.get('fixed_commitment') or d.get('user_adjusted') or w['publish_status']!='local'):
                notes.append('Event '+e['title']+' conflicts with another fixed/published session; choose a time or event priority.');blocked=True;continue
            if overlap:
                c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
                changes.append({'workout_id':w['id'],'title':w['title'],'action':'Replaced by upcoming event','reason':e['title']})
            elif demanding and abs((day-event_day).days)<=protected and (d['duration_minutes']>=60 or d.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic')):
                if d.get('fixed_commitment') or d.get('user_adjusted') or w['publish_status']!='local':notes.append('Review protected session '+w['title']+' near '+e['title']);continue
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
    quality_assigned=any(json.loads(w['definition_json']).get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo') or json.loads(w['definition_json']).get('fixed_commitment') and 'hard' in json.loads(w['definition_json']).get('effort_target',{}).get('description','') for w in _program_workouts(c,program) if w['completion_status']=='planned')
    for w in _program_workouts(c,program):
        d=json.loads(w['definition_json'])
        if w['completion_status']!='planned' or w['publish_status']!='local' or d.get('fixed_commitment') or d.get('user_adjusted') or datetime.fromisoformat(w['scheduled_for'])<now:continue
        if w['sport']=='cycling' and d.get('workout_kind') and (d.get('program_ftp')!=state['brief'].get('ftp_watts') or d.get('program_goal')!=state['brief'].get('goal') or d.get('calibration')!=state['brief'].get('calibration') or d.get('workout_location')!=state['brief'].get('workout_location','outdoor')):
            kind=d['workout_kind'];minutes=d['duration_minutes']
            if d.get('program_goal')!=state['brief'].get('goal'):
                if state['brief']['goal']=='ftp' and not quality_assigned and minutes>=45:kind='threshold';minutes=min(minutes,60);quality_assigned=True
                elif state['brief']['goal']!='ftp' and kind in ('threshold','vo2'):kind='endurance'
            replacement=endurance(kind,minutes,state['brief'],today=today)
            c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(replacement['title'],encoded(replacement),w['id']));_revision(c,_snapshot(c,w['id']))
            changes.append({'workout_id':w['id'],'title':replacement['title'],'action':'Updated targets','reason':'Use the current program direction and confirmed calibration.'})
    review_context=_context(c,now,brief=state['brief'],timezone_name=state['timezone'])
    answers=review_context['answers']
    rows=_program_workouts(c,program)
    anchor=date.fromisoformat(state['starts_on'])
    for week,sport in {(anchor+timedelta(weeks=(datetime.fromisoformat(w['scheduled_for']).date()-anchor).days//7),w['sport']) for w in rows if w['completion_status'] in ('planned','completed')}:
        selected=[w for w in rows if w['sport']==sport and w['completion_status'] in ('planned','completed') and week<=datetime.fromisoformat(w['scheduled_for']).date()<=week+timedelta(days=6)]
        total=sum(json.loads(w['definition_json'])['duration_minutes'] for w in selected);budget=answers.get('weekly_minutes',{}).get(sport,0);excess=total-budget
        for w in sorted(selected,key=lambda w:json.loads(w['definition_json'])['duration_minutes'],reverse=True):
            if excess<=0:break
            d=json.loads(w['definition_json'])
            if w['completion_status']!='planned' or d.get('fixed_commitment') or d.get('user_adjusted') or w['publish_status']!='local' or datetime.fromisoformat(w['scheduled_for'])<now:continue
            old=d['duration_minutes'];new=old-excess;minimum=20 if sport!='running' else 15
            if new<minimum or sport=='strength':
                c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));excess-=old
            else:
                replacement=endurance('endurance',int(new),state['brief'],sport,today=today)
                c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(replacement['title'],encoded(replacement),w['id']));excess-=old-new
            _revision(c,_snapshot(c,w['id']));changes.append({'workout_id':w['id'],'title':w['title'],'action':'Adjusted weekly volume','reason':'Fit the event while preserving the confirmed weekly budget.'})
        if excess>0:notes.append(f'{sport}: fixed/completed work exceeds the weekly budget by {excess:g} minutes. Review volume or event priority; no fixed event was shortened.')
    return changes,list(dict.fromkeys(notes))


def _cycling_review_targets(rows,answers,estimate,today,tz,other_rows=()):
    """Reallocate local generated rides without replacing a plan or published rows."""
    from .training_constraints import slots_for,day_limit
    from .training_coach import _cycling_allocations
    days=answers.get('week_schedule',[])
    primary=[slot for day in days if day['mode']=='training' and day['activities']
             for slot in day['activities'][:1] if slot['sport']=='cycling' and slot['max_minutes']>=90]
    longest=max((slot['max_minutes'] for slot in primary),default=0)
    preferred=[slot['slot_id'] for slot in primary if slot['max_minutes']==longest]
    long_slot=preferred[0] if len(preferred)==1 else None
    candidates=[];assigned={};caps={};long_id=None;used_slots=set()
    for row in rows:
        definition=json.loads(row['definition_json'])
        day=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()
        if row['completion_status']!='planned' or day<today or row['publish_status']!='local' or row['garmin_workout_id'] or definition.get('fixed_commitment') or definition.get('user_adjusted'):
            continue
        slots=slots_for(days,day.weekday(),'cycling')
        slot=next((slot for slot in slots if slot['slot_id']==definition.get('schedule_slot_id')),None)
        if slot is None and len(slots)==1:slot=slots[0]
        if slot is None:continue  # Ambiguous/moved sessions need explicit slot review.
        if (day,slot['slot_id']) in used_slots:continue
        used_slots.add((day,slot['slot_id']))
        candidates.append(row);assigned[row['id']]=slot
        current=definition['duration_minutes']
        automatic=bool(definition.get('planning_policy_version') or definition.get('workout_kind') in ('long_endurance','climbing_endurance','long_tempo'))
        desired=estimate.get('long_session_minutes',current) if automatic and slot['slot_id']==long_slot else max(60,current) if automatic else current
        if slot['slot_id']==long_slot:long_id=row['id']
        # Preserve recovery sessions, novice limits, and recovery/taper weeks.
        if definition.get('workout_kind')=='recovery' or answers.get('experience',{}).get('cycling')=='new' or estimate.get('progression',{}).get('recovery_week'):
            desired=min(current,30)
        if definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic'):
            desired=min(desired,60)
        other_minutes=sum(json.loads(peer['definition_json'])['duration_minutes'] for peer in other_rows
                          if peer['completion_status'] in ('planned','completed') and datetime.fromisoformat(peer['scheduled_for']).astimezone(ZoneInfo(tz)).date()==day)
        caps[row['id']]=min(desired,slot['max_minutes'],estimate.get('long_session_minutes',desired),max(0,day_limit(days,day.weekday())-other_minutes))
    candidate_ids={row['id'] for row in candidates}
    daily_remaining={}
    for row in sorted(candidates,key=lambda row:(assigned[row['id']]['slot_id']!=long_slot,row['scheduled_for'],row['id'])):
        day=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()
        if day not in daily_remaining:
            peers=[peer for peer in rows if peer['id'] not in candidate_ids]+list(other_rows)
            committed=sum(json.loads(peer['definition_json'])['duration_minutes'] for peer in peers
                          if peer['completion_status'] in ('planned','completed') and datetime.fromisoformat(peer['scheduled_for']).astimezone(ZoneInfo(tz)).date()==day)
            daily_remaining[day]=max(0,day_limit(days,day.weekday())-committed)
        caps[row['id']]=min(caps[row['id']],daily_remaining[day]);daily_remaining[day]-=caps[row['id']]
    # Past plans and all publication states reserve their dose too. Never spend
    # their minutes twice just because a published ride is before today.
    reserved=sum(json.loads(row['definition_json'])['duration_minutes'] for row in rows
                 if row['id'] not in candidate_ids and row['completion_status'] in ('planned','completed'))
    ceiling=min(answers.get('weekly_minutes',{}).get('cycling',0),estimate.get('effective_ceiling_minutes',0))
    targets=_cycling_allocations(caps,max(0,ceiling-reserved),long_id)
    return {row['id']:targets.get(row['id'],0) for row in candidates},long_id,assigned


REVIEW_POLICY='training-review-v7-multiweek-edits'

def review(path=None,timezone_name='UTC',now=None,trigger='auto'):
    timezone_info(timezone_name);now=now or datetime.now(timezone.utc)
    with connect(path) as c:
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
    if not program:return {'program':None,'workouts':[],'review':None}
    if trigger not in ('auto','manual'):raise ValueError('Choose auto or manual review')
    local_date=now.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    with connect(path) as gate_connection:
        from .training_lifecycle import guard
        root=guard(gate_connection,program['plan_id']);input_revision=str(root['plan_revision'])+':'+str(program['revision'])
        gate=gate_connection.execute('SELECT * FROM training_review_gate WHERE plan_id=?',(program['plan_id'],)).fetchone()
    if program['status']!='active' or trigger=='auto' and gate and gate['local_date']==local_date and gate['timezone']==timezone_name and gate['input_revision']==input_revision and gate['policy_version']==REVIEW_POLICY:return active_view(path,timezone_name,now)
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
    if readiness['score'] is not None and readiness['score']<60:reasons.append('Lower readiness supports reviewing intensity alongside actual workload and tolerance; it does not require rest by itself.')
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
        if not fresh or fresh['plan_id']!=program['plan_id'] or fresh['revision']!=program['revision']:raise ValueError('Active plan changed; review again')
        from .training_lifecycle import guard
        root_now=guard(c,program['plan_id'])
        if str(root_now['plan_revision'])+':'+str(fresh['revision'])!=input_revision:raise ValueError('Training inputs changed during review; review again')
        gate_now=c.execute('SELECT * FROM training_review_gate WHERE plan_id=?',(program['plan_id'],)).fetchone()
        if trigger=='auto' and gate_now and gate_now['local_date']==local_date and gate_now['timezone']==timezone_name and gate_now['input_revision']==input_revision and gate_now['policy_version']==REVIEW_POLICY:return active_view(path,timezone_name,now)
        warnings=[]
        if program['status']=='active' and today.isoformat()>state['ends_on']:
            c.execute("UPDATE active_training_program SET status='completed',revision=revision+1 WHERE id=1")
            program={**dict(program),'status':'completed'}
        event_changes,event_warnings=_reconcile_events(c,program['plan_id'],state,today,now) if program['status']=='active' else ([],[])
        reviewed_today=any(json.loads(r[0]).get('date')==today.isoformat() and json.loads(r[0]).get('commitment_revision',0)==state.get('commitment_revision',0) for r in c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=?',(program['plan_id'],)))
        if program['status']=='active':warnings=_fill(c,program['plan_id'],state,today,now)
        warnings.extend(event_warnings)
        if program['status']!='active':warnings.append('Plan '+program['status']+': automatic schedule changes are stopped.')
        feedback=[dict(r) for r in c.execute('SELECT f.*,w.training_plan_id,w.sport,w.completion_status FROM training_feedback f JOIN planned_workouts w ON w.id=f.workout_id WHERE f.updated_at>=?',((today-timedelta(days=7)).isoformat(),))]
        adverse=[f for f in feedback if f['pain_or_illness'] or (f['effort'] or 0)>=8 or (f['soreness'] or 0)>=5 or re.search(r'\b(too hard|exhausted|could not finish|couldn.t finish|too tired)\b',f['notes'] or '',re.I)]
        pain=bool(_context(c,now)['answers'].get('pain_or_illness')) or any(f['pain_or_illness'] for f in adverse)
        if adverse:reasons.append('Recent effort, soreness or session notes indicate difficulty; reduce upcoming demanding sessions.')
        if pain:reasons.append('Reported pain or illness: upcoming training is held for your review.')
        from .training_prescriptions import cycling_dose,recovery_policy
        adaptation=recovery_policy(readiness,load,feedback,capabilities,today)
        if pain:adaptation['level']='hold'
        workouts=_program_workouts(c,program['plan_id'])
        upcoming=[w for w in workouts if w['completion_status']=='planned' and today<=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()<=today+timedelta(days=6)]
        state_key={'review_policy_version':REVIEW_POLICY,'planning_policy_version':'cycling-dose-v1','recovery_policy_version':'recovery-context-v1','date':today.isoformat(),'program_revision':program['revision'],'readiness':readiness.get('score'),'load':load,'feedback':feedback,'capabilities':capabilities,'workouts':[(w['id'],w['revision']) for w in upcoming]}
        fingerprint=hashlib.sha256(encoded(state_key).encode()).hexdigest()
        old=c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=? AND fingerprint=?',(program['plan_id'],fingerprint)).fetchone()
        report=json.loads(old[0]) if old else {'date':today.isoformat(),'commitment_revision':state.get('commitment_revision',0),'reasons':reasons,'changes':event_changes,'warnings':warnings,'capabilities':capabilities,'readiness':{'date':readiness['date'],'score':readiness['score'],'status':readiness['status']},'load':load}
        from .training_ftp import resolve
        latest_ftp=resolve(c,today)
        approved_ftp=state['brief'].get('ftp_watts')
        approved_date=state['brief'].get('calibration',{}).get('ftp_confirmed_on')
        report['ftp_progress']={'goal':state['brief'].get('goal'),'approved_watts':approved_ftp,'approved_measurement_date':approved_date,'latest_measurement':latest_ftp,'review_update_available':bool(latest_ftp.get('measurement_date') and (not approved_date or latest_ftp['measurement_date']>approved_date) and latest_ftp.get('watts')!=approved_ftp),'note':'Progress uses dated cycling FTP measurements only. A single ride does not establish FTP improvement. Updating approved targets requires plan preview and approval.'}
        report['recovery_context']=adaptation
        report['current_block']=next((block for block in state['blocks'] if block['starts_on']<=today.isoformat()<=(date.fromisoformat(block['starts_on'])+timedelta(days=6)).isoformat()),None)
        if not old:
            review_context=_context(c,now,brief=state['brief'],timezone_name=tz)
            answers=review_context['answers']
            # Compute the whole week's targets together; a long outlier cannot consume every other day's dose.
            weekly_targets={};long_rides=set();cycling_slots={};week_estimates={};anchor=date.fromisoformat(state['starts_on']);all_program=_program_workouts(c,program['plan_id'])
            windows={anchor+timedelta(weeks=(datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()-anchor).days//7) for row in upcoming}
            for window,sport in [(window,sport) for window in windows for sport in answers.get('sports',[])]:
                rows=[row for row in all_program if row['sport']==sport and window<=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()<window+timedelta(days=7)]
                if sport=='cycling':
                    week_context=_context(c,now,brief={**state['brief'],'_planning_day':window.isoformat()},timezone_name=tz)
                    estimate=week_context['volume_estimates'].get('cycling',{})
                    other_rows=[row for row in all_program if row['sport']!='cycling' and window<=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()<window+timedelta(days=7)]
                    targets,long_id,assigned=_cycling_review_targets(rows,week_context['answers'],estimate,today,tz,other_rows)
                    weekly_targets.update(targets);cycling_slots.update(assigned)
                    if long_id:long_rides.add(long_id)
                    week_estimates.update({row['id']:estimate for row in rows})
                    continue
                generated=[row for row in rows if row['completion_status']=='planned' and datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()>=today and row['publish_status']=='local' and not json.loads(row['definition_json']).get('fixed_commitment')]
                reserved=sum(json.loads(row['definition_json'])['duration_minutes'] for row in rows if row['completion_status']=='completed' or row['completion_status']=='planned' and row not in generated and datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(tz)).date()>=today)
                sport_estimate=review_context['volume_estimates'].get(sport,{})
                guidance={'minutes':sport_estimate.get('long_session_minutes',60),'weekly_cap_minutes':sport_estimate.get('effective_ceiling_minutes',0)}
                budget=max(0,min(answers.get('weekly_minutes',{}).get(sport,0),guidance['weekly_cap_minutes'])-reserved)
                desired={row['id']:min(json.loads(row['definition_json'])['duration_minutes'],guidance['minutes']) for row in generated}
                scale=min(1,budget/sum(desired.values())) if sum(desired.values()) else 1
                remaining=budget
                ordered=sorted(generated,key=lambda item:desired[item['id']],reverse=True)
                for index,row in enumerate(ordered):
                    reserve=20*(len(ordered)-index-1) if budget>=20*len(ordered) else 0
                    target=min(desired[row['id']],max(20,int(desired[row['id']]*scale)) if budget>=20*len(ordered) else int(desired[row['id']]*scale),max(0,remaining-reserve))
                    weekly_targets[row['id']]=target if target>=20 else 0;remaining-=weekly_targets[row['id']]
            for w in upcoming:
                original=json.loads(w['definition_json']);definition=dict(original)
                schedule_metadata={key:definition[key] for key in ('scheduled_date','time_unspecified','schedule_timezone','training_block','schedule_slot_id','schedule_slot_label') if key in definition}
                day=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()
                demanding=definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo') or definition.get('template_id')=='cycling_controlled_intervals' or definition.get('duration_minutes',0)>=90
                action='Kept';why='Consistent with the active block and recent recorded tolerance.'
                protected=definition.get('fixed_commitment') or definition.get('user_adjusted') or w['publish_status']!='local' or w['garmin_workout_id']
                minutes=definition['duration_minutes'];kind=definition.get('workout_kind')
                if program['status']=='active' and pain:
                    definition['review_hold']={'date':today.isoformat(),'reason':'; '.join(reasons)};action='Review required';why='; '.join(reasons)
                elif program['status']=='active' and not protected:
                    if w['sport']=='cycling':
                        slot=next((slot for slot in answers.get('availability',[]) if slot['weekday']==day.weekday()),None)
                        estimate=week_estimates.get(w['id'],review_context['volume_estimates'].get('cycling',{}))
                        guidance={**cycling_dose(slot['minutes'] if slot else minutes,capabilities,feedback,today),'weekly_cap_minutes':estimate.get('effective_ceiling_minutes',0),'weekly_budget_policy':estimate.get('policy_version'),'weekly_reference':estimate.get('weekly_reference'),'weekly_reference_minutes':estimate.get('baseline_minutes')}
                        if minutes>=90 and minutes>guidance['minutes']:
                            minutes=guidance['minutes'];action='Reduced oversized long ride';why=guidance['reason']
                        weekly_target=weekly_targets.get(w['id'],minutes)
                        if weekly_target==0:
                            c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
                            report['changes'].append({'workout_id':w['id'],'title':definition['title'],'action':'Rest within recent volume budget','reason':'No supported minimum training dose remains within the recent completed-volume reference.'});continue
                        if weekly_target!=minutes:
                            minutes=weekly_target;action='Reallocated cycling week';why='The longest available cycling slot receives the remaining sport-specific budget after purposeful weekday rides and reserved sessions.'
                        if w['id'] in long_rides and minutes>60 and kind in ('endurance','long_endurance'):
                            kind='long_endurance';action='Restored long-ride priority'
                        guidance['allocated_minutes']=minutes
                        assigned=cycling_slots.get(w['id'])
                        if assigned:
                            schedule_metadata.update(schedule_slot_id=assigned['slot_id'],schedule_slot_label=assigned.get('label','Cycling'))
                        if definition.get('user_adjusted'):schedule_metadata['user_adjusted']=True
                        if day<=today+timedelta(days=1) and adaptation['level'] in ('easy','recovery'):
                            minutes=min(minutes,30 if adaptation['level']=='recovery' else 60);kind='recovery' if adaptation['level']=='recovery' else 'endurance'
                            action='Adapted intensity and duration';why='; '.join(adaptation['reasons'])
                            guidance['recovery_adjustment']={'level':adaptation['level'],'allocated_minutes':guidance['allocated_minutes'],'effective_minutes':minutes,'reasons':adaptation['reasons']}
                        from .training_prescriptions import endurance,KINDS,advanced_cycling_eligible
                        if kind in ('sprint','anaerobic'):
                            planned_block=next((block for block in state['blocks'] if date.fromisoformat(block['starts_on'])<=day<date.fromisoformat(block['starts_on'])+timedelta(days=7)),{})
                            stage=max(0,(day-date.fromisoformat(state['starts_on'])).days//7)
                            if not advanced_cycling_eligible(c,now,answers.get('experience',{}).get('cycling'),stage,planned_block.get('phase'),adaptation['quality_allowed']):
                                kind='endurance';action='Deferred advanced intensity';why='Sprint/anaerobic work needs a build phase, experienced cycling, tolerated completed quality sessions and current recovery clearance.'
                        if kind in KINDS and (minutes!=original['duration_minutes'] or kind!=original.get('workout_kind') or original.get('duration_guidance')!=guidance or original.get('planning_policy_version')!='cycling-dose-v1' or not original.get('reference_ftp') or any('power_reference_fractions' not in step for step in original.get('steps',[]))):
                            definition=endurance(kind,minutes,state['brief'],'cycling',today=today)
                            definition.update(schedule_metadata);definition['duration_guidance']=guidance;definition['planning_policy_version']='cycling-dose-v1'
                            definition['rationale'].append(why)
                            if action=='Kept':action='Updated explicit power-reference guidance'
                    elif weekly_targets.get(w['id'],minutes)<minutes:
                        target=weekly_targets[w['id']]
                        if target<20:
                            c.execute("UPDATE planned_workouts SET completion_status='cancelled',revision=revision+1 WHERE id=?",(w['id'],));_revision(c,_snapshot(c,w['id']))
                            report['changes'].append({'workout_id':w['id'],'title':definition['title'],'action':'Rest within sport volume budget','reason':'Recent sport-specific evidence does not support this additional dose.'});continue
                        definition=workout_definition(definition['template_id'],target,answers)
                        definition.update(schedule_metadata);minutes=target;action='Reduced to sport volume estimate'
                    elif demanding and day<=today+timedelta(days=1) and adaptation['level']=='recovery':
                        minutes=min(30,minutes)
                        if w['sport']=='strength':definition=workout_definition('strength_foundation',max(20,minutes),answers)
                        else:
                            definition=workout_definition(definition['template_id'],minutes,answers)
                        definition.update(schedule_metadata);action='Changed to easy recovery';why='; '.join(adaptation['reasons'])
                elif program['status']=='active' and protected and demanding and day<=today+timedelta(days=1) and adaptation['level']=='recovery':
                    definition['review_hold']={'date':today.isoformat(),'reason':'; '.join(adaptation['reasons'])};action='Review required';why='; '.join(adaptation['reasons'])
                if definition!=original:
                    c.execute('UPDATE planned_workouts SET title=?,definition_json=?,revision=revision+1 WHERE id=?',(definition['title'],encoded(definition),w['id']));_revision(c,_snapshot(c,w['id']))
                report['changes'].append({'workout_id':w['id'],'title':definition['title'],'action':action,'reason':why})
            from .training_completion import adapt_missed_stimulus
            stimulus_changes,stimulus_warnings=adapt_missed_stimulus(c,_program_workouts(c,program['plan_id']),state,today,now,adaptation,answers) if program['status']=='active' else ([],[])
            report['changes'].extend(stimulus_changes);report['warnings'].extend(stimulus_warnings)
            if readiness['score'] is None:report['warnings'].append('A complete current readiness score is unavailable; no readiness-based increase is made.')
            report['warnings'].append('Review thresholds are provisional app rules. Garmin training effects describe recent stimulus, not aerobic or anaerobic capacity tests.')
            c.execute('INSERT INTO training_program_reviews(plan_id,fingerprint,review_json) VALUES(?,?,?)',(program['plan_id'],fingerprint,encoded(report)))
        c.execute('INSERT INTO training_review_gate(plan_id,local_date,timezone,input_revision,policy_version,reviewed_at) VALUES(?,?,?,?,?,?) ON CONFLICT(plan_id) DO UPDATE SET local_date=excluded.local_date,timezone=excluded.timezone,input_revision=excluded.input_revision,policy_version=excluded.policy_version,reviewed_at=excluded.reviewed_at',(program['plan_id'],local_date,timezone_name,input_revision,REVIEW_POLICY,now.isoformat()))
    return active_view(path,timezone_name,now)


def read_active(arguments,path=None):
    # Assistant context is read-only: startup/UI performs the local review.
    with connect(path) as c:
        p=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not p:return {'tool':'get_active_training_plan','program':None,'workouts':[]}
        root=c.execute('SELECT * FROM training_plans WHERE id=? AND deleted_at IS NULL',(p['plan_id'],)).fetchone()
        if root is None:return {'tool':'get_active_training_plan','program':None,'workouts':[]}
        rows=_program_workouts(c,p['plan_id'])
        last=c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=? ORDER BY id DESC LIMIT 1',(p['plan_id'],)).fetchone()
        from .training_completion import benefit_coverage
        state=json.loads(p['state_json']);coverage=benefit_coverage(c,rows,state['timezone'],datetime.now(timezone.utc).astimezone(ZoneInfo(state['timezone'])).date())
    from .training_prescriptions import cycling_mix
    return {'tool':'get_active_training_plan','benefit_coverage':coverage,'completed_workouts':[{**w,'definition':json.loads(w['definition_json'])} for w in rows if w['completion_status']=='completed'][-30:],'program':{**dict(p),'root_plan_id':p['plan_id'],'name':root['name'],'plan_revision':root['plan_revision'],'state':json.loads(p['state_json']),'cycling_mix':cycling_mix(json.loads(p['state_json'])['brief'])},'workouts':[{**w,'definition':json.loads(w['definition_json'])} for w in rows if w['completion_status']=='planned'],'latest_review':json.loads(last[0]) if last else None}


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
        managed=bool(c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND verified_hash IS NOT NULL',(identifier,)).fetchone())
        if row['completion_status']!='planned' or row['publish_status'] not in ('local','published','update_needed') or (row['publish_status']!='local' or row['garmin_workout_id']) and not managed:raise ValueError('Only local sessions or verified app-managed Garmin sessions can be moved')
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
            if (definition['duration_minutes']>=90 or definition.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo') or definition.get('template_id')=='cycling_controlled_intervals') and abs((start.astimezone(tz).date()-day).days)<=1 and (d['duration_minutes']>=90 or d.get('workout_kind') in ('tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo') or d.get('template_id')=='cycling_controlled_intervals'):raise ValueError('Keep a recovery day between demanding sessions')
        from .training_constraints import assign_slot,day_limit
        constraints=_context(c,now,brief=state['brief'],timezone_name=state['timezone'])['answers']['week_schedule']
        used_ids=[json.loads(other['definition_json']).get('schedule_slot_id') for other in c.execute("SELECT * FROM planned_workouts WHERE id!=? AND completion_status='planned'",(identifier,)) if datetime.fromisoformat(other['scheduled_for']).astimezone(tz).date()==day]
        assigned=assign_slot(constraints,day.weekday(),row['sport'],definition['duration_minutes'],definition.get('schedule_slot_id'),used_ids)
        definition['schedule_slot_id']=assigned['slot_id']
        if day_total>day_limit(constraints,day.weekday()):raise ValueError('The scheduled day exceeds confirmed availability')
        c.execute('UPDATE planned_workouts SET scheduled_for=?,definition_json=?,revision=revision+1 WHERE id=?',(local.isoformat(),encoded(definition),identifier));_revision(c,_snapshot(c,identifier))
        if managed:c.execute("UPDATE planned_workouts SET publish_status='update_needed' WHERE id=?",(identifier,))
        c.execute('UPDATE active_training_program SET revision=revision+1 WHERE id=1')
        from .training_lifecycle import invalidate
        invalidate(c,program['plan_id'])
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
    from .training_adjustments import propose
    return propose(arguments.get('message'),path)


def suggest_today(arguments,path=None,now=None):
    """A time-bounded recommendation; does not replace or save any session."""
    minutes=arguments.get('minutes')
    if type(minutes) is not int or not 10<=minutes<=360:raise ValueError('Available time must be 10–360 whole minutes')
    tz=arguments.get('timezone') or 'UTC';timezone_info(tz);now=now or datetime.now(timezone.utc);today=now.astimezone(ZoneInfo(tz)).date()
    mode=arguments.get('mode','independent')
    if mode not in ('independent','plan'):raise ValueError('Choose independent or plan mode')
    active=read_active({'timezone':tz},path) if mode=='plan' else {'program':None,'workouts':[]}
    program=active['program'];sport=arguments.get('sport')
    if mode=='plan' and (not program or program['status']!='active'):return {'tool':'suggest_today_workout','mode_used':'plan','status':'needs_input','active_plan_id':None,'planned_workout_id':None,'session':None,'questions':['No active program is available. Choose Independent for a recommendation from your completed history and current health.'],'saved':False}
    from .training_coach import DEFAULT,validate_brief
    with connect(path) as personal_connection:
        personal_row=personal_connection.execute('SELECT brief_json FROM training_coach_brief WHERE id=1').fetchone()
    personal_brief=validate_brief(json.loads(personal_row[0])) if personal_row else validate_brief(DEFAULT)
    personal_brief={**personal_brief,'goal':None,'program_start':None,'sport_days':{}}
    if sport is not None and sport not in ('cycling','running','strength','hiking','other'):raise ValueError('Choose cycling, running or strength')
    current=[w for w in active['workouts'] if datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()==today]
    selected=arguments.get('workout_id')
    if mode=='plan' and len(current)>1 and not selected:return {'tool':'suggest_today_workout','mode_used':mode,'status':'needs_input','questions':['Which of today’s planned activities should I adapt?'],'planned_workouts':[{'id':row['id'],'title':row['title'],'sport':row['sport']} for row in current],'session':None,'saved':False}
    planned=next((row for row in current if row['id']==selected),None) if selected else current[0] if current else None
    if selected and mode=='plan' and not planned:raise ValueError('Choose one of today’s planned workouts')
    if planned and sport and planned['sport']!=sport:return {'tool':'suggest_today_workout','mode_used':mode,'status':'needs_input','session':None,'questions':['The selected planned activity is '+planned['sport']+'. Choose that sport or Independent to request a different activity.'],'saved':False}
    with connect(path) as c:context=_context(c,now,timezone_name=tz)
    if not sport:sport=planned['sport'] if planned else (context['answers'].get('sports') or [None])[0]
    from .readiness import readiness_history
    readiness=readiness_history(today,1,tz,path,now=now)['latest']
    capacity=capability(path,today,tz)
    from .training_load_charts import daily_rows
    loads=[r for r in daily_rows(path) if (today-timedelta(days=2)).isoformat()<=r['date']<=today.isoformat()]
    load=loads[-1] if loads else None
    blockers=context['blockers'] if mode=='plan' else [message for message in context['blockers'] if 'restriction' in message.lower() or 'pain or illness' in message.lower()]
    adverse=any(f['pain_or_illness'] or (f['effort'] or 0)>=8 or (f['soreness'] or 0)>=5 or re.search(r'\b(too hard|exhausted|too tired)\b',f['notes'] or '',re.I) for f in context['recent_feedback'])
    base={'tool':'suggest_today_workout','mode_used':mode,'date':today.isoformat(),'available_minutes':minutes,'active_plan_id':program['plan_id'] if program and program['status']=='active' else None,'planned_workout_id':planned['id'] if planned else None,'capability_context':capacity,'readiness':{'score':readiness['score'],'status':readiness['status']},'saved':False}
    def rest(reason,questions=None,alternative=None):
        return {**base,'status':'suggestion','questions':questions or [],'session':{'sport':'rest','title':'Rest day','duration_minutes':0,'effort_target':{'description':'No structured training today. Prioritize sleep, food and hydration.'},'steps':[]},'reason':reason,'alternative':alternative,'training_mix':capacity['training_mix'],'warnings':['Recommendation only; your saved plan is unchanged.']}
    def recovery_ride(duration):
        from .training_prescriptions import endurance
        from .training_coach import read_brief
        brief=program['state']['brief'] if program and program['status']=='active' else personal_brief
        return endurance('recovery',max(10,duration),brief,'cycling',today=today)
    pain=context['answers'].get('pain_or_illness') or any(f['pain_or_illness'] for f in context['recent_feedback'])
    if pain:return rest('Reported pain or illness favors rest; review your training restrictions before resuming.',blockers)
    if blockers:return rest('Rest while the recorded training restrictions are reviewed.',blockers)
    from .training_prescriptions import cycling_dose,recovery_policy
    adaptation=recovery_policy(readiness,load,context['recent_feedback'],capacity,today)
    cycling_days=program['state']['brief'].get('sport_days',{}).get('cycling') if program and program['status']=='active' else None
    cycling_today_allowed=cycling_days is None or today.weekday() in cycling_days
    if sport=='cycling' and not cycling_today_allowed:return rest('The approved sport schedule does not assign cycling today. Keep its strength or rest day; a different sport day needs an explicit plan adjustment.')
    rest_day=bool(program and program['status']=='active' and not planned)
    if rest_day:return rest('The active plan has no workout today. Keep the planned rest day.',alternative=recovery_ride(min(minutes,20)) if sport=='cycling' and cycling_today_allowed and not adverse and adaptation['level']!='hold' else None)

    if not sport:return {**base,'status':'needs_input','questions':['Which activity can you do today: cycling, running or strength?'],'session':None}
    if sport in context['answers'].get('blocked_sports',[]):return {**base,'status':'needs_review','questions':['This sport is excluded in your training preferences. Choose an allowed sport.'],'session':None}
    low=adaptation['level']=='recovery'
    easy=adaptation['level']=='easy'
    rest_day=bool(program and program['status']=='active' and not planned)
    reason='Use today’s saved workout within your available time.' if planned else 'Easy session based on your saved preferences and recent training.'
    if rest_day:reason='No session is scheduled today in the active plan. Keep it a recovery day; optional easy movement is not a replacement for the next planned workout.'
    dose=min(minutes,30) if low or rest_day else min(minutes,60) if easy else minutes
    if not planned: dose=min(dose,30 if context['answers'].get('experience',{}).get(sport)=='new' else 60)
    sport_capacity=next((r for r in capacity.get('sports',[]) if r['sport']==sport),None)
    from .training_volume import estimates
    request_answers={**context.get('raw_answers',context['answers']),'sports':[sport],'week_schedule':[{'weekday':today.weekday(),'mode':'training','total_limit_minutes':minutes,'activities':[{'slot_id':'today-request','sport':sport,'label':'Requested activity','min_minutes':None,'max_minutes':minutes}]}]}
    with connect(path) as dose_connection:volume_context=estimates(dose_connection,request_answers,personal_brief,today,tz)
    if sport in volume_context:dose=min(dose,volume_context[sport]['long_session_minutes'],volume_context[sport]['effective_ceiling_minutes'])
    if sport=='cycling':dose=min(dose,cycling_dose(minutes,capacity,context['recent_feedback'],today)['minutes'])
    elif sport_capacity and sport_capacity['activity_count']>=6 and sport_capacity['longest_minutes']>0:dose=min(dose,max(20,sport_capacity['longest_minutes']))
    if planned:dose=min(dose,planned['definition']['duration_minutes'])
    if dose<10:return {**base,'status':'needs_review','session':None,'questions':['The current history, restrictions or explicit cap leave no supported training dose. Rest or review the optional limit.'],'volume_estimates':volume_context}
    if sport=='strength':
        if not context['answers'].get('equipment') or 'strength' not in context['answers'].get('experience',{}):return {**base,'status':'needs_input','questions':['What strength equipment and experience should I use for this session?'],'session':None}
        definition=workout_definition('strength_foundation',max(20,dose),context['answers']) if dose>=20 else None
        if definition is None:return {**base,'status':'needs_input','questions':['The supported strength session needs at least 20 minutes. Choose an easy cycling/running option or more time.'],'session':None}
    else:
        duration=max(10,dose);warm=min(10,max(3,round(duration*.15)));cool=min(5,max(2,round(duration*.1)));main=duration-warm-cool
        definition={'sport':sport,'title':'Easy '+{'cycling':'ride','running':'run','hiking':'hike','other':'activity'}.get(sport,sport),'duration_minutes':duration,'effort_target':{'description':'Easy conversational effort, about 2–3/10. Ease off or stop if you feel unwell.'},'steps':[{'type':'Warm-up','duration_seconds':warm*60,'effort':'very easy'},{'type':'Steady','duration_seconds':main*60,'effort':'conversational'},{'type':'Cool-down','duration_seconds':cool*60,'effort':'very easy'}]}
        if planned and adaptation['quality_allowed'] and not rest_day and planned['definition'].get('template_id')=='cycling_controlled_intervals' and dose>=26:
            definition={**planned['definition'],'duration_minutes':dose,'steps':[dict(step) for step in planned['definition']['steps']]}
            extra=dose*60-sum(s['duration_seconds'] for s in definition['steps']);definition['steps'][-1]['duration_seconds']+=extra
        elif planned and not low:definition['title']=planned['title']+' · time-limited version'
    if sport in ('hiking','other'):
        from .training_constraints import SPORT_CATALOG
        definition['title']='Easy '+SPORT_CATALOG[sport]['label'].lower();definition['sport']=sport
        definition['effort_target']={'description':'Easy, self-selected effort for the requested activity; no sport-specific calibration or capacity is inferred.'}
    mix=capacity['training_mix']
    if not planned and adaptation['quality_allowed'] and not rest_day and context['answers'].get('experience',{}).get(sport) in ('regular','experienced') and sport in ('cycling','running') and dose>=40:
        gaps=mix['gaps']
        if 'endurance' in gaps:
            reason='No recorded endurance/base benefit in the recent 14-day mix. Use your available time for conversational endurance.'
        elif 'tempo' in gaps:
            definition.update(title='Controlled tempo '+('ride' if sport=='cycling' else 'run'),effort_target={'description':'Controlled tempo, about 5–6/10; never an all-out test.'},steps=[{'type':'Warm-up','duration_seconds':600,'effort':'easy'},{'type':'Tempo','duration_seconds':480,'effort':'controlled 5–6/10'},{'type':'Recovery','duration_seconds':240,'effort':'easy'},{'type':'Tempo','duration_seconds':480,'effort':'controlled 5–6/10'},{'type':'Easy finish','duration_seconds':(dose-30)*60,'effort':'easy'}])
            reason='No recorded tempo/threshold benefit in the recent 14-day mix; recovery permits a controlled tempo session.'
        elif 'short_hard_efforts' in gaps and (readiness['score'] is None or readiness['score']>=70):
            steps=[{'type':'Warm-up','duration_seconds':900,'effort':'easy, gradually build'}]
            for _ in range(4):steps.extend([{'type':'Short acceleration','duration_seconds':15,'effort':'strong and controlled, about 7/10; not maximal'},{'type':'Recovery','duration_seconds':180,'effort':'very easy'}])
            steps.append({'type':'Easy finish','duration_seconds':(dose-28)*60,'effort':'easy'})
            definition.update(title='Short controlled accelerations',effort_target={'description':'Four 15-second controlled accelerations with full easy recoveries. Stop the efforts if technique deteriorates.'},steps=steps)
            reason='Recent endurance and tempo are represented but short-hard-effort benefit is absent; current recovery and saved experience permit a small controlled dose.'
    if planned and mix['gaps']:reason+=' Recent mix gaps: '+', '.join(g.replace('_',' ') for g in mix['gaps'])+'. The saved plan still governs today.'
    if low:
        reason='Current recovery/load or recent feedback favors recovery rather than a training session; leave unused time free.'
        if sport=='cycling':definition=recovery_ride(min(dose,30))
        else:return rest(reason)
    if sport=='cycling':
        from .training_prescriptions import endurance
        from .training_coach import read_brief
        b=program['state']['brief'] if program and program['status']=='active' else personal_brief
        kind='recovery' if low else 'endurance' if easy else planned['definition'].get('workout_kind','endurance') if planned and adaptation['quality_allowed'] else 'tempo' if 'tempo' in definition['title'].lower() else 'short_efforts' if 'acceleration' in definition['title'].lower() else 'endurance'
        if kind in ('sprint','anaerobic'):
            from .training_prescriptions import advanced_cycling_eligible
            stage=max(0,(today-date.fromisoformat(program['state']['starts_on'])).days//7) if program else 0
            block=next((row for row in program['state']['blocks'] if date.fromisoformat(row['starts_on'])<=today<date.fromisoformat(row['starts_on'])+timedelta(days=7)),{}) if program else {}
            with connect(path) as intensity_connection:eligible=advanced_cycling_eligible(intensity_connection,now,context['answers'].get('experience',{}).get('cycling'),stage,block.get('phase'),adaptation['quality_allowed'])
            if not eligible:kind='endurance';reason='Advanced intensity is deferred until the build phase, completed quality-session tolerance and recovery support it.'
        requested_kind=kind
        definition=endurance(kind,definition['duration_minutes'],b,today=today)
        if requested_kind in ('sprint','anaerobic') and definition['workout_kind']!=requested_kind:reason='Available time is too short for the full warm-up and recoveries; use easy endurance instead.'
    if planned and planned['definition'].get('review_hold'):return {**base,'status':'needs_review','questions':[planned['definition']['review_hold']['reason']],'session':None}
    return {**base,'volume_estimates':volume_context,'recovery_context':adaptation,'status':'suggestion','session':definition,'reason':reason,'training_mix':mix,'questions':[],'warnings':['Recommendation only; your saved plan is unchanged.']+(['Readiness is unavailable; the suggestion uses recorded workload, recent training consistency and feedback rather than treating missing readiness as zero.'] if readiness['score'] is None else [])}


def recent_mix(arguments,path=None):
    days=arguments.get('days',14)
    if type(days) is not int or not 7<=days<=42:raise ValueError('Choose a recent window of 7–42 days')
    tz=arguments.get('timezone') or 'UTC';timezone_info(tz)
    today=datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
    return {'tool':'get_recent_training_mix',**capability(path,today,tz,days)}


def active_view(path=None,timezone_name='UTC',now=None):
    timezone_info(timezone_name);now=now or datetime.now(timezone.utc);today=now.astimezone(ZoneInfo(timezone_name)).date()
    with connect(path) as c:
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not program:return {'program':None,'workouts':[],'review':None,'review_due':False}
        root=c.execute('SELECT * FROM training_plans WHERE id=? AND deleted_at IS NULL',(program['plan_id'],)).fetchone()
        if not root:return {'program':None,'workouts':[],'review':None,'review_due':False}
        state=json.loads(program['state_json']);gate=c.execute('SELECT * FROM training_review_gate WHERE plan_id=?',(root['id'],)).fetchone()
        last=c.execute('SELECT review_json FROM training_program_reviews WHERE plan_id=? ORDER BY id DESC LIMIT 1',(root['id'],)).fetchone()
    history=list_training(path);ids={row['id'] for row in history['plans'] if row['id']==root['id'] or row['context'].get('program_id')==root['id']}
    upcoming=[row for row in history['workouts'] if row['training_plan_id'] in ids and row['completion_status']=='planned' and today<=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(timezone_name)).date()<=today+timedelta(days=6)]
    completed=[row for row in history['workouts'] if row['training_plan_id'] in ids and row['completion_status']=='completed' and (today-timedelta(days=6))<=datetime.fromisoformat(row['scheduled_for']).astimezone(ZoneInfo(timezone_name)).date()<=today]
    from .training_completion import benefit_coverage
    with connect(path) as c:coverage=benefit_coverage(c,_program_workouts(c,root['id']),timezone_name,today,now)
    key=str(root['plan_revision'])+':'+str(program['revision']);due=program['status']=='active' and not(gate and gate['local_date']==today.isoformat() and gate['timezone']==timezone_name and gate['input_revision']==key and gate['policy_version']==REVIEW_POLICY)
    metadata={'review_due':due,'last_reviewed_date':gate['local_date'] if gate else None,'reviewed_at':gate['reviewed_at'] if gate else None}
    from .training_prescriptions import cycling_mix
    return {'program':{'cycling_mix':cycling_mix(state['brief']),'id':root['id'],'root_plan_id':root['id'],'plan_id':root['id'],'name':root['name'],'plan_revision':root['plan_revision'],'revision':program['revision'],'status':program['status'],**state},'completed_workouts':completed,'benefit_coverage':coverage,'workouts':upcoming,'review':json.loads(last[0]) if last else None,'review_due':due,'review_metadata':metadata,**metadata}


def save_event(arguments,path=None,now=None):
    now=now or datetime.now(timezone.utc);tz=arguments.get('timezone') or 'UTC';today=now.astimezone(timezone_info(tz)).date()
    root_id=arguments.get('root_plan_id');operation=arguments.get('operation');expected=arguments.get('expected_revision')
    from .training_lifecycle import guard,invalidate
    from .training_coach import validate_brief
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE');guard(c,root_id)
        program=c.execute('SELECT * FROM active_training_program WHERE id=1').fetchone()
        if not program or program['plan_id']!=root_id or program['status']!='active':raise ValueError('Select the current active root program')
        state=json.loads(program['state_json']);brief=state['brief'];events=brief.get('fixed_events',[])
        if operation=='upsert':
            incoming=arguments.get('event')
            if not isinstance(incoming,dict):raise ValueError('Review an event before saving it')
            normalized=validate_brief({**brief,'fixed_events':[incoming]})['fixed_events'][0]
            if normalized['date']<today.isoformat():raise ValueError('Choose today or an upcoming event date')
            if not normalized.get('duration_minutes'):raise ValueError('Provide or review an estimated event duration')
            old=next((event for event in events if event['id']==normalized['id']),None)
            if old==normalized:return active_view(path,tz,now)
            updated=[event for event in events if event['id']!=normalized['id']]+[normalized]
        elif operation=='remove':
            identifier=arguments.get('event_id');updated=[event for event in events if event['id']!=identifier]
            if updated==events:return active_view(path,tz,now)
        else:raise ValueError('Choose event upsert or remove')
        if type(expected) is not int or program['revision']!=expected:raise ValueError('Active program changed; review a fresh event proposal')
        affected=normalized['id'] if operation=='upsert' else arguments.get('event_id')
        for row in _program_workouts(c,root_id):
            definition=json.loads(row['definition_json'])
            if definition.get('event_id')==affected and (row['completion_status']!='planned' or row['publish_status']!='local'):raise ValueError('Completed or published event sessions cannot be changed locally')
        state['brief']=validate_brief({**brief,'fixed_events':updated});state['commitment_revision']=state.get('commitment_revision',0)+1
        c.execute('UPDATE active_training_program SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=1',(encoded(state),));invalidate(c,root_id)
        changes,warnings=_reconcile_events(c,root_id,state,today,now);warnings.extend(_fill(c,root_id,state,today,now))
        state['last_event_change']={'date':today.isoformat(),'changes':changes,'warnings':warnings,'scope':'active_program_only'}
        c.execute('UPDATE active_training_program SET state_json=? WHERE id=1',(encoded(state),))
    result=active_view(path,tz,now);result['event_changes']={'changes':changes,'warnings':warnings,'scope':'active_program_only'}
    return result


def propose_event(arguments,path=None):
    from .training_coach import parse_request,validate_brief
    now=datetime.now(timezone.utc);tz=arguments.get('timezone') or 'UTC';today=now.astimezone(timezone_info(tz)).date();active=read_active({},path)
    if not active['program'] or active['program']['status']!='active':raise ValueError('An active plan is required for an event change')
    program=active['program'];message=arguments.get('message') or '';operation=arguments.get('operation') or ('remove' if re.search(r'\b(remove|delete|cancel)\b',message,re.I) else 'upsert')
    if operation=='remove':
        event_id=arguments.get('event_id');event=None
        if not event_id:
            matches=[e for e in program['state']['brief'].get('fixed_events',[]) if e.get('title','').lower() in message.lower() or e.get('date','!') in message]
            if len(matches)!=1:return {'tool':'propose_training_event','status':'needs_input','questions':['Which saved event should I remove? Please provide its title or date.']}
            event_id=matches[0]['id']
    else:
        supplied=arguments.get('event')
        if supplied:event=validate_brief({**program['state']['brief'],'fixed_events':[supplied]})['fixed_events'][0]
        else:
            if re.search(r'\bin a few days\b',message,re.I):return {'tool':'propose_training_event','status':'needs_input','questions':['Which date is the event? “In a few days” does not identify one date.']}
            brief,_=parse_request(message,{**program['state']['brief'],'fixed_events':[]},today,today)
            if not brief['fixed_events']:return {'tool':'propose_training_event','status':'needs_input','questions':['What date and expected duration should I use for the event?']}
            event=brief['fixed_events'][0]
        event_id=event['id']
        if not event.get('duration_minutes'):return {'tool':'propose_training_event','status':'needs_input','questions':['How long is the event expected to last? Distance and climbing will be retained.']}
    proposal={'root_plan_id':program['plan_id'],'expected_revision':program['revision'],'timezone':tz,'operation':operation,'event':event,'event_id':event_id,'message':'Review this event change. Saving adapts nearby flexible sessions and preserves the active long-term goal.'}
    return {'tool':'propose_training_event','status':'proposal','training_event':proposal}
