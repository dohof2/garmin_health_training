"""Broad ride comparisons, separate from GPS-course matching."""
from datetime import date, timedelta
import json
import math
import re
from statistics import median, quantiles

from .database import connect
from .history import list_activities


def requested(message):
    text = message.lower()
    return (bool(re.search(r'\b(last|latest|most recent|my)\s+(?:cycling |bike |bicycle )?ride\b', text))
            and bool(re.search(r'\b(compared?|comparison|versus|vs|stack up)\b', text)))


def scope(message):
    if re.search(r'\b(?:not|no|without)\s+(?:using\s+)?(?:gps|route matching|matching)\b|\b(?:normal|general|ordinary) comparison\b',message,re.I): return 'all'
    if re.search(r'\b(gps|same course|same route|matching routes?|match(?:ing)? rides?)\b',message,re.I): return 'gps'
    if re.search(r'\b(all (?:other )?rides|general(?: records| comparison| rides)?|overall)\b',message,re.I): return 'all'
    return None


def resolve_followup(message, history):
    if not history or history[-1]['role']!='assistant': return message
    prompt = history[-1]['content']
    scope_question = 'All rides, or rides on the same GPS route?' in prompt
    # A short explicit scope change may follow the default general comparison.
    if not requested(message) and scope(message) and len(message.split())<=10:
        original=next((h['content'] for h in reversed(history) if h['role']=='user' and requested(h['content'])),None)
        if original and (scope_question or 'compared with' in prompt):
            from .plot_requests import period
            selected=period(original,date.today())
            bounds=f'from {selected[0]} to {selected[1]}' if selected else 'across full history' if re.search(r'\b(?:all|full|entire) history\b',original,re.I) else ''
            return 'Compare my latest ride '+message+' '+bounds
    period_question = 'Which period should I compare:' in prompt
    if not (scope_question or period_question) or requested(message): return message
    from .plot_requests import period
    if scope_question and not scope(message):
        if re.fullmatch(r'(?:yes|no|please|not sure)[.!? ]*',message,re.I):
            original=next((h['content'] for h in reversed(history) if h['role']=='user' and requested(h['content'])),None)
            return original or message
        return message
    if period_question and not period(message,date.today()) and not re.search(r'\bhistory\b',message,re.I): return message
    if period_question and period(message,date.today()):
        selected=period(message,date.today())
        message=f'from {selected[0]} to {selected[1]}'
    for index in range(len(history)-1,-1,-1):
        if history[index]['role']=='user' and requested(history[index]['content']):
            replies=[h['content'] for h in history[index+1:] if h['role']=='user']
            return ' '.join([history[index]['content'],*replies,message])
    return message


def comparison_start(message, today):
    from .plot_requests import period
    selected = period(message,today)
    return date.fromisoformat(selected[0]) if selected else date(today.year,1,1)


def comparison_end(message, today):
    from .plot_requests import period
    selected = period(message,today)
    return date.fromisoformat(selected[1]) if selected else today


def riding_volume_context(rides, reference):
    """Recorded time, not physiological load or verified inactivity on empty days."""
    anchor=date.fromisoformat(reference['local_date'])
    windows=[]
    for index in range(9):
        end=anchor-timedelta(days=7*index);start=end-timedelta(days=6)
        selected=[r for r in rides if start.isoformat()<=r['local_date']<=end.isoformat()]
        missing=sum(r.get('duration_seconds') is None for r in selected)
        values=[float(r['duration_seconds'])/3600 for r in selected if r.get('duration_seconds') is not None]
        windows.append({'start':start.isoformat(),'end':end.isoformat(),'hours':sum(values),'rides':len(selected),'missing_durations':missing})
    baseline=[w['hours'] for w in windows[1:] if w['rides'] and not w['missing_durations']]
    result={'current':windows[0],'baseline_windows':windows[1:],'comparison_week_count':len(baseline),'interpretation':None}
    if len(baseline)>=4 and not windows[0]['missing_durations']:
        lower,_,upper=quantiles(baseline,n=4,method='inclusive')
        hours=windows[0]['hours'];position='above' if hours>upper else 'below' if hours<lower else 'within'
        result.update(recent_middle_range_hours=[lower,upper],position=position,
                      interpretation=f"Your seven-day recorded riding time ({hours:.1f} h) was {position} your recent typical range ({lower:.1f}–{upper:.1f} h across {len(baseline)} prior weeks with rides).")
    return result


