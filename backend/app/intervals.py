"""Read-only, timestamp-aware interval analysis over stored activity records."""
from __future__ import annotations
import json
import math
import statistics
from datetime import datetime, date, UTC
from .database import connect
from .time_utils import calendar_date, timezone_info

RIDES = ('cycling','gravel_cycling','indoor_cycling','mountain_biking','virtual_ride')
MAX_GAP = 3.0


def stamp(value):
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0


def power_segments(samples):
    """Zero-order hold only until the next observed timestamp, never across a gap."""
    segments=[]
    for left,right in zip(samples,samples[1:]):
        width=right['t']-left['t']
        if 0 < width <= MAX_GAP and number(left['power_watts']):
            segments.append((left['t'],right['t'],float(left['power_watts'])))
    return segments


def weighted_power(segments,start,end):
    parts=[(max(0,min(b,end)-max(a,start)),p) for a,b,p in segments if a<end and b>start]
    coverage=math.fsum(w for w,_ in parts)
    # Missing measurements do not become zeros or silently count as observed effort.
    if coverage < end-start-0.01 or not coverage:return None
    return math.fsum(w*p for w,p in parts)/coverage


def ride_efforts(samples,laps,minimum,maximum,threshold=None):
    segments=power_segments(samples)
    positives=[s['power_watts'] for s in samples if number(s['power_watts']) and s['power_watts']>0]
    cutoff=float(threshold) if threshold is not None else statistics.median(positives)*1.8 if positives else None
    if cutoff is None:return [],None
    efforts=[]
    # Prefer complete timed lap boundaries. Do not use moving time across an unobserved pause.
    for index,lap in enumerate(laps):
        try:
            start=stamp(lap['start_time']);end=stamp(lap['timestamp']);duration=end-start
        except (KeyError,ValueError,TypeError):continue
        if not minimum-0.01 <= duration <= maximum+0.01:continue
        average=weighted_power(segments,start,end)
        if average is not None and average>=cutoff:
            efforts.append({'start':start,'end':end,'duration_seconds':duration,'average_power_watts':average,'method':'recorded_lap','lap_index':index})
    # Detect disjoint above-threshold bursts, not every overlapping rolling window.
    bursts=[];active=None
    for start,end,power in segments:
        if power>=cutoff:
            if active and abs(start-active[1])<0.01:active[1]=end
            else:
                if active:bursts.append(active)
                active=[start,end]
        elif active:bursts.append(active);active=None
    if active:bursts.append(active)
    for start,end in bursts:
        duration=end-start
        if minimum-0.01<=duration<=maximum+0.01 and not any(start<e['end'] and end>e['start'] for e in efforts):
            efforts.append({'start':start,'end':end,'duration_seconds':duration,'average_power_watts':weighted_power(segments,start,end),'method':'power_burst','lap_index':None})
    efforts.sort(key=lambda e:e['start'])
    # Overlapping FIT laps must not count the same effort twice.
    disjoint=[]
    for effort in efforts:
        if not disjoint or effort['start']>=disjoint[-1]['end']:disjoint.append(effort)
    return disjoint,cutoff


def analyze(arguments,path=None):
    timezone=arguments.get('timezone') or 'UTC';timezone_info(timezone)
    start=arguments.get('start_date');end=arguments.get('end_date')
    for value in (start,end):
        if value:date.fromisoformat(value)
    if start and end and start>end:raise ValueError('Start date must precede end date')
    minimum=arguments.get('min_seconds',10);maximum=arguments.get('max_seconds',15)
    repeats=arguments.get('min_repetitions',2);threshold=arguments.get('threshold_watts')
    if not number(minimum) or not number(maximum) or not 1<=minimum<=maximum<=120:raise ValueError('Use interval durations from 1 to 120 seconds')
    if maximum-minimum>5:raise ValueError('Use a duration range no wider than five seconds to keep duration groups comparable')
    if not isinstance(repeats,int) or isinstance(repeats,bool) or not 2<=repeats<=50:raise ValueError('Use 2–50 repetitions')
    if threshold is not None and (not number(threshold) or threshold<=0):raise ValueError('Power threshold must be positive')
    rides=[];observations=[];excluded=0;scanned=0
    with connect(path) as c:
        activities=c.execute("SELECT id,name,started_at,timezone,source_name,raw_json,activity_type FROM activities WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture' AND activity_type IN (?,?,?,?,?) ORDER BY started_at",RIDES).fetchall()
        for activity in activities:
            if arguments.get('sport') not in (None,'all',activity['activity_type']):continue
            day=calendar_date(activity['started_at'],timezone).isoformat()
            if (start and day<start) or (end and day>end):continue
            scanned+=1
            samples=[{**dict(r),'t':stamp(r['recorded_at'])} for r in c.execute('SELECT recorded_at,power_watts FROM activity_samples WHERE activity_id=? ORDER BY recorded_at',(activity['id'],))]
            laps=json.loads(activity['raw_json'] or '{}').get('fit_laps') or []
            efforts,cutoff=ride_efforts(samples,laps,minimum,maximum,threshold)
            if len(efforts)<repeats:
                if not power_segments(samples):excluded+=1
                continue
            groups={}
            for effort in efforts:
                # Integer-second bins are labeled explicitly; exact durations remain in source evidence.
                duration=round(effort['duration_seconds'])
                groups.setdefault(duration,[]).append(effort)
            summaries=[]
            for duration,group in sorted(groups.items()):
                average=statistics.fmean(e['average_power_watts'] for e in group)
                summaries.append({'duration_bin_seconds':duration,'count':len(group),'mean_power_watts':average})
                observations.append({'date':day,'value':average,'key':activity['id'],'id':activity['id'],'source':activity['source_name'],'duration_seconds':duration,'effort_count':len(group)})
            rides.append({'id':activity['id'],'date':day,'name':activity['name'],'effort_count':len(efforts),'threshold_watts':cutoff,'groups':summaries,'evidence_url':f"/api/activities/{activity['id']}"})
    return {'tool':'analyze_sprint_intervals','period':{'start':start,'end':end},'rides_scanned':scanned,'matching_rides':len(rides),'rides_without_usable_power':excluded,'interval_count':sum(r['effort_count'] for r in rides),'rides':rides,'observations':observations,
        'method':{'min_seconds':minimum,'max_seconds':maximum,'min_repetitions':repeats,'threshold':threshold if threshold is not None else '1.8 × each ride’s median positive power','maximum_sample_gap_seconds':MAX_GAP,'power_average':'timestamp-weighted zero-order hold; complete coverage required','duration_grouping':'nearest whole second; inspect exact durations using get_activity_stream'},
        'limitations':['Detected high-power efforts are candidates, not proof of a prescribed sprint workout.','Only repeated efforts within the requested duration range are included. Long efforts are not chopped into overlapping short sprints.','Missing/large sample gaps are never filled; final samples without a following timestamp have no assumed duration.','Ride-average effort power is grouped by duration; recovery, fatigue, conditions and effort intent are not normalized. A rising chart alone does not establish fitness improvement.']}


