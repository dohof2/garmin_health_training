"""Conditional next-morning projection; simulated inputs never become measurements."""
from datetime import datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo
from .database import connect
from .readiness import _load, _series, _sessions, calculate, get_readiness_settings, stamp
from .time_utils import timezone_info

VERSION='readiness-forecast-v4'
KINDS=('hrv_last_night_average','sleep_duration','sleep_score','resting_heart_rate')


def project(as_of, zone_name, rows, activities, coverage, config, *, prepared_sessions=None):
    zone=ZoneInfo(zone_name);day=as_of.astimezone(zone).date();target=day+timedelta(days=1)
    # Whole-day resting HR is incomplete during the forecast day. Never use it as an observed completed day.
    available=[]
    for row in rows:
        local_day=str(row['recorded_at'])[:10]
        end=stamp(row.get('period_end'))
        if local_day>day.isoformat() or end and end>as_of: continue
        if row['metric_type']=='resting_heart_rate' and local_day>=day.isoformat():continue
        available.append(row)
    series=_series(available,zone);synthetic=[];inputs=[];missing=[]
    for kind in KINDS:
        history=sorted((r for key,r in series.get(kind,{}).items() if (day-timedelta(days=13)).isoformat()<=key<=day.isoformat()),key=lambda r:r['wake_date'])[-7:]
        if len(history)<5 or not history or history[-1]['wake_date']<(day-timedelta(days=2)).isoformat():
            missing.append(kind);continue
        predicted=sum(r['value'] for r in history[-3:])/len(history[-3:]) if kind=='hrv_last_night_average' else median(r['value'] for r in history)
        key=target.isoformat()
        wake=datetime.combine(target,time(config['morning_hour']),zone)
        synthetic.append({'id':'projected:'+kind,'source_name':'projection','metric_type':kind,'recorded_at':key,'value':predicted,'unit':history[-1]['unit'],
                          'period_start':(wake-timedelta(seconds=predicted)).isoformat() if kind=='sleep_duration' else key,
                          'period_end':wake.isoformat() if kind.startswith('sleep_') else key})
        inputs.append({'metric':kind,'predicted_value':predicted,'unit':history[-1]['unit'],'observations':len(history),'latest_date':history[-1]['wake_date'],'latest_value':history[-1]['value'],'recent_change':history[-1]['value']-history[0]['value']})
    if missing:return None,inputs,missing
    known_activities=[]
    sessions=_sessions(activities) if prepared_sessions is None else prepared_sessions
    ends={s['id']:s['end'] for s in sessions}
    for row in activities:
        if stamp(row['started_at']) and stamp(row['started_at'])<=as_of:
            # End and load are only known after a recorded workout has finished.
            end=ends.get(row['id'])
            if end and end>as_of:continue
            known_activities.append(row)
    projected_coverage=dict(coverage)
    if coverage.get('coverage_end','')>=day.isoformat():projected_coverage['coverage_end']=target.isoformat()
    known_ids={row['id'] for row in known_activities}
    prepared=(_series(available+synthetic,zone),[s for s in sessions if s['id'] in known_ids])
    result=calculate(target,zone_name,available+synthetic,known_activities,projected_coverage,config,now=wake.astimezone(timezone.utc),prepared=prepared)
    return result,inputs,[]


def features(result,inputs):
    by_kind={r['metric']:r for r in inputs}
    h=by_kind['hrv_last_night_average'];sleep=by_kind['sleep_duration'];quality=by_kind['sleep_score'];rhr=by_kind['resting_heart_rate']
    return [result['score']/100,h['latest_value']/h['predicted_value'],h['recent_change']/h['predicted_value'],
            sleep['latest_value']/3600,sleep['recent_change']/3600,quality['latest_value']/100,
            rhr['recent_change']/max(1,rhr['predicted_value']),result['groups'][2]['percentile']]


