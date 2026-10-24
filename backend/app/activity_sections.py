"""Recorded activity traces and approximate sustained-climb boundaries. Read only."""
import json
import math
import statistics
from .database import connect
from .intervals import stamp, MAX_GAP
from .activity_stream_charts import reduce_segments

FIELDS={'speed':('speed_mps','Speed','km/h',3.6),'elevation':('elevation_meters','Elevation','m',1),'power':('power_watts','Power','W',1),'cadence':('cadence_rpm','Cadence','rpm',1),'heart_rate':('heart_rate_bpm','Heart rate','bpm',1)}


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def recording(identifier,path=None):
    with connect(path) as c:
        activity=c.execute("SELECT * FROM activities WHERE id=? AND deleted_at IS NULL AND source_name!='synthetic_fixture'",(identifier,)).fetchone()
        if activity is None:raise ValueError('Choose an available recorded activity')
        rows=[dict(r) for r in c.execute('SELECT * FROM activity_samples WHERE activity_id=? ORDER BY recorded_at',(identifier,))]
    origin=stamp(activity['started_at']);distances={}
    # Older normalized samples omit distance; use the retained original FIT,
    # never integrate speed or invent distance from an activity total.
    from .fit_access import original_messages
    try:
        messages=original_messages(identifier,path) or {}
        for record in messages.get('record_mesgs',[]):
            if finite(record.get('distance')) and record.get('timestamp'):
                distances[stamp(record['timestamp'])]=record['distance']/1000
    except (OSError,ValueError,KeyError):pass
    samples=[]
    for row in rows:
        t=stamp(row['recorded_at']);raw=json.loads(row['raw_json'] or '{}')
        distance=raw.get('distance')
        samples.append({**row,'t':t-origin,'distance':distance/1000 if finite(distance) else distances.get(t)})
    return dict(activity),[r for r in samples if r['t']>=0]


def plots(identifier,path=None):
    activity,samples=recording(identifier,path);traces={}
    for metric,(field,label,unit,multiplier) in FIELDS.items():
        segments=[];previous=None;broken=True
        for row in samples:
            value=row[field]
            if not finite(value) or metric!='elevation' and value<0:broken=True;continue
            if previous is not None and (row['t']-previous>MAX_GAP or row['t']<=previous):broken=True
            if broken:segments.append([])
            segments[-1].append({'x':row['t'],'y':value*multiplier,'distance':row['distance'],'segment':len(segments)-1})
            previous=row['t'];broken=False
        traces[metric]={'label':label,'unit':unit,'points':reduce_segments(segments),'sample_count':sum(map(len,segments))}
    return {'activity_id':identifier,'name':activity['name'],'traces':traces,'distance_available':any(r['distance'] is not None for r in samples),'note':'Recorded samples only. Each coloured trace has its own labelled scale. Gaps break lines; elapsed time includes pauses. Distance uses recorded FIT distance and may be unavailable.'}


def climbs(arguments,path=None):
    identifier=arguments.get('activity_id')
    if not isinstance(identifier,str) or not identifier or len(identifier)>160:raise ValueError('Choose an activity ID')
    activity,samples=recording(identifier,path)
    elevation=[r for r in samples if finite(r['elevation_meters'])]
    # Five-second local median reduces altitude jitter without assuming a sample rate.
    smooth=[];left=right=0
    for r in elevation:
        while left<len(elevation) and elevation[left]['t']<r['t']-2.5:left+=1
        while right<len(elevation) and elevation[right]['t']<=r['t']+2.5:right+=1
        smooth.append({**r,'z':statistics.median(p['elevation_meters'] for p in elevation[left:right])})
    sections=[];base=peak=None;previous=None
    def finish():
        if base is not None and peak is not None and peak['z']-base['z']>=20 and peak['t']-base['t']>=60:
            sections.append((base,peak))
    for r in smooth:
        if previous is not None and r['t']-previous>15:finish();base=peak=None
        if base is None:base=peak=r
        elif peak['z']-r['z']>8:finish();base=peak=r
        elif r['z']<base['z']:base=peak=r
        elif r['z']>peak['z']:peak=r
        previous=r['t']
    finish();results=[]
    for begin,end in sections:
        duration=end['t']-begin['t'];energy=covered=moving=known_motion=0
        selected=[r for r in samples if begin['t']<=r['t']<=end['t']]
        for a,b in zip(selected,selected[1:]):
            seconds=b['t']-a['t']
            if not 0<seconds<=MAX_GAP:continue
            if finite(a['power_watts']) and a['power_watts']>=0:energy+=a['power_watts']*seconds;covered+=seconds
            if finite(a['speed_mps']):known_motion+=seconds;moving+=seconds if a['speed_mps']>.5 else 0
        results.append({'start_seconds':begin['t'],'end_seconds':end['t'],'elapsed_seconds':duration,'moving_seconds':moving if known_motion>=duration-.01 else None,'gain_meters':round(end['z']-begin['z'],1),'start_distance_km':begin['distance'],'end_distance_km':end['distance'],'average_power_watts':round(energy/covered,1) if covered>=duration-.01 and covered else None,'covered_average_power_watts':round(energy/covered,1) if covered else None,'power_coverage_seconds':covered,'power_coverage_fraction':covered/duration})
    results.sort(key=lambda r:r['gain_meters'],reverse=True)
    return {'tool':'analyze_activity_climbs','activity_id':identifier,'activity_name':activity['name'],'candidates':results[:5],'candidate_count':len(results),'needs_clarification':len(results)>1 and results[1]['gain_meters']>=results[0]['gain_meters']*.7,'method':'Approximate sustained climbs: 5-second elevation median; split at descent over 8 m or elevation gaps over 15 s; minimum net gain 20 m and elapsed duration 60 s. Moving time requires complete recorded speed coverage and counts intervals above 0.5 m/s. Power uses full-resolution timestamp intervals, including recorded zeros, with no interpolation across gaps over 3 s.','limitations':['Boundaries are algorithmic candidates, not surveyed climb segments.','Elapsed time includes pauses. A full-climb average is unavailable with incomplete power coverage; covered-only averages are labelled separately.'],'evidence_url':f'/api/activities/{identifier}'}