def stream(arguments,path=None):
    from .history import get_activity
    identifier=arguments.get('activity_id')
    if not identifier:
        with connect(path) as c:
            row=c.execute("SELECT id FROM activities WHERE deleted_at IS NULL AND source_name!='synthetic_fixture' AND activity_type IN (?,?,?,?,?) ORDER BY started_at DESC LIMIT 1",RIDES).fetchone()
        identifier=row['id'] if row else None
    activity=get_activity(identifier,path,arguments.get('timezone')) if identifier else None
    if not activity:raise ValueError('No recorded activity available')
    limit=arguments.get('limit',200)
    if not isinstance(limit,int) or isinstance(limit,bool) or not 10<=limit<=1000:raise ValueError('Use 10–1000 sample points')
    start=arguments.get('start_seconds',0);end=arguments.get('end_seconds')
    if not number(start) or (end is not None and (not number(end) or end<start)):raise ValueError('Invalid elapsed-time range')
    with connect(path) as c:
        raw=c.execute('SELECT raw_json FROM activities WHERE id=?',(identifier,)).fetchone()
        samples=[dict(r) for r in c.execute('SELECT recorded_at,power_watts,heart_rate_bpm,cadence_rpm,speed_mps FROM activity_samples WHERE activity_id=? ORDER BY recorded_at',(identifier,))]
    origin=stamp(activity['started_at'])
    samples=[{**r,'elapsed_seconds':stamp(r['recorded_at'])-origin} for r in samples]
    samples=[r for r in samples if r['elapsed_seconds']>=start and (end is None or r['elapsed_seconds']<=end)]
    count=len(samples)
    if count>limit:samples=[samples[round(i*(count-1)/(limit-1))] for i in range(limit)]
    laps=json.loads(raw['raw_json'] or '{}').get('fit_laps',[])
    return {'tool':'get_activity_stream','activity':activity,'lap_count':len(laps),'laps':laps[:100],'laps_truncated':len(laps)>100,'sample_count':count,'samples':samples,'display_reduced':count>limit,'evidence_url':f'/api/activities/{identifier}',
        'note':'Timestamped recorded samples; null values and gaps remain missing. Reduced display is not the input to sprint detection.'}


def plot_result(spec,result):
    from .charts import analyze_points
    duration=spec.get('sprint_seconds')
    points=[{**o,'x':o['date'],'y':o['value']} for o in result['observations'] if duration is None or o['duration_seconds']==duration]
    count=len(points);latest=points[-1] if points else None
    if count>2000:points=[points[round(i*(count-1)/1999)] for i in range(2000)]
    return {'spec':spec,'points':points,'unit':'W','x_unit':'Date','count':count,'excluded':result['rides_without_usable_power'],'unpaired':0,'latest':latest,'sources':sorted({p['source'] for p in points}),'notes':[f"Per-ride mean power of detected efforts in the {duration}-second duration bin; minimum {result['method']['min_repetitions']} efforts per qualifying ride.",f"Detection threshold: {result['method']['threshold']}. Duration bins round to the nearest second; full sample coverage required.",*result['limitations']], 'analysis':analyze_points(points,spec)}


def analyze_tool(arguments,path=None):
    result=analyze(arguments,path)
    result['plots']=[plot_result({'metric':'activity_sprint_power','x_metric':'date','kind':'scatter','size':'full','title':f'{duration}-second repeated efforts · average power by ride','sprint_seconds':duration,'interval_min_seconds':arguments.get('min_seconds',10),'interval_max_seconds':arguments.get('max_seconds',15),'min_repetitions':arguments.get('min_repetitions',2),**({'threshold_watts':arguments['threshold_watts']} if arguments.get('threshold_watts') is not None else {}),**{k:v for k,v in [('start',arguments.get('start_date')),('end',arguments.get('end_date')),('timezone',arguments.get('timezone'))] if v}},result) for duration in sorted({o['duration_seconds'] for o in result['observations']})]
    # All rides are included in plots/counts; bound model-facing record details explicitly.
    result['returned_rides']=min(100,len(result['rides']));result['rides_truncated']=len(result['rides'])>100
    result['rides']=result['rides'][-100:]
    result['returned_ride_order']='latest 100 matching rides, chronological'
    del result['observations']
    return result