def fit_predict(examples,x,baseline):
    """Ridge residual correction with training-only standardization, solved without extra dependencies."""
    n=len(examples);width=len(x)
    centers=[sum(e['features'][j] for e in examples)/n for j in range(width)]
    scales=[max(1e-6,(sum((e['features'][j]-centers[j])**2 for e in examples)/n)**.5) for j in range(width)]
    vectors=[[1]+[(e['features'][j]-centers[j])/scales[j] for j in range(width)] for e in examples]
    size=width+1
    matrix=[[sum(v[i]*v[j] for v in vectors)+(10 if i==j and i else 0) for j in range(size)] for i in range(size)]
    rhs=[sum(v[i]*(e['actual']-e['baseline']) for v,e in zip(vectors,examples)) for i in range(size)]
    for i in range(size):
        pivot=max(range(i,size),key=lambda k:abs(matrix[k][i]));matrix[i],matrix[pivot]=matrix[pivot],matrix[i];rhs[i],rhs[pivot]=rhs[pivot],rhs[i]
        divisor=matrix[i][i]
        if abs(divisor)<1e-10:return baseline
        matrix[i]=[v/divisor for v in matrix[i]];rhs[i]/=divisor
        for k in range(size):
            if k==i:continue
            factor=matrix[k][i];matrix[k]=[a-factor*b for a,b in zip(matrix[k],matrix[i])];rhs[k]-=factor*rhs[i]
    vector=[1]+[(x[j]-centers[j])/scales[j] for j in range(width)]
    return round(max(0,min(100,baseline+sum(v*b for v,b in zip(vector,rhs)))))


