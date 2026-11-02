"""Bounded, read-only comparisons over explicitly selected recorded sections."""
import json,math,statistics
from .activity_sections import recording,finite
from .intervals import MAX_GAP,stamp,ride_efforts

METRICS={'power_watts':('power','W',1),'heart_rate_bpm':('heart_rate','bpm',1),'cadence_rpm':('cadence','rpm',1),'speed_mps':('speed','km/h',3.6)}


def number(value,name,minimum=0):
    if not finite(value) or value<minimum:raise ValueError(name+' must be a finite number in range')
    return float(value)


def statistics_for(samples,start,end):
    duration=end-start;metrics={};moving=known_motion=0.
    for field,(name,unit,scale) in METRICS.items():
        total=covered=0.
        for left,right in zip(samples,samples[1:]):
            width=right['t']-left['t'];overlap=max(0,min(end,right['t'])-max(start,left['t']))
            value=left[field]
            if not 0<width<=MAX_GAP or not overlap or not finite(value) or value<0:continue
            covered+=overlap;total+=value*overlap
            if field=='speed_mps':
                known_motion+=overlap;moving+=overlap if value>.5 else 0
        metrics[name]={'unit':unit,'average':round(total/covered*scale,3) if covered>=duration-.01 and covered else None,
                       'covered_average':round(total/covered*scale,3) if covered else None,
                       'coverage_seconds':round(covered,3),'coverage_fraction':min(1.,covered/duration)}
    def boundary(t):return next((r for r in samples if abs(r['t']-t)<.001),None)
    first,last=boundary(start),boundary(end)
    gain=last['elevation_meters']-first['elevation_meters'] if first and last and finite(first['elevation_meters']) and finite(last['elevation_meters']) else None
    return {'start_seconds':start,'end_seconds':end,'elapsed_seconds':round(duration,3),
            'moving_seconds':round(moving,3) if known_motion>=duration-.01 else None,
            'elevation_change_meters':round(gain,3) if gain is not None else None,'metrics':metrics}


def terrain_candidates(samples,kind):
    candidates=[];active=None
    smoothed=[]
    for i,row in enumerate(samples):
        heights=[p['elevation_meters'] for p in samples[max(0,i-1):i+2] if abs(p['t']-row['t'])<=3 and finite(p['elevation_meters'])]
        smoothed.append({**row,'z':statistics.median(heights) if heights and finite(row['elevation_meters']) else None})
    def finish():
        if active and active[1]-active[0]>=30:candidates.append(tuple(active))
    for a,b in zip(smoothed,smoothed[1:]):
        valid=0<b['t']-a['t']<=MAX_GAP and finite(a['distance']) and finite(b['distance']) and b['distance']>a['distance'] and finite(a['z']) and finite(b['z'])
        grade=(b['z']-a['z'])/((b['distance']-a['distance'])*1000) if valid else None
        fits=valid and (abs(grade)<=.02 if kind=='flat' else grade<-.02 if kind=='descent' else grade>.02)
        if fits:
            if active and abs(active[1]-a['t'])<.001:active[1]=b['t']
            else:finish();active=[a['t'],b['t']]
        else:finish();active=None
    finish();return candidates


def distance_candidates(samples,start,end):
    groups=[];group=[];previous=None
    for row in samples:
        if not finite(row['distance']):continue
        if previous is not None and row['distance']<previous:
            if group:groups.append(group)
            group=[]
        group.append(row);previous=row['distance']
    if group:groups.append(group)
    result=[]
    for group in groups:
        # Use observed distance crossings only; no speed integration or invented
        # fraction of whole-ride distance. Report the actual observed boundaries.
        a=next((r for r in group if r['distance']>=start),None)
        b=next((r for r in group if r['distance']>=end),None)
        if a and b and a['t']<b['t'] and group[0]['distance']<=start:
            result.append((a['t'],b['t']))
    return result


