"""Bounded GPS tracks with co-located sensor values; no guessed coordinates."""
import math
from datetime import datetime
from .database import connect


def route(activity_id, path=None, max_points=4000):
    with connect(path) as c:
        exists=c.execute("SELECT 1 FROM activities WHERE id=? AND deleted_at IS NULL AND source_name!='synthetic_fixture'",(activity_id,)).fetchone()
        if not exists:raise KeyError('Activity not found')
        rows=c.execute('SELECT recorded_at,latitude,longitude,power_watts,speed_mps,heart_rate_bpm,elevation_meters FROM activity_samples WHERE activity_id=? ORDER BY recorded_at,id',(activity_id,)).fetchall()
    def valid(value,low,high):
        return isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high
    candidates=[];segment=0;previous=None
    for row in rows:
        if not valid(row['latitude'],-90,90) or not valid(row['longitude'],-180,180):
            previous=None;segment+=1;continue
        when=datetime.fromisoformat(row['recorded_at'].replace('Z','+00:00'))
        if previous is not None and (when-previous).total_seconds()>120:segment+=1
        previous=when
        candidates.append({**dict(row),'segment':segment})
    count=len(candidates)
    if count>max_points:
        indices={round(i*(count-1)/(max_points-1)) for i in range(max_points)}
        candidates=[point for i,point in enumerate(candidates) if i in indices]
    for point in candidates:
        for field in ('power_watts','speed_mps','heart_rate_bpm','elevation_meters'):
            value=point[field]
            if not isinstance(value,(int,float)) or not math.isfinite(value) or field!='elevation_meters' and value<0:point[field]=None
    available=[field for field in ('power_watts','speed_mps','heart_rate_bpm','elevation_meters') if any(p[field] is not None for p in candidates)]
    return {'activity_id':activity_id,'points':candidates,'gps_sample_count':count,'sampled':count>len(candidates),
            'available_metrics':available,'default_metric':'power_watts' if 'power_watts' in available else 'speed_mps' if 'speed_mps' in available else None}
