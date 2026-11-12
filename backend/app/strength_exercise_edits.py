"""Atomic dated additions; existing exercises, history and recurring notes stay intact."""
import copy
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo

from .database import connect
from .training import _context,encoded

PREFIX='@strength_exercise:'


def requested(message):
    return bool(re.search(r'\b(?:add|include)\b',message,re.I) and re.search(r'\bcalf\s+raises?\b',message,re.I))


def from_message(message):
    sets=re.search(r'\b(\d+)\s+sets?\b',message,re.I)
    reps=re.search(r'\b(\d+)\s+(?:reps?|repetitions?)\b',message,re.I)
    if not sets:raise ValueError('How many sets of calf raises should I add?')
    return {'id':'calf_raise','sets':int(sets[1]),**({'repetitions':int(reps[1])} if reps else {})}


def preview(arguments,path=None,now=None):
    from .active_training import _program_workouts,capability
    from .training_accounting import session_day,counts_toward_plan,completed_minutes
    from .training_constraints import assign_slot,day_limit,optional_cap
    from .training_prescriptions import recovery_policy
    from .garmin_strength_catalog import planner_exercises
    from .garmin_strength import payload
    from .readiness import readiness_history
    from .training_load_charts import daily_rows
    now=now or datetime.now(timezone.utc)
    if set(arguments)-{'workouts','exercise'}:raise ValueError('Unsupported exercise-addition fields')
    targets=arguments.get('workouts');exercise=arguments.get('exercise')
    if not isinstance(targets,list) or not 1<=len(targets)<=7:raise ValueError('Choose 1–7 dated strength sessions')
    if not isinstance(exercise,dict) or set(exercise)-{'id','sets','repetitions','rest_seconds'}:raise ValueError('Choose a catalog exercise and its sets')
    if type(exercise.get('sets')) is not int or not 1<=exercise['sets']<=5:raise ValueError('Choose 1–5 sets for the added exercise')
    for key,low,high in (('repetitions',1,100),('rest_seconds',0,600)):
        if key in exercise and (type(exercise[key]) is not int or not low<=exercise[key]<=high):raise ValueError('Use 1–100 repetitions and 0–600 seconds of rest')
    spec=next((e for e in planner_exercises(include_additions=True) if e['id']==exercise.get('id')),None)
    if not spec:raise ValueError('Choose an exercise with reviewed equipment and Garmin mapping')
    identifiers=[]
    for target in targets:
        if not isinstance(target,dict) or set(target)!={'workout_id','expected_revision'} or not isinstance(target['workout_id'],str) or type(target['expected_revision']) is not int:raise ValueError('Read each selected workout and supply its current revision')
        identifiers.append(target['workout_id'])
    if len(set(identifiers))!=len(identifiers):raise ValueError('Choose distinct workouts')
    base={'tool':'propose_training_adjustment','kind':'adaptation','status':'needs_input','request':PREFIX+encoded(arguments),'changes':{},'adjustments':[]}
    def reject(message,status='not_recommended'):return {**base,'status':status,'message':message}
    with connect(path) as c:
        program=c.execute("SELECT * FROM active_training_program WHERE id=1 AND status='active'").fetchone()
        if not program:return reject('Activate a plan before editing its strength workouts.','needs_input')
        state=json.loads(program['state_json']);tz=state['timezone'];today=now.astimezone(ZoneInfo(tz)).date()
        context=_context(c,now,timezone_name=tz);sessions=_program_workouts(c,program['plan_id'])
        rows={w['id']:w for w in sessions}
        selected=[]
        for target in targets:
            row=rows.get(target['workout_id'])
            if not row or row['revision']!=target['expected_revision']:raise ValueError('A selected workout changed. Read the selected dates again before preparing this edit.')
            old=json.loads(row['definition_json']);day=session_day(row,tz)
            if row['sport']!='strength' or row['completion_status']!='planned' or day<today:raise ValueError('Choose upcoming planned strength sessions; historical workouts are preserved')
            if any(old.get(k) for k in ('fixed_commitment','event_id','review_hold')):return reject('Resolve the selected session’s commitment or review hold before adding an exercise.')
            if row['publish_status'] not in ('local','published','update_needed') or (row['publish_status']!='local' or row['garmin_workout_id']) and not c.execute('SELECT 1 FROM garmin_publication_links WHERE workout_id=? AND remote_workout_id=? AND verified_hash IS NOT NULL',(row['id'],row['garmin_workout_id'])).fetchone():return reject('Reconcile the unfinished or unverified Garmin send before adding exercises.')
            if any(e['id']==spec['id'] for e in old.get('exercises',[])):return reject(f'{day}: this exercise is already present. Edit its existing sets instead of adding a duplicate.','needs_input')
            selected.append((row,old,day))
        if context['blockers'] or context['answers'].get('pain_or_illness'):return reject('Saved restrictions need review before adding strength work: '+'; '.join(context['blockers']))
        if spec['equipment'] not in context['answers'].get('equipment',[]) or spec['movement'] in context['answers'].get('blocked_movements',[]):return reject('The added exercise conflicts with saved equipment or excluded movements.')
        capacity=capability(path,today,tz)
        readiness=readiness_history(today,1,tz,path,now=now)['latest']
        loads=[r for r in daily_rows(path) if r['date']<=today.isoformat()]
        policy=recovery_policy(readiness,loads[-1] if loads else None,context['recent_feedback'],capacity,today)
        if policy['level'] in ('hold','recovery'):return reject('Current recovery guidance does not support adding strength work: '+'; '.join(policy['reasons']))
        updated={};changes=[];defaults=[]
        for row,old,day in selected:
            existing=old['exercises']
            if not existing:return reject(f'{day}: review this session’s missing exercise instructions before adding another movement.','needs_input')
            def routine_value(key):
                values=Counter(e[key] for e in existing if e.get('equipment')=='bodyweight') or Counter(e[key] for e in existing)
                ranked=values.most_common()
                if len(ranked)>1 and ranked[0][1]==ranked[1][1]:raise ValueError(f'Specify {key.replace("_"," ")} for the new exercise; the existing routine has no common value.')
                return ranked[0][0]
            reps=exercise.get('repetitions') if 'repetitions' in exercise else routine_value('repetitions')
            rest=exercise.get('rest_seconds') if 'rest_seconds' in exercise else routine_value('rest_seconds')
            if 'repetitions' not in exercise or 'rest_seconds' not in exercise:defaults.append(f'{day}: new exercise uses the routine’s {reps} repetitions and {rest}s rest.')
            if spec['equipment']!='bodyweight':return reject('This addition currently supports reviewed bodyweight exercises; weighted additions need an explicit reviewed load.')
            added={**spec,'sets':exercise['sets'],'repetitions':reps,'rest_seconds':rest,'load':'Body weight; controlled repetitions with the saved comfortable-effort guidance.'}
            new=copy.deepcopy(old);new['exercises'].append(added)
            extra=added['sets']*(reps*3+rest)
            new.update(duration_minutes=math.ceil(old['duration_minutes']+extra/60),duration_estimated=True,user_adjusted=True)
            warmup=new.get('warmup_minutes',0)*60;rest_total=sum(e['sets']*e['rest_seconds'] for e in new['exercises'])
            new['strength_timing']={'method':'saved_workout_plus_added_exercise','sets':sum(e['sets'] for e in new['exercises']),
                'warmup_seconds':warmup,'rest_seconds':rest_total,'work_seconds_estimate':new['duration_minutes']*60-warmup-rest_total}
            try:assign_slot(context['answers']['week_schedule'],day.weekday(),'strength',new['duration_minutes'],old.get('schedule_slot_id'))
            except ValueError as error:return reject(f'{day}: {error}')
            payload(new,'exercise-addition-validation')
            updated[row['id']]=new
            changes.append({'workout_id':row['id'],'expected_revision':row['revision'],'title':row['title'],'date':day.isoformat(),
                'changes':{'definition':new},'summary':[f"Add {added['sets']} × {reps} {added['name']}, {rest}s rest. Existing exercises/targets are unchanged. Estimated total {old['duration_minutes']:g} → {new['duration_minutes']:g} minutes."]})
        anchor=datetime.fromisoformat(state['starts_on']).date();budgets=[]
        for row,new_old,day in selected:
            new=updated[row['id']]
            day_total=new['duration_minutes']+sum(updated.get(peer['id'],json.loads(peer['definition_json']))['duration_minutes'] for peer in sessions if peer['id']!=row['id'] and counts_toward_plan(peer,today,tz) and session_day(peer,tz)==day)
            if day_total>day_limit(context['answers']['week_schedule'],day.weekday()):return reject(f'{day}: the added exercise exceeds the shared day limit.')
            week=anchor+timedelta(weeks=(day-anchor).days//7)
            if any(b['week_start']==week.isoformat() for b in budgets):continue
            estimate=_context(c,now,brief={**state['brief'],'_planning_day':week.isoformat()},timezone_name=tz)['volume_estimates']['strength']
            total=completed_minutes(c,sessions,week,today,tz,'strength')+sum(updated.get(p['id'],json.loads(p['definition_json']))['duration_minutes'] for p in sessions if p['sport']=='strength' and p['completion_status']=='planned' and counts_toward_plan(p,today,tz) and week<=session_day(p,tz)<week+timedelta(days=7))
            cap,_=optional_cap(context['raw_answers'],'strength')
            if total>min(cap if cap is not None else 5040,estimate['availability_ceiling_minutes']):return reject(f'{week}: these additions exceed the saved strength weekly cap or availability. Review that limit first.')
            if total>estimate['effective_ceiling_minutes']:
                if estimate['cap_source']!='approved_strength_progression' or estimate.get('factors',{}).get('reduction',1)<1:return reject(f'{week}: these additions exceed the current strength/recovery allowance. Review the week’s volume first.')
                override={'root_plan_id':program['plan_id'],'week_start':week.isoformat(),'minutes':math.ceil(total),'reason':'Explicit dated exercise addition; recurring weekly limits are unchanged.'}
                budgets.append({**override,'previous_minutes':estimate['effective_ceiling_minutes']})
                for selected_row,_,selected_day in selected:
                    if week<=selected_day<week+timedelta(days=7):updated[selected_row['id']]['strength_week_override']=override
    result={**base,'status':'proposal','root_plan_id':program['plan_id'],'program_revision':program['revision'],'adjustments':changes,
        'weekly_allowance_changes':budgets,'message':'Review these dated exercise additions together; Save applies them atomically. Existing exercises are preserved. '+ ' '.join(defaults)+
        (' '+ ' '.join(f"Week {b['week_start']}: dated strength allowance {b['previous_minutes']:g} → {b['minutes']:g} minutes; recurring limits stay unchanged." for b in budgets) if budgets else '')+' Saving alone does not update Garmin.'}
    result['fingerprint']=hashlib.sha256(encoded({k:result[k] for k in ('root_plan_id','program_revision','adjustments')}).encode()).hexdigest()
    return result
