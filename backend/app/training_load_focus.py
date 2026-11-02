"""Read recorded Garmin load-focus ranges without inferring cycling ability.

The feed is device/account level, not established as cycling-only. These
28-day source totals are not mixed into the app's seven/28-day EWMA load.
"""
import json
import math
from datetime import date,timedelta

FIELDS={'low_aerobic':'monthlyLoadAerobicLow','high_aerobic':'monthlyLoadAerobicHigh','anaerobic':'monthlyLoadAnaerobic'}


def adjust_workout(workout,focus):
    """Keep the intended stimulus; use less interval work when its feed is high.

    The 20% reduction is a provisional product tuning rule, not a Garmin or
    physiological conversion. A below-range category never adds intensity.
    """
    import copy
    category={'tempo':'high_aerobic','long_tempo':'high_aerobic','threshold':'high_aerobic','vo2':'high_aerobic',
              'sprint':'anaerobic','anaerobic':'anaerobic','short_efforts':'anaerobic'}.get(workout.get('workout_kind'))
    observation=focus.get('categories',{}).get(category)
    if workout.get('sport')!='cycling' or focus.get('status')!='current' or not observation or observation['position']!='above':return workout
    result=copy.deepcopy(workout)
    work=[step for step in result['steps'] if step['name'].startswith(('Work lap','Sprint','Anaerobic effort'))]
    if not work:return workout
    previous=sum(s['duration_seconds']*s.get('repetitions',1) for s in work)
    for step in work:step['duration_seconds']=max(1,round(step['duration_seconds']*.8))
    reduced=sum(s['duration_seconds']*s.get('repetitions',1) for s in work)
    if reduced>=previous:return workout
    freed=previous-reduced
    steady=next((s for s in result['steps'] if s['name']=='Steady endurance'),None)
    if steady:steady['duration_seconds']+=freed/steady.get('repetitions',1)
    else:
        easy=copy.deepcopy(result['steps'][0]);easy.update(name='Easy recovery for load context',type='recovery',duration_seconds=freed,repetitions=1)
        result['steps'].insert(-1,easy)
    if result.get('variant_label'):
        result['source_variant_label']=result['variant_label']
        result['variant_label']='Reduced-work '+result['title'].lower()
    result['load_focus_adjustment']={'category':category,'observed_date':focus['date'],'original_work_seconds':previous,'work_seconds':reduced,
        'rule':'Provisional 20% interval-time reduction; retain targets, repetitions, full recovery and session duration.',
        'scope':focus['sport_scope']}
    result['rationale']=list(result.get('rationale',[]))+[
        f"Garmin's {focus['date']} {category.replace('_',' ')} load is above its recorded range. Keep the intended stimulus with less interval time and more easy riding; recovery intervals and the total session duration are preserved. This is an app tuning rule, and the device/account feed is not confirmed as cycling-only."]
    from .training_prescriptions import validate_workout
    return validate_workout(result)


def finite(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0


def normalize(payload,today):
    """Keep dated, non-conflicting source observations; never combine devices."""
    candidates=[]
    endpoints=payload.get('endpoints',{})
    status=endpoints.get('get_training_status')
    sources=[('get_training_four_week_load_balance',endpoints.get('get_training_four_week_load_balance')),
             ('get_training_status',status.get('mostRecentTrainingLoadBalance') if isinstance(status,dict) else None)]
    for source,body in sources:
        mapping=body.get('metricsTrainingLoadBalanceDTOMap') if isinstance(body,dict) else None
        if not isinstance(mapping,dict):continue
        for record in mapping.values():
            if not isinstance(record,dict):continue
            try:observed=date.fromisoformat(record.get('calendarDate',''))
            except (TypeError,ValueError):continue
            if observed>today:continue
            categories={}
            for category,field in FIELDS.items():
                value,low,high=(record.get(field+suffix) for suffix in ('','TargetMin','TargetMax'))
                if not all(finite(v) for v in (value,low,high)) or low>high:continue
                categories[category]={'value':value,'target_min':low,'target_max':high,
                    'position':'below' if value<low else 'above' if value>high else 'within'}
            if categories:candidates.append({'date':observed.isoformat(),'source_endpoint':source,'categories':categories})
    return candidates


def read_load_focus(connection,today):
    candidates=[]
    # Project only the two relevant endpoints: supplementary payloads also
    # retain large activity collections and unrelated private profile data.
    for row in connection.execute("SELECT json_extract(payload_json,'$.endpoints.get_training_status') AS status_json,json_extract(payload_json,'$.endpoints.get_training_four_week_load_balance') AS balance_json FROM garmin_sync_payloads WHERE data_type='supplementary_metrics' AND json_valid(payload_json) AND calendar_date BETWEEN ? AND ? ORDER BY calendar_date DESC LIMIT 8",((today-timedelta(days=7)).isoformat(),today.isoformat())):
        try:payload={'endpoints':{'get_training_status':json.loads(row['status_json']) if row['status_json'] else None,
                                 'get_training_four_week_load_balance':json.loads(row['balance_json']) if row['balance_json'] else None}}
        except (ValueError,TypeError):continue
        if isinstance(payload,dict):candidates.extend(normalize(payload,today))
    base={'source':'Garmin recorded training load focus','unit':'Garmin load','window_days':28,
          'sport_scope':'Device/account-level feed; cycling-only scope is not established.',
          'note':'Ranges describe recorded training-load distribution, not Cycling Ability, a fitness test or clearance for extra intensity.'}
    if not candidates:return {**base,'status':'unavailable','categories':{},'reason':'No usable dated load-focus totals and target ranges were found.'}
    latest=max(c['date'] for c in candidates)
    choices=[c for c in candidates if c['date']==latest]
    # Duplicate endpoint copies are equivalent; contradictory devices/snapshots
    # remain explicit instead of selecting the largest load or summing them.
    signatures={json.dumps(c['categories'],sort_keys=True) for c in choices}
    if len(signatures)>1:return {**base,'status':'ambiguous','date':latest,'categories':{},'reason':'Latest dated device/source records disagree; no combined range is invented.'}
    chosen=choices[0];age=(today-date.fromisoformat(latest)).days
    return {**base,**chosen,'age_days':age,'status':'current' if age<=2 else 'stale',
            'reason':'Latest recorded ranges; use alongside the goal, actual training and recovery.' if age<=2 else 'Stored ranges are over two days old; preserve them as historical context.'}
