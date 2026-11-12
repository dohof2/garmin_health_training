"""Weekly cycling balance using actual rides, available slots and recovery context."""
import json
from datetime import datetime, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo

POLICY='cycling-week-v3-deload-endurance'
QUALITY={'tempo','threshold','vo2','short_efforts','sprint','anaerobic','long_tempo'}
EASY_PHASES={'Recovery / review','Freshen up','Post-event recovery','Race week','Outside plan'}
LABELS={'TEMPO':'tempo','THRESHOLD':'threshold','LACTATE_THRESHOLD':'threshold',
        'VO2MAX':'vo2','VO2_MAX':'vo2','SPEED':'sprint','SPRINT':'sprint',
        'ANAEROBIC':'anaerobic','ANAEROBIC_CAPACITY':'anaerobic','AEROBIC_BASE':'endurance'}


def observations(c,today,now,tz):
    from .ride_comparison import training_benefit
    result=[]
    for row in c.execute("SELECT id,started_at,duration_seconds,activity_type FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND started_at>=?",((today-timedelta(days=8)).isoformat(),)):
        if not any(word in row['activity_type'].lower() for word in ('cycl','bik')):continue
        start=datetime.fromisoformat(row['started_at'].replace('Z','+00:00'))
        if start.tzinfo is None or start+timedelta(seconds=row['duration_seconds'] or 0)>now:continue
        day=start.astimezone(ZoneInfo(tz)).date()
        if not today-timedelta(days=7)<=day<=today:continue
        kind=LABELS.get(training_benefit(c,row['id'])['source_label'])
        metrics={r['metric_type']:r['value'] for r in c.execute('SELECT metric_type,value FROM activity_metrics WHERE activity_id=?',(row['id'],))}
        hard=kind in QUALITY or (metrics.get('intensity_factor') or 0)>=.9 or (metrics.get('aerobic_training_effect') or 0)>=4 or (metrics.get('anaerobic_training_effect') or 0)>=2.5
        result.append({'id':row['id'],'day':day,'kind':kind,'hard':hard,'minutes':(row['duration_seconds'] or 0)/60})
    return result