def analyze(arguments,path=None):
    identifier=arguments.get('activity_id');requests=arguments.get('sections')
    if not isinstance(identifier,str) or not 1<=len(identifier)<=160:raise ValueError('Choose an activity ID')
    if not isinstance(requests,list) or not 1<=len(requests)<=2:raise ValueError('Select one or two sections')
    activity,samples=recording(identifier,path)
    duration=activity.get('duration_seconds') or max((r['t'] for r in samples),default=0)
    results=[];choices=[]
    for position,request in enumerate(requests,1):
        if not isinstance(request,dict) or set(request)-{'kind','start','end','index','threshold_watts','min_seconds','max_seconds'}:raise ValueError('Invalid section selection')
        kind=request.get('kind');bounds=[];detection={}
        allowed={'kind','index'}|({'start','end'} if kind in ('time','distance') else {'threshold_watts','min_seconds','max_seconds'} if kind in ('sprint','effort') else set())
        if set(request)-allowed:raise ValueError('Some selection fields do not apply to this section kind; use explicit time/distance bounds or an effort duration filter.')
        if kind in ('time','distance'):
            start=number(request.get('start'),'Section start');end=number(request.get('end'),'Section end')
            if end<=start:raise ValueError('Section end must follow its start')
            if kind=='time':
                if end>duration+.01:raise ValueError('The requested time range extends beyond the recorded activity')
                bounds=[(start,end)]
            else:bounds=distance_candidates(samples,start,end)
        elif kind in ('flat','descent','climb'):bounds=terrain_candidates(samples,kind)
        elif kind in ('sprint','effort'):
            minimum=number(request.get('min_seconds',5 if kind=='sprint' else 30),'Minimum duration',1)
            maximum=number(request.get('max_seconds',30 if kind=='sprint' else 1200),'Maximum duration',minimum)
            if maximum>3600:raise ValueError('Choose candidate efforts up to one hour')
            threshold=request.get('threshold_watts')
            if threshold is not None:threshold=number(threshold,'Power threshold',1)
            efforts,cutoff=ride_efforts(samples,[],minimum,maximum,threshold)
            detection={'threshold_watts':cutoff,'threshold_rule':'explicit' if threshold is not None else '1.8 × median positive recorded power','min_seconds':minimum,'max_seconds':maximum}
            bounds=[(r['start'],r['end']) for r in efforts]
        elif kind=='lap':
            payload=json.loads(activity.get('raw_json') or '{}');laps=payload.get('fit_laps') or []
            if not laps:
                from .fit_access import original_messages
                laps=(original_messages(identifier,path) or {}).get('lap_mesgs',[])
            origin=stamp(activity['started_at'])
            for lap in laps:
                try:
                    a,b=stamp(lap['start_time'])-origin,stamp(lap['timestamp'])-origin
                    if 0<=a<b<=duration+.01:bounds.append((a,b))
                except (KeyError,TypeError,ValueError):continue
        else:raise ValueError('Choose time, distance, lap, flat, climb, descent, sprint or effort')
        index=request.get('index')
        if index is not None and (type(index) is not int or not 1<=index<=len(bounds)):raise ValueError('Choose an available section index starting at 1')
        if index is None and len(bounds)!=1:
            choices.append({'section':position,'kind':kind,'candidate_count':len(bounds),'candidates':[{'index':i+1,'start_seconds':a,'end_seconds':b,'elapsed_seconds':b-a} for i,(a,b) in enumerate(bounds[:8])],'truncated':len(bounds)>8,
                            'reason':'Choose the candidate index; no section was silently substituted.' if bounds else 'No supported section boundaries were found in the available recordings.'})
            continue
        start,end=bounds[(index or 1)-1]
        results.append({'section':position,'kind':kind,'requested':request,'detection':detection,**statistics_for(samples,start,end)})
    comparisons={}
    if len(results)==2:
        for metric in METRICS.values():
            name,unit,_=metric;a,b=(r['metrics'][name]['average'] for r in results)
            comparisons[name]={'unit':unit,'second_minus_first':round(b-a,3) if a is not None and b is not None else None}
    return {'tool':'analyze_activity_sections','activity_id':identifier,'activity_name':activity.get('name'),'sections':results,
            'needs_clarification':bool(choices),'selections':choices,'comparisons':comparisons,'evidence_url':f'/api/activities/{identifier}',
            'method':'Full-resolution timestamp-weighted samples, clipped at section bounds; recorded zeros retained and gaps over three seconds excluded. Distance bounds use observed crossings. Terrain uses a local three-point median, recorded grade ±2% and at least 30 seconds; effort candidates use disjoint above-threshold power segments.',
            'limitations':['Terrain/effort candidates are approximate, not verified workout intent or surveyed boundaries.','A full-section average is withheld when coverage is incomplete; covered averages are explicitly partial.','Missing distance/elevation/metric data is not replaced by whole-ride or unrelated lap statistics.']}