def forecast(timezone_name='UTC',path=None,now=None):
    timezone_info(timezone_name);now=now or datetime.now(timezone.utc);zone=ZoneInfo(timezone_name);today=now.astimezone(zone).date()
    settings=get_readiness_settings(path);config=settings['parameters'];lookback=max(config['baseline_days']+7,config['load_reference_days']+7)+101
    with connect(path) as c:rows,activities,coverage=_load(c,today-timedelta(days=lookback),today)
    sessions=_sessions(activities);prepared=(_series(rows,zone),sessions)
    prediction,inputs,missing=project(now,timezone_name,rows,activities,coverage,config,prepared_sessions=sessions)
    response={'date':(today+timedelta(days=1)).isoformat(),'as_of':now.isoformat(),'timezone':timezone_name,'model_version':VERSION,'config_version':settings['config_version'],
              'status':'insufficient_data','score':None,'range':None,'inputs':inputs,'missing_metrics':missing,'validation':None,
              'assumptions':['No additional workouts before tomorrow morning; only recorded completed workouts are included.','Tonight’s HRV uses the mean of the latest three available nights; readiness evaluates six recorded nights plus that projection as a seven-day average. Sleep duration and score use recent seven-observation medians.','Tomorrow’s resting heart rate is a projection from earlier completed days; today’s provisional RHR is excluded from forecast training inputs.'],
              'limitations':['App forecast of the prototype score, not Garmin’s measured training readiness.','Unexpected sleep, stress, illness and unrecorded exercise can change the result.','Historical checks use corrected records available now, not archived snapshots of what was known then.']}
    if prediction is None or prediction['score'] is None:
        response['reason']='Recent measurements or personal baseline/workout coverage are insufficient for a tomorrow estimate.'
        if prediction:response['missing_reasons']=prediction['warnings']
        return response
    response['hrv_7day']=prediction['inputs']['hrv_7day']
    measured=calculate(today,timezone_name,rows,activities,coverage,config,now=now,prepared=prepared)
    names={'autonomic':'HRV and resting heart rate','sleep':'Sleep','workload':'Workout load'}
    response['comparison']={
        'today_score':measured['score'],
        'today_hrv_7day':measured['inputs']['hrv_7day'],
        'baseline_score':prediction['score'],
        'contributors':[{'name':names[current['name']],
                         'today_penalty':current['penalty_min'],
                         'projected_penalty':future['penalty_min'],
                         'score_change':round(current['penalty_min']-future['penalty_min'],2)}
                        for current,future in zip(measured['groups'],prediction['groups'])
                        if current['complete'] and future['complete']],
        'explanation':'No further workouts does not assume unchanged HRV or sleep. HRV is assessed using a seven-day average, including one projected night. That night uses the latest three-night mean; sleep and resting heart rate use recent medians. These assumptions can differ from today’s readings.'}
    # Up to 100 historical targets, ordered oldest to newest. Labels are earlier measured app scores.
    examples=[]
    for offset in range(99,-1,-1):
        target=today-timedelta(days=offset)
        evening=datetime.combine(target-timedelta(days=1),time(23,59),zone).astimezone(timezone.utc)
        actual=calculate(target,timezone_name,rows,activities,coverage,config,now=now,prepared=prepared)
        if actual['score'] is None:continue
        historical,h_inputs,_=project(evening,timezone_name,rows,activities,coverage,config,prepared_sessions=sessions)
        if historical and historical['score'] is not None:
            examples.append({'date':target.isoformat(),'baseline':historical['score'],'actual':actual['score'],'features':features(historical,h_inputs)})
    checks=[]
    for index in range(20,len(examples)):
        train=examples[:index];point=examples[index]
        fitted=fit_predict(train,point['features'],point['baseline'])
        checks.append({'date':point['date'],'actual':point['actual'],'baseline':point['baseline'],'fitted':fitted})
    baseline_error=sum(abs(p['baseline']-p['actual']) for p in checks)/len(checks) if checks else None
    fitted_error=sum(abs(p['fitted']-p['actual']) for p in checks)/len(checks) if checks else None
    # Retain the simpler forecast unless a sufficient chronological check set shows improvement.
    use_fitted=len(checks)>=14 and fitted_error<baseline_error*.95
    selected='fitted' if use_fitted else 'baseline'
    score=fit_predict(examples,features(prediction,inputs),prediction['score']) if use_fitted else prediction['score']
    response.update(score=score,model={'lookback_days':100,'usable_mornings':len(examples),'selected':'regularized_regression' if use_fitted else 'recent_median',
        'baseline_mae':round(baseline_error,1) if baseline_error is not None else None,'regression_mae':round(fitted_error,1) if fitted_error is not None else None,
        'evaluation_mornings':len(checks),'minimum_training_mornings':20,'selection_rule':'At least 14 walk-forward checks and over 5% lower mean absolute error to choose regression.',
        'target':'Next morning’s app prototype score, not Garmin readiness or proven physiological recovery.'})
    errors=[abs(p[selected]-p['actual']) for p in checks]
    # If there are too few model-selection checks, use the unchanged trend baseline for range diagnostics.
    if not use_fitted and len(checks)<14:
        errors=[abs(p['baseline']-p['actual']) for p in examples]
    validation={'mornings':len(errors),'mean_absolute_error':round(sum(errors)/len(errors),1) if errors else None,
                'checks':[{'date':p['date'],'predicted':p[selected],'actual':p['actual']} for p in checks]}
    if len(errors)>=14:
        ordered=sorted(errors);radius=max(5,ordered[min(len(ordered)-1,int(.8*len(ordered)))])
        validation['range_method']='Chronological forecast absolute-error 80th percentile, minimum ±5; not a calibrated confidence interval. Model selection uses these same checks.'
        response.update(status='projected',range={'low':max(0,score-radius),'high':min(100,score+radius)},validation=validation)
    else:
        response.update(status='provisional',validation=validation,reason='Too few complete historical mornings to estimate a useful error range.')
    return response


def forecast_tool(arguments,path=None):
    return {'tool':'get_projected_training_readiness',**forecast(arguments.get('timezone') or 'UTC',path)}