def training_benefit(connection, activity_id):
    """Report source labels; scores alone cannot identify a sprint/base category."""
    row=connection.execute('SELECT raw_json FROM activities WHERE id=?',(activity_id,)).fetchone()
    payload=json.loads(row['raw_json'] or '{}') if row else {}
    summary={**payload,**(payload.get('summaryDTO') or {})}
    label=summary.get('trainingEffectLabel')
    labels={'AEROBIC_BASE':'Aerobic base (endurance)','RECOVERY':'Recovery','TEMPO':'Tempo',
            'LACTATE_THRESHOLD':'Lactate threshold','THRESHOLD':'Threshold','VO2MAX':'VO₂ max',
            'VO2_MAX':'VO₂ max','ANAEROBIC_CAPACITY':'Anaerobic capacity','ANAEROBIC':'Anaerobic',
            'SPEED':'Speed','SPRINT':'Sprint'}
    label_text=labels.get(label) if isinstance(label,str) else None
    scores={}
    for r in connection.execute("SELECT metric_type,value,source_method,source_field FROM activity_metrics WHERE activity_id=? AND metric_type IN ('aerobic_training_effect','anaerobic_training_effect')",(activity_id,)):
        if math.isfinite(r['value']) and 0<=r['value']<=5: scores[r['metric_type']]=dict(r)
    for field,metric in [('aerobicTrainingEffect','aerobic_training_effect'),('trainingEffect','aerobic_training_effect'),('anaerobicTrainingEffect','anaerobic_training_effect')]:
        value=summary.get(field)
        if metric not in scores and isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<=value<=5:
            scores[metric]={'value':value,'source_method':'garmin_summary','source_field':field}
    sessions=payload.get('fit_sessions') or []
    if len(sessions)==1:
        for field,metric in [('total_training_effect','aerobic_training_effect'),('total_anaerobic_training_effect','anaerobic_training_effect')]:
            value=sessions[0].get(field)
            if metric not in scores and isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<=value<=5:
                scores[metric]={'value':value,'source_method':'fit_session','source_field':field}
    parts=[f"Garmin primary benefit: {label_text}." if label_text else 'Primary training benefit is unavailable in the stored source label.']
    values=[f"{name}: {scores[key]['value']:.1f}" for key,name in [('aerobic_training_effect','aerobic effect'),('anaerobic_training_effect','anaerobic effect')] if key in scores]
    if values: parts.append('Training Effect — '+', '.join(values)+' (0–5).')
    return {'label':label_text,'source_label':label,'label_source':'garmin_summary' if label_text else None,'scores':scores,'answer':' '.join(parts)}