def assignments(c,entries,week,today,now,tz,brief,block,recovery,focus,priority_strength=False):
    """Entries carry id/day/definition/mutable/status. Return targets, never add volume.

    Two intervals are a normal-week aim, not a debt to make up. Unknown actual
    benefit is not invented. Completed prescriptions without a recording still
    reserve their intended hard slot conservatively.
    """
    from .training_prescriptions import cycling_mix
    actual=observations(c,today,now,tz)
    end=week+timedelta(days=7)
    entries=[e for e in entries if e.get('status','planned')=='completed' or e.get('status','planned')=='planned' and e['day']>=today]
    rows=[e for e in entries if e['sport']=='cycling' and week<=e['day']<end]
    editable=[e for e in rows if e['mutable'] and e.get('status','planned')=='planned' and e['day']>=today]
    locked=[e for e in rows if e not in editable]
    hard_days={r['day'] for r in actual if r['hard']}
    demanding_days={r['day'] for r in actual if r['hard'] or r['minutes']>=120}
    for entry in entries:
        d=entry['definition']
        if entry.get('status','planned')!='planned' or not d.get('fixed_commitment'):continue
        if d.get('is_race') or d['duration_minutes']>=90 or (d.get('distance_km') or 0)>=60 or (d.get('elevation_gain_meters') or 0)>=1000 or 'hard' in d.get('effort_target',{}).get('description',''):
            demanding_days.add(entry['day'])
    reserved_hard_days=set()
    # Earlier reviewed weeks remain part of spacing and rolling load. A
    # calendar boundary must not permit Sunday/Monday interval stacking.
    for entry in entries:
        if entry['sport']!='cycling' or not today<=entry['day']<week or entry.get('status','planned')!='planned':continue
        d=entry['definition']
        if d.get('workout_kind') in QUALITY:
            hard_days.add(entry['day']);reserved_hard_days.add(entry['day']);demanding_days.add(entry['day'])
        elif d['duration_minutes']>=120:demanding_days.add(entry['day'])
    completed_ids={r['id'] for r in actual}
    actual_week=[r for r in actual if week<=r['day']<end]
    hard_count=sum(r['hard'] for r in actual_week)
    base_count=sum(r['kind']=='endurance' and r['minutes']<120 for r in actual_week)
    long_done=any(r['minutes']>=120 for r in actual_week)
    for entry in locked:
        linked=c.execute('SELECT activity_id FROM training_feedback WHERE workout_id=?',(entry['id'],)).fetchone()
        if entry.get('status')=='completed' and linked and linked['activity_id'] in completed_ids:continue
        d=entry['definition'];kind=d.get('workout_kind')
        hard=kind in QUALITY or d.get('fixed_commitment') and 'hard' in d.get('effort_target',{}).get('description','')
        if hard:
            hard_count+=1;hard_days.add(entry['day'])
            reserved_hard_days.add(entry['day'])
        if hard or d['duration_minutes']>=120:demanding_days.add(entry['day'])
        if kind in ('long_endurance','climbing_endurance','long_tempo') or d['duration_minutes']>=120:long_done=True
        elif kind=='endurance':base_count+=1
    long_candidates=[e for e in editable if e['definition']['duration_minutes']>=90 or e['definition'].get('workout_kind') in ('long_endurance','climbing_endurance')]
    # A long ride is desirable, not a mandatory fourth obligation. With only
    # three usable rides, prefer two intervals and base instead of forcing it.
    weekly_opportunities=len(editable)+len(actual_week)+sum(e.get('status','planned')=='planned' for e in locked)
    long_entry=max(long_candidates,key=lambda e:e['definition']['duration_minutes'],default=None) if not long_done and (weekly_opportunities>=4 or week<today) else None
    targets={e['id']:'endurance' for e in editable}
    if long_entry:targets[long_entry['id']]='long_endurance'
    if long_entry:demanding_days.add(long_entry['day'])
    normal=block.get('phase') not in EASY_PHASES and not priority_strength
    limit=2 if normal else 0
    # Actual hard work in the rolling seven days also constrains this week's
    # additions; previous-week hard rides are not reset away on Monday.
    candidates=[e for e in editable if e is not long_entry and e['definition']['duration_minutes']>=45
                and all(abs((e['day']-day).days)>=2 for day in demanding_days)
                and (e['day']>today+timedelta(days=1) or recovery['quality_allowed'])]
    remaining=max(0,limit-hard_count)
    if recovery.get('adverse_feedback') or recovery.get('level')=='hold':remaining=0
    # Reserve one short base ride when there is room; limited availability or
    # recovery means fewer intervals, never shortening the long ride to fit.
    remaining=min(remaining,max(0,len(editable)-(1 if long_entry else 0)-(0 if base_count else 1)))
    selected=()
    for count in range(min(2,remaining,len(candidates)),0,-1):
        choices=[group for group in combinations(sorted(candidates,key=lambda e:e['day']),count)
                 if all(abs((a['day']-b['day']).days)>=2 for a,b in combinations(group,2))
                 and all(sum(r['hard'] for r in actual if e['day']-timedelta(days=6)<=r['day']<=e['day'])
                         +sum(e['day']-timedelta(days=6)<=day<=e['day'] for day in reserved_hard_days)
                         +sum(e['day']-timedelta(days=6)<=other['day']<=e['day'] for other in group)<=2 for e in group)]
        if choices:selected=choices[0];break
    rotation=cycling_mix(brief)['quality_rotation']
    week_index=max(0,(week-datetime.fromisoformat(brief.get('program_start') or week.isoformat()).date()).days//7)
    offset=(week_index-week_index//4)%len(rotation)
    ordered=rotation[offset:]+rotation[:offset]
    counts={kind:sum(r['kind']==kind for r in actual) for kind in set(rotation)}
    used=set();used_families=set()
    for entry in selected:
        def rank(kind):
            category='anaerobic' if kind in ('sprint','anaerobic','short_efforts') else 'high_aerobic'
            position=focus.get('categories',{}).get(category,{}).get('position') if focus.get('status')=='current' else None
            preferred='anaerobic' if cycling_mix(brief)['focus']=='short_power' else 'high_aerobic'
            family_penalty=category in used_families if used_families else category!=preferred
            return (family_penalty if len(selected)==2 else False,kind in used,position=='above',counts[kind],position!='below',ordered.index(kind))
        kind=min(set(rotation),key=rank);targets[entry['id']]=kind;used.add(kind)
        used_families.add('anaerobic' if kind in ('sprint','anaerobic','short_efforts') else 'high_aerobic')
    if not normal:
        targets={key:'endurance' for key in targets}
    # A deload block is base riding, not an acute recovery prescription.
    for entry in editable:
        if entry['day']<=today+timedelta(days=1) and recovery['level'] in ('easy','recovery','hold'):
            targets[entry['id']]='recovery' if recovery['level'] in ('recovery','hold') else 'endurance'
    evidence={'policy':POLICY,'aim':{'intervals':limit,'long':1 if normal else 0,'long_optional':True,'base':1},'phase':block.get('phase'),
              'recorded_hard_this_week':hard_count,'selected_intervals':len(selected),
              'recent_activity_ids':[r['id'] for r in actual],'load_focus_status':focus.get('status'),
              'reason':('Reduced block: preserve base ride duration and omit VO₂, threshold and sprint intervals. Acute recovery rides depend on current recovery needs.' if block.get('phase') in EASY_PHASES else 'Aim for two separated intervals and one base ride, plus a desirable optional long ride when it fits; actual riding, recovery, block and available time can reduce the target.')}
    return targets,evidence


def apply_definition(c,definition,kind,brief,today,tz,focus,evidence):
    from .training_prescriptions import endurance
    from .cycling_variants import select
    from .training_load_focus import adjust_workout
    variant,selection=select(c,kind,today,tz,kind in QUALITY)
    result=endurance(kind,definition['duration_minutes'],brief,today=today,variant=variant)
    result=adjust_workout(result,focus)
    for key in ('scheduled_date','time_unspecified','schedule_timezone','training_block','schedule_slot_id','schedule_slot_label','duration_guidance','planning_policy_version','daily_base_definition'):
        if key in definition:result[key]=definition[key]
    result.update(variant_selection=selection,weekly_mix=evidence)
    result['rationale'].append(evidence['reason'])
    return result


def reconcile(c,rows,state,today,now,recovery,focus,answers):
    """Revise managed future prescriptions in place; retain publication identities."""
    from .training import encoded,_revision,_snapshot
    from .training_coach import roadmap
    tz=state['timezone'];brief=state['brief'];anchor=datetime.fromisoformat(state['starts_on']).date()
    blocks=roadmap(brief,anchor,answers)
    entries=[]
    for row in rows:
        d=json.loads(row['definition_json']);start=datetime.fromisoformat(row['scheduled_for'])
        day=start.astimezone(ZoneInfo(tz)).date()
        link=c.execute('SELECT verified_hash FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=?',(row['id'],row['garmin_workout_id'])).fetchone()
        managed=row['publish_status']=='local' and not row['garmin_workout_id'] or row['publish_status'] in ('published','update_needed') and link and link['verified_hash']
        mutable=bool(managed and row['completion_status']=='planned' and (day>=today if d.get('time_unspecified') else start>=now)
                     and not d.get('fixed_commitment') and not d.get('user_adjusted') and not d.get('review_hold'))
        entries.append({'id':row['id'],'sport':row['sport'],'day':day,'definition':d,'mutable':mutable,'status':row['completion_status']})
    changes=[]
    for week in sorted({anchor+timedelta(weeks=(e['day']-anchor).days//7) for e in entries if e['mutable']}):
        block=next((b for b in blocks if b['starts_on']==week.isoformat()),{'phase':'Outside plan'})
        targets,evidence=assignments(c,entries,week,today,now,tz,brief,block,recovery,focus,brief.get('strength_role')=='primary' or answers.get('priority')=='strength')
        for entry in entries:
            kind=targets.get(entry['id']);original=entry['definition']
            if kind is None:continue
            definition=apply_definition(c,original,kind,brief,today,tz,focus,evidence)
            if definition==original:continue
            c.execute("UPDATE planned_workouts SET title=?,definition_json=?,publish_status=CASE WHEN garmin_workout_id IS NOT NULL THEN 'update_needed' ELSE publish_status END,revision=revision+1 WHERE id=?",(definition['title'],encoded(definition),entry['id']))
            _revision(c,_snapshot(c,entry['id']))
            entry['definition']=definition
            changes.append({'workout_id':entry['id'],'title':definition['title'],'action':'Balanced cycling week','reason':evidence['reason']})
    return changes
