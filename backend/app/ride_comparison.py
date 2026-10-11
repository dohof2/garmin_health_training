"""Broad ride comparisons, separate from GPS-course matching."""
from datetime import date, timedelta
import re
from statistics import median

from .database import connect
from .history import list_activities


def requested(message):
    text = message.lower()
    return (bool(re.search(r'\b(last|latest|most recent)\s+(ride|cycling ride|bike ride)\b', text))
            and bool(re.search(r'\b(compared?|comparison|versus|vs)\b', text))
            and bool(re.search(r'\b(this year|(?:the )?(?:last|past) year|last 12 months|past 12 months)\b', text))
            and not re.search(r'\b(gps|same course|same route|similar|matching)\b', text))


def comparison_start(message, today):
    if re.search(r'\b(?:the (?:last|past) year|(?:last|past) 12 months|past year)\b', message, re.I):
        return today - timedelta(days=365)
    if re.search(r'\blast year\b', message, re.I):
        return date(today.year - 1, 1, 1)
    return date(today.year, 1, 1)


def comparison_end(message, today):
    if re.search(r'\blast year\b', message, re.I) and not re.search(r'\bthe last year\b', message, re.I):
        return date(today.year - 1, 12, 31)
    return today


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
        for row in c.execute("SELECT activity_id,metric_type,value FROM activity_metrics WHERE metric_type IN ('average_power','average_heart_rate')"):
            if row['activity_id'] in by_id:
                by_id[row['activity_id']][row['metric_type']] = row['value']
    lines = [f"Your latest recorded ride was {reference['name'] or reference['activity_type']} on {reference['local_date']}.",
             f"I compared it with {len(others)} other recorded rides from {start.isoformat()} through {end.isoformat()}, excluding the reference ride. This includes all cycling types; it does not require a matching GPS route."]
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
        lines.append(f"{label}: {value:.1f} {unit}; comparison-period other-ride median {baseline:.1f} {unit}{change} ({len(values)} rides with this measurement).")
        comparisons.append({'metric': field, 'reference': value, 'median': baseline, 'count': len(values), 'unit': unit})
    if not others:
        lines.append('There are no other recorded rides in that period to establish a comparison.')
    elif not comparisons:
        lines.append('The stored rides lack the shared measurements needed for a numerical comparison.')
    lines.append('Longer, harder or faster does not by itself mean better: route, indoor/outdoor riding, stops and intended effort differ. Missing measurements are omitted.')
    lines.append(f"Reference activity: /api/activities/{reference['id']}")
    return {'tool': 'compare_latest_ride', 'period': {'start': start.isoformat(), 'end': end.isoformat()},
            'reference_record': {'id': reference['id'], 'name': reference['name'], 'local_date': reference['local_date'],
                                 'url': f"/api/activities/{reference['id']}"},
            'candidate_pool_count': len(others), 'comparisons': comparisons, 'answer': '\n\n'.join(lines)}
