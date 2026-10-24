"""Conservative one-to-one completion matching using recorded local-day evidence."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from .training import _snapshot, _revision


def sport(value):
    value=value.lower()
    return 'cycling' if any(k in value for k in ('cycl','bik','virtual_ride')) else 'running' if 'run' in value else 'strength' if 'strength' in value else value


def reconcile(c,workouts,tz,now):
    zone=ZoneInfo(tz);linked={r[0] for r in c.execute('SELECT activity_id FROM training_feedback WHERE activity_id IS NOT NULL')}
    recordings=[dict(r) for r in c.execute("SELECT * FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture'") if r['id'] not in linked]
    candidates={};by_workout={w['id']:w for w in workouts}
    for w in workouts:
        if w['completion_status']!='planned':continue
        d=json.loads(w['definition_json']);start=datetime.fromisoformat(w['scheduled_for']);day=d.get('scheduled_date') or start.astimezone(zone).date().isoformat()
        if day>now.astimezone(zone).date().isoformat():continue
        possible=[]
        for a in recordings:
            began=datetime.fromisoformat(a['started_at'].replace('Z','+00:00'))
            if began>=now or began.astimezone(zone).date().isoformat()!=day or sport(a['activity_type'])!=w['sport']:continue
            # Do not mark a recording still in progress as complete.
            if a['duration_seconds'] is None or began.timestamp()+a['duration_seconds']>now.timestamp():continue
            if not d.get('time_unspecified') and abs((began-start).total_seconds())>3600:continue
            possible.append(a['id'])
        candidates[w['id']]=possible
    changes=[];warnings=[]
    for identifier,possible in candidates.items():
        w=by_workout[identifier]
        if len(possible)!=1 or sum(possible[0] in choices for choices in candidates.values())!=1:
            if possible:warnings.append('Several recordings/session matches are possible for '+w['title']+'; link its activity in Feedback / edit session.')
            continue
        activity_id=possible[0]
        c.execute("UPDATE planned_workouts SET completion_status='completed',revision=revision+1 WHERE id=?",(identifier,))
        c.execute('INSERT INTO training_feedback(workout_id,pain_or_illness,activity_id,updated_at) VALUES(?,0,?,?) ON CONFLICT(workout_id) DO UPDATE SET activity_id=excluded.activity_id,updated_at=excluded.updated_at',(identifier,activity_id,now.isoformat()))
        _revision(c,_snapshot(c,identifier))
        changes.append({'workout_id':identifier,'title':w['title'],'action':'Matched completed activity','reason':'A unique one-to-one recording matches the local day, sport and any specified clock time. Completion does not prove the intended stimulus was achieved.'})
    return changes,warnings


def benefit_coverage(c,workouts,tz,today,now=None):
    from .ride_comparison import training_benefit
    intended={'endurance':'base','long_endurance':'base','recovery':'recovery','tempo':'tempo','long_tempo':'tempo','climbing_endurance':'base','threshold':'threshold','sprint':'sprint','anaerobic':'anaerobic','vo2':'vo2'}
    labels={'AEROBIC_BASE':'base','RECOVERY':'recovery','TEMPO':'tempo','LACTATE_THRESHOLD':'threshold','THRESHOLD':'threshold','SPRINT':'sprint','SPEED':'sprint','ANAEROBIC':'anaerobic','ANAEROBIC_CAPACITY':'anaerobic','VO2MAX':'vo2','VO2_MAX':'vo2'}
    from datetime import timedelta,timezone
    now=now or datetime.now(timezone.utc)
    last={};next_dates={};completed=[];missed=[]
    for w in sorted(workouts,key=lambda w:w['scheduled_for']):
        d=json.loads(w['definition_json']);category=intended.get(d.get('workout_kind'));day=d.get('scheduled_date') or datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date().isoformat()
        if w['sport']!='cycling' or not category:continue
        if w['completion_status']=='planned' and day>=today.isoformat():next_dates.setdefault(category,day)
        if w['completion_status']=='skipped' and day<=today.isoformat():
            missed.append({'workout_id':w['id'],'date':day,'intended':category,'achieved':None,'reason':'Session explicitly skipped'})
        if w['completion_status']!='completed' or not (today-timedelta(days=42)).isoformat()<=day<=today.isoformat():continue
        feedback=c.execute('SELECT activity_id FROM training_feedback WHERE workout_id=?',(w['id'],)).fetchone()
        activity_id=feedback['activity_id'] if feedback else None
        benefit=training_benefit(c,activity_id) if activity_id else None
        actual=labels.get(benefit['source_label']) if benefit else None
        completed.append({'workout_id':w['id'],'activity_id':activity_id,'date':day,'intended':category,'achieved':actual,'matches_intent':actual==category if actual else None,'recorded_benefit':benefit['label'] if benefit else None})
    # Include unplanned rides: they can satisfy an outstanding stimulus too.
    for row in c.execute("SELECT id,started_at,activity_type,duration_seconds FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' ORDER BY started_at"):
        if sport(row['activity_type'])!='cycling':continue
        start=datetime.fromisoformat(row['started_at'].replace('Z','+00:00'))
        if row['duration_seconds'] is None or start+timedelta(seconds=row['duration_seconds'])>now:continue
        day=start.astimezone(ZoneInfo(tz)).date()
        if not today-timedelta(days=42)<=day<=today:continue
        actual=labels.get(training_benefit(c,row['id'])['source_label'])
        if actual:last[actual]=max(last.get(actual,''),day.isoformat())
    missed.extend({**r,'reason':'Recorded benefit differed from intended stimulus'} for r in completed if r['matches_intent'] is False)
    pending={}
    for record in sorted(missed,key=lambda r:r['date']):
        category=record['intended']
        if category not in ('threshold','sprint','anaerobic','tempo','vo2') or record['date']<(today-timedelta(days=42)).isoformat() or last.get(category,'')>=record['date']:continue
        pending.setdefault(category,{**record,'next_planned':next_dates.get(category),'status':'scheduled' if next_dates.get(category) else 'awaiting_suitable_slot'})
    return {'completed':completed,'pending_stimuli':list(pending.values()),'categories':{key:{'last_achieved':last.get(key),'next_planned':next_dates.get(key)} for key in ('base','threshold','tempo','vo2','anaerobic','sprint')},'note':'Recorded benefit labels are evidence of stimulus, not proof of adaptation. Missing labels stay unknown. Outstanding categories are reconsidered for 42 days across week boundaries; no extra hard session is added automatically.'}


def adapt_missed_stimulus(c,workouts,state,today,now,policy,answers):
    """Reassign an existing quality slot, without adding load or catch-up sessions."""
    from datetime import timedelta
    from .training_prescriptions import endurance,advanced_cycling_eligible
    tz=state['timezone'];coverage=benefit_coverage(c,workouts,tz,today,now)
    quality={'threshold','sprint','anaerobic','tempo','vo2'}
    horizon=today+timedelta(days=6)
    missed=coverage['pending_stimuli']
    changes=[];deferred=[]
    for record in missed:
        category=record['intended']
        peers=[]
        for w in workouts:
            d=json.loads(w['definition_json']);day=datetime.fromisoformat(w['scheduled_for']).astimezone(ZoneInfo(tz)).date()
            if w['sport']=='cycling' and w['completion_status']=='planned' and today<=day<=horizon:peers.append((w,d,day))
        if record['next_planned']:continue
        replacement=None
        if policy['quality_allowed'] and policy['level']=='normal':
            for w,d,day in peers:
                phase=d.get('training_block',{}).get('phase');stage=max(0,(day-datetime.fromisoformat(state['starts_on']).date()).days//7)
                blocks=state.get('blocks',[])
                if stage<len(blocks):phase=blocks[stage]['phase']
                if phase in ('Recovery / review','Race week','Freshen up','Post-event recovery'):continue
                if w['publish_status']!='local' or w['garmin_workout_id'] or d.get('fixed_commitment') or d.get('user_adjusted') or d.get('review_hold') or d.get('workout_kind') not in quality or d['duration_minutes']<45:continue
                if category in ('sprint','anaerobic') and not advanced_cycling_eligible(c,now,answers.get('experience',{}).get('cycling'),stage,phase,True):continue
                # The completed work still counts: never put the replacement next
                # to a completed or planned quality session, even after a mismatch.
                nearby=False
                for peer in workouts:
                    if peer['id']==w['id'] or peer['completion_status'] not in ('planned','completed'):continue
                    pd=json.loads(peer['definition_json']);pday=datetime.fromisoformat(peer['scheduled_for']).astimezone(ZoneInfo(tz)).date()
                    if pd.get('workout_kind') in quality and abs((pday-day).days)<2:nearby=True
                if nearby:continue
                from .cycling_variants import select
                variant,evidence=select(c,category,today,tz,True)
                new=endurance(category,d['duration_minutes'],state['brief'],today=today,variant=variant)
                # Bound the new dose by the replaced session's existing work time.
                from .workout_edits import work_seconds
                if work_seconds(new)>work_seconds(d):new=endurance(category,d['duration_minutes'],state['brief'],today=today)
                if work_seconds(new)>work_seconds(d):continue
                new={**d,**{k:new[k] for k in ('steps','title','workout_kind','template_id','effort_target','variant_id','variant_label','sources')},'variant_selection':evidence,'stimulus_replacement_for':record['workout_id']}
                c.execute('UPDATE planned_workouts SET definition_json=?,title=?,revision=revision+1 WHERE id=?',(json.dumps(new),new['title'],w['id']));_revision(c,_snapshot(c,w['id']))
                changes.append({'workout_id':w['id'],'title':new['title'],'action':'Reconsidered missed stimulus','reason':f"{record['date']} intended {category}: {record['reason']}. Replaced an existing quality slot in the next seven days, preserving duration, recovery spacing and the work-time ceiling."})
                replacement=w['id'];break
        if replacement:break # At most one quality reassignment per review.
        deferred.append(f"{record['date']}: intended {category}. No suitable existing quality slot in the next seven days under recovery, dose, commitments and publication constraints; retain this stimulus for the next review.")
    return changes,deferred