def compare_latest_ride(today: date, path=None, timezone_name=None, message='this year'):
    from .ai_tools import RIDE_ACTIVITY_TYPES
    # History already excludes deleted and synthetic activities. Its date filters
    # use the selected local timezone, before applying pagination.
    start = comparison_start(message, today)
    end = comparison_end(message, today)
    records = []
    offset = 0
    while True:
        page = list_activities(limit=1000, offset=offset, end_date=today,
                               timezone_name=timezone_name, path=path)
        records.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    rides = [r for r in records if r['activity_type'] in RIDE_ACTIVITY_TYPES]
    if not rides:
        return {'tool': 'compare_latest_ride', 'answer': 'There is no recorded ride available to compare.'}
    reference = rides[0]
    if re.search(r'\b(?:all|full|entire) history\b',message,re.I):
        start=date.fromisoformat(min(r['local_date'] for r in rides))
    others = [r for r in rides[1:] if start.isoformat() <= r['local_date'] <= end.isoformat()]
    fields = [('distance_meters', 'Distance', 'km', .001),
              ('duration_seconds', 'Duration', 'hours', 1/3600),
              ('elevation_gain_meters', 'Climb', 'm', 1),
              ('calories_kcal', 'Recorded calories', 'kcal', 1),
              ('average_power', 'Average power', 'W', 1),
              ('average_heart_rate', 'Average heart rate', 'bpm', 1)]
    by_id = {r['id']: r for r in [reference, *others]}
    # Prefer recorded activity summaries; do not substitute zeros for missing data.
    with connect(path) as c:
        benefit=training_benefit(c,reference['id'])
        for row in c.execute("SELECT activity_id,metric_type,value FROM activity_metrics WHERE metric_type IN ('average_power','average_heart_rate')"):
            if row['activity_id'] in by_id:
                by_id[row['activity_id']][row['metric_type']] = row['value']
    lines = [f"{reference['name'] or reference['activity_type']} · {reference['local_date']}, compared with {len(others)} other rides ({start.isoformat()}–{end.isoformat()})."]
    comparisons = []
    for field, label, unit, scale in fields:
        value = reference.get(field)
        values = [float(r[field]) * scale for r in others if r.get(field) is not None]
        if value is None or not values:
            continue
        value = float(value) * scale
        baseline = median(values)
        delta = ((value / baseline - 1) * 100) if baseline else None
        change = f", {abs(delta):.1f}% {'above' if delta >= 0 else 'below'} the median" if delta is not None else ''
        text=f"{label}: {value:.1f} {unit} vs median {baseline:.1f} {unit}{change} (n={len(values)})."
        comparisons.append({'metric': field, 'reference': value, 'median': baseline, 'count': len(values), 'unit': unit,'text':text})
    focused=[r for r in comparisons if ('power' in r['metric'] and re.search(r'\bpower\b',message,re.I)) or ('heart_rate' in r['metric'] and re.search(r'\bheart rate\b',message,re.I))]
    if not focused:
        focused=[r for key in ['distance_meters','duration_seconds','average_power'] for r in comparisons if r['metric']==key]
    shown=comparisons if re.search(r'\b(?:details?|all measurements|full breakdown)\b',message,re.I) else (focused+[r for r in comparisons if r not in focused])[:3]
    lines.extend(r['text'] for r in shown)
    for r in comparisons: r.pop('text')
    if not others:
        lines.append('There are no other recorded rides in that period to establish a comparison.')
    elif not comparisons:
        lines.append('The stored rides lack the shared measurements needed for a numerical comparison.')
    by_metric={r['metric']:r for r in comparisons}
    duration=by_metric.get('duration_seconds');power=by_metric.get('average_power')
    personal=[]
    if duration and duration['median']>0:
        ratio=duration['reference']/duration['median']
        personal.append('This was longer than your typical recorded ride' if ratio>1.25 else 'This was shorter than your typical recorded ride' if ratio<.75 else 'The duration was close to your typical recorded ride')
    if power and power['median']>0 and power['count']>=3:
        ratio=power['reference']/power['median']
        phrase='lower average power' if ratio<.75 else 'higher average power' if ratio>1.25 else 'average power close to your recorded norm'
        personal.append('with '+phrase if personal else 'This ride had '+phrase)
    interpretation=(', '.join(personal)+'.') if personal else None
    if interpretation: lines.append(interpretation)
    if benefit['label'] or benefit['scores']: lines.append(benefit['answer'])
    volume=riding_volume_context(rides,reference)
    if volume['interpretation']: lines.append(volume['interpretation'])
    lines.append('Includes all cycling types; route and effort differ, so this alone does not establish fitness improvement.')
    return {'tool': 'compare_latest_ride', 'period': {'start': start.isoformat(), 'end': end.isoformat()},
            'reference_record': {'id': reference['id'], 'name': reference['name'], 'activity_type': reference['activity_type'], 'local_date': reference['local_date'],
                                 'url': f"/api/activities/{reference['id']}"},
            'candidate_pool_count': len(others), 'comparisons': comparisons,'interpretation':interpretation,'riding_volume':volume,'training_benefit':benefit, 'answer': '\n\n'.join(lines)}