def conversational_selection(message,context,activity_id):
    import re
    # Only explicit ranges are resolved here; the model can use the same tool
    # for more involved selections. A trailing range does not imply GPS matching.
    pattern=r'\b(?:(minutes?|mins?|kilometers?|kilometres?|km)\s+(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(minutes?|mins?|kilometers?|kilometres?|km))\b'
    found=[]
    for match in re.finditer(pattern,message,re.I):
        unit=match[1] or match[6];start=float(match[2] or match[4]);end=float(match[3] or match[5]);time=unit.lower().startswith('min')
        found.append({'kind':'time' if time else 'distance','start':start*60 if time else start,'end':end*60 if time else end})
    if found:
        if len(found)>2:raise ValueError('Compare at most two sections at once')
        return found
    if context and re.search(r'\b(there|that section|same section|those sections|compare them)\b',message,re.I) and re.search(r'power|watts|heart|cadence|speed|long|duration|compare|time',message,re.I) and not re.search(r'\b(last|first|next|other|different|climb|uphill|up hill|descent|flat|sprint|lap|interval|effort)\b',message,re.I):
        if not isinstance(context,list) or len(context)>2:raise ValueError('Retain at most two selected sections')
        return [{'kind':'time','start':item.get('start_seconds'),'end':item.get('end_seconds')} for item in context if isinstance(item,dict) and item.get('activity_id')==activity_id]
    return None


def answer(result,message=''):
    import re
    from .workout_edits import duration_label
    if result['needs_clarification']:
        lines=[]
        for selection in result['selections']:
            if not selection['candidate_count']:lines.append(f"No supported {selection['kind']} section was found in the available recorded data.")
            else:
                choices='; '.join(f"{c['index']}: {duration_label(c['start_seconds'])}–{duration_label(c['end_seconds'])}" for c in selection['candidates'])
                lines.append(f"Which {selection['kind']} section do you mean? {choices}."+(' More candidates are available by index.' if selection['truncated'] else ''))
        return ' '.join(lines)
    labels={'power':'Time-weighted average power','heart_rate':'Average heart rate','cadence':'Average cadence','speed':'Average speed'}
    requested=[key for key,pattern in [('power',r'power|watts'),('heart_rate',r'heart rate|\bhr\b'),('cadence',r'cadence'),('speed',r'speed')] if re.search(pattern,message,re.I)] or ['power','heart_rate']
    lines=[]
    for section in result['sections']:
        parts=[f"Section {section['section']}: {duration_label(section['start_seconds'])}–{duration_label(section['end_seconds'])}, {duration_label(section['elapsed_seconds'])} elapsed."]
        for key in requested:
            metric=section['metrics'][key]
            if metric['average'] is not None:parts.append(f"{labels[key]}: {metric['average']:g} {metric['unit']}.")
            elif metric['covered_average'] is not None:parts.append(f"{labels[key]} is incomplete; covered-data average {metric['covered_average']:g} {metric['unit']} at {metric['coverage_fraction']:.0%} coverage.")
            else:parts.append(f"{labels[key]} is unavailable in this section.")
        lines.append(' '.join(parts))
    if len(result['sections'])==2:
        changes=[f"{key.replace('_',' ')} {result['comparisons'][key]['second_minus_first']:+g} {result['comparisons'][key]['unit']}" for key in requested if result['comparisons'][key]['second_minus_first'] is not None]
        if changes:lines.append('Second versus first: '+', '.join(changes)+'.')
    return '\n\n'.join(lines)
