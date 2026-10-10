"""Validated chart queries shared by the dashboard and assistant. No generated SQL."""
from __future__ import annotations

import json
import math
import uuid
from datetime import date
from pathlib import Path

from .database import connect
from .time_utils import calendar_date, timezone_info

ACTIVITY_FIELDS = {'distance': ('distance_meters', 'km', .001),
                   'duration': ('duration_seconds', 'min', 1 / 60),
                   'calories': ('calories_kcal', 'kcal', 1),
                   'elevation': ('elevation_gain_meters', 'm', 1),
                   'power': ('average_power', 'W', 1),
                   'speed': ('speed', 'km/h', 3.6),
                   'heart_rate': ('average_heart_rate', 'bpm', 1)}
KINDS = {'line', 'bar', 'scatter', 'dial'}


def catalog(path: Path | None = None):
    with connect(path) as c:
        rows = c.execute('SELECT metric_type, unit, COUNT(*) AS count FROM metric_readings GROUP BY metric_type, unit ORDER BY metric_type').fetchall()
    if not any(r['metric_type'] == 'weight' for r in rows):
        rows = [*rows, {'metric_type': 'weight', 'unit': 'kg', 'count': None}]
    return {'metrics': [{'id': r['metric_type'], 'label': r['metric_type'].replace('_', ' ').capitalize(),
                         'unit': r['unit'], 'count': r['count']} for r in rows]
            + [{'id': 'vo2_cycling', 'label': 'VO₂ max · cycling', 'unit': 'mL/kg/min', 'count': None},
               {'id': 'vo2_running', 'label': 'VO₂ max · running', 'unit': 'mL/kg/min', 'count': None}],
            'activity_fields': [{'id': 'activity_' + key, 'label': 'Activity ' + key.replace('_', ' '), 'unit': unit}
                                for key, (_, unit, _) in ACTIVITY_FIELDS.items()]}


def validate_spec(spec, path=None):
    if not isinstance(spec, dict):
        raise ValueError('Chart must be an object')
    allowed = {'id', 'title', 'metric', 'x_metric', 'kind', 'start', 'end', 'sport', 'size', 'timezone', 'gps_reference_id', 'reference_lines', 'trend_line', 'correlation'}
    if set(spec) - allowed:
        raise ValueError('Unsupported chart fields')
    known = {m['id'] for m in catalog(path)['metrics']} | {'activity_' + f for f in ACTIVITY_FIELDS}
    if spec.get('metric') not in known or (spec.get('x_metric') and spec['x_metric'] not in known):
        raise ValueError('Choose a supported metric')
    if spec.get('kind') not in KINDS or spec.get('size', 'half') not in {'half', 'full'}:
        raise ValueError('Unsupported chart type or size')
    if spec['kind'] == 'scatter' and not spec.get('x_metric'):
        raise ValueError('Scatter plots require an X metric')
    if spec.get('x_metric') and (spec['metric'].startswith('activity_') != spec['x_metric'].startswith('activity_')):
        raise ValueError('Pair health metrics with health metrics, or activity fields with activity fields')
    for key in ('id', 'title', 'sport', 'timezone', 'gps_reference_id'):
        if key in spec and (not isinstance(spec[key], str) or len(spec[key]) > 160):
            raise ValueError(f'Invalid {key}')
    for key in ('start', 'end'):
        if spec.get(key):
            date.fromisoformat(spec[key])
    if spec.get('start') and spec.get('end') and spec['start'] > spec['end']:
        raise ValueError('Start date must be before end date')
    if spec.get('gps_reference_id') and not spec['metric'].startswith('activity_'):
        raise ValueError('GPS-matched charts require an activity metric')
    for key in ('trend_line', 'correlation'):
        if key in spec and not isinstance(spec[key], bool):
            raise ValueError(f'{key} must be a boolean')
    lines = spec.get('reference_lines', [])
    if not isinstance(lines, list) or len(lines) > 4 or any(v != 'mean' and not _valid(v) for v in lines):
        raise ValueError('Use up to four mean or finite numeric reference lines')
    if spec['kind'] == 'dial' and (lines or spec.get('trend_line') or spec.get('correlation')):
        raise ValueError('Analysis overlays require a line, bar or scatter plot')
    timezone_info(spec.get('timezone'))
    return dict(spec)


def _valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _observations(metric, spec, path=None, activity_ids=None):
    observations = []
    excluded = 0
    unit = ''
    with connect(path) as c:
        if metric.startswith('vo2_'):
            sport = 'CYCLING' if metric == 'vo2_cycling' else 'RUNNING'
            rows = c.execute("SELECT id, record_date, payload_json FROM garmin_archive_records WHERE category IN ('max_met_fitness','activity_vo2_max') ORDER BY record_date, id").fetchall()
            seen = set()
            for row in rows:
                p = json.loads(row['payload_json'])
                if not isinstance(p, dict) or str(p.get('sport', '')).upper() != sport:
                    continue
                day = row['record_date'] or p.get('calendarDate')
                value = p.get('vo2MaxValue')
                if not day or not _valid(value) or value <= 0:
                    excluded += 1
                    continue
                if (day, value) in seen:
                    continue
                seen.add((day, value))
                observations.append({'key': day, 'date': day, 'value': value, 'source': 'garmin_export', 'id': row['id']})
            unit = 'mL/kg/min'
        elif metric.startswith('activity_'):
            field, unit, multiplier = ACTIVITY_FIELDS[metric[9:]]
            rows = c.execute('''SELECT a.*, p.value AS average_power, h.value AS average_heart_rate
                FROM activities a
                LEFT JOIN activity_metrics p ON p.activity_id=a.id AND p.metric_type='average_power'
                LEFT JOIN activity_metrics h ON h.activity_id=a.id AND h.metric_type='average_heart_rate'
                ORDER BY a.started_at''').fetchall()
            for row in rows:
                if activity_ids is not None and row['id'] not in activity_ids:
                    continue
                sport = spec.get('sport', 'all')
                activity_type = row['activity_type']
                matches = sport in activity_type
                if sport == 'cycling':
                    matches = 'cycling' in activity_type or 'biking' in activity_type or activity_type == 'virtual_ride'
                if sport != 'all' and not matches:
                    continue
                day = calendar_date(row['started_at'], spec.get('timezone')).isoformat()
                if not _in_period(day, spec):
                    continue
                value = row[field] if field != 'speed' else None
                if field == 'speed':
                    raw = json.loads(row['raw_json'] or '{}')
                    if isinstance(raw, dict):
                        summary = raw.get('summaryDTO') if isinstance(raw.get('summaryDTO'), dict) else raw
                        value = summary.get('averageSpeed')
                        sessions = raw.get('fit_sessions') or []
                        if not _valid(value) and len(sessions) == 1:
                            value = sessions[0].get('enhanced_avg_speed', sessions[0].get('avg_speed'))
                if not _valid(value):
                    excluded += 1
                    continue
                observations.append({'key': row['id'], 'id': row['id'], 'date': day,
                                     'value': value * multiplier, 'source': row['source_name']})
        else:
            rows = c.execute('SELECT * FROM metric_readings WHERE metric_type=? ORDER BY recorded_at,created_at,rowid', (metric,)).fetchall()
            units = {r['unit'] for r in rows}
            if len(units) > 1:
                raise ValueError('This metric contains incompatible units; normalize it before plotting')
            for row in rows:
                day = calendar_date(row['recorded_at'], spec.get('timezone')).isoformat()
                unit = row['unit']
                if _valid(row['value']):
                    observations.append({'key': day, 'date': day, 'value': row['value'], 'source': row['source_name'], 'id': row['id']})
        if metric == 'weight':
            # The ZIP importer preserves historic biometric records separately
            # from live-sync readings. Include their explicitly recorded weights.
            rows = c.execute("SELECT id, record_date, payload_json FROM garmin_archive_records WHERE category='biometrics_history' ORDER BY record_date, id").fetchall()
            seen = {(p['date'], round(p['value'], 6)) for p in observations if p['source'] != 'manual'}
            for row in rows:
                payload = json.loads(row['payload_json'])
                if not isinstance(payload, dict) or payload.get('userSetNullForWeight') is True:
                    continue
                weight = payload.get('weight')
                if not isinstance(weight, dict):
                    continue
                grams = weight.get('weight')
                if not _valid(grams) or grams <= 0:
                    excluded += 1
                    continue
                stamp = weight.get('timestampGMT')
                try:
                    day = calendar_date(stamp + ('Z' if not stamp.endswith('Z') and '+' not in stamp else ''), spec.get('timezone')).isoformat() if isinstance(stamp, str) else row['record_date']
                    if not day:
                        continue
                    date.fromisoformat(day)
                except ValueError:
                    excluded += 1
                    continue
                value = grams / 1000
                key = (day, round(value, 6))
                if key in seen:
                    continue
                seen.add(key)
                observations.append({'key': day, 'date': day, 'value': value, 'source': 'garmin_export', 'id': row['id']})
            unit = 'kg'
            observations.sort(key=lambda p: (p['date'], p['source'] == 'manual'))
    return [p for p in observations if _in_period(p['date'], spec)], unit, excluded


def _in_period(day, spec):
    return (not spec.get('start') or day >= spec['start']) and (not spec.get('end') or day <= spec['end'])


def analyze_points(points, spec):
    """Calculate on the full observation set, before display reduction."""
    values = [p['y'] for p in points]
    result = {'sample_count': len(points), 'reference_lines': [], 'trend': None,
              'pearson_r': None, 'r_squared': None, 'reason': None}
    if not points:
        result['reason'] = 'No recorded observations.'
        return result
    mean_y = math.fsum(values) / len(values)
    for v in spec.get('reference_lines', []):
        result['reference_lines'].append({'label': 'Mean' if v == 'mean' else 'Reference',
                                           'value': mean_y if v == 'mean' else v})
    if not (spec.get('trend_line') or spec.get('correlation')):
        return result
    xs = [float(p['x']) if spec['kind'] == 'scatter' else date.fromisoformat(p['date']).toordinal() for p in points]
    if len(points) < 3:
        result['reason'] = 'At least three paired observations are required for trend and correlation.'
        return result
    mean_x = math.fsum(xs) / len(xs)
    xx = math.fsum((x-mean_x)**2 for x in xs)
    yy = math.fsum((y-mean_y)**2 for y in values)
    xy = math.fsum((x-mean_x)*(y-mean_y) for x,y in zip(xs, values))
    if xx == 0 or yy == 0:
        result['reason'] = 'Trend and correlation are unavailable because an axis is constant.'
        return result
    r = max(-1., min(1., xy / math.sqrt(xx*yy)))
    if spec.get('correlation'):
        result.update(pearson_r=r, r_squared=r*r)
    if spec.get('trend_line'):
        slope = xy / xx
        lo, hi = min(xs), max(xs)
        result['trend'] = {'x_start': lo if spec['kind'] == 'scatter' else date.fromordinal(int(lo)).isoformat(),
                           'x_end': hi if spec['kind'] == 'scatter' else date.fromordinal(int(hi)).isoformat(),
                           'y_start': mean_y + slope*(lo-mean_x), 'y_end': mean_y + slope*(hi-mean_x),
                           'slope': slope, 'r_squared': r*r}
    return result


def chart_data(spec, path=None):
    spec = validate_spec(spec, path)
    if not spec.get('title'):
        def metric_label(metric):
            return ('VO₂ max · ' + metric[4:]) if metric.startswith('vo2_') else metric.replace('_', ' ').capitalize()
        spec['title'] = metric_label(spec['metric'])
        if spec['kind'] == 'scatter':
            spec['title'] += ' vs ' + metric_label(spec['x_metric'])
            if {spec['metric'], spec['x_metric']} == {'activity_speed', 'activity_power'}:
                spec['title'] = 'Power vs speed across rides'
    scope = None
    activity_ids = None
    if spec.get('gps_reference_id'):
        from .ai_tools import find_same_course_rides_tool
        scope = find_same_course_rides_tool({'reference_activity_id': spec['gps_reference_id'],
                                            'timezone': spec.get('timezone'), 'distance_tolerance_percent': None}, path)
        activity_ids = {scope['reference_ride']['id'], *scope['matched_activity_ids']}
    ys, unit, excluded = _observations(spec['metric'], spec, path, activity_ids)
    points = []
    x_unit = 'Date'
    unpaired = 0
    if spec['kind'] == 'scatter':
        xs, x_unit, _ = _observations(spec['x_metric'], spec, path, activity_ids)
        # Last stored reading per date, manual takes precedence, without inventing missing dates.
        xs = sorted(xs, key=lambda p: (p['date'], p['source'] == 'manual'))
        by_key = {p['key']: p for p in xs}
        ys = sorted(ys, key=lambda p: (p['date'], p['source'] == 'manual'))
        ys = list({p['key']: p for p in ys}.values())
        for p in ys:
            x = by_key.get(p['key'])
            if x:
                points.append({**p, 'x': x['value'], 'y': p['value']})
            else:
                unpaired += 1
    else:
        points = [{**p, 'x': p['date'], 'y': p['value']} for p in ys]
    analysis = analyze_points(points, spec)
    count = len(points)
    latest = max(points, key=lambda p: (p['date'], p['source'] == 'manual'), default=None)
    # Preserve latest point and chronological ends when reducing very large histories.
    if count > 2000:
        points = [points[round(i * (count - 1) / 1999)] for i in range(2000)]
    notes = ['Actual recorded observations only; missing days are not filled.']
    if scope:
        reference = scope['reference_ride']
        notes.append(f"GPS course matches for {reference['name']} on {reference['local_date']}: {scope['total_matches']} matching rides plus the reference ride. Uses the entire matching set, not the displayed top ten. {excluded} attempts lack this metric. Matching is recomputed when the chart is refreshed.")
    if spec['metric'] == 'weight' or spec.get('x_metric') == 'weight':
        notes.append('Includes dated weights from Garmin biometric history, live sync and manual entries. Duplicate Garmin values on the same date are shown once; no profile weight is carried forward into missing dates.')
    if spec['kind'] == 'scatter':
        notes.append('Paired by activity ID.' if spec['metric'].startswith('activity_') else 'Paired on the same local date; latest reading per date, manual takes precedence.')
    if spec['metric'] == 'activity_speed' or spec.get('x_metric') == 'activity_speed':
        notes.append('Speed uses the recorded Garmin/FIT mean, not distance divided by elapsed time. Conditions are not adjusted.')
    if spec.get('correlation') or spec.get('trend_line'):
        if analysis['reason']:
            notes.append(analysis['reason'])
        elif analysis['pearson_r'] is not None:
            notes.append(f"Pearson r = {analysis['pearson_r']:.3f}; R² = {analysis['r_squared']:.3f}; n = {analysis['sample_count']}. Association does not establish causation.")
        if analysis['trend']:
            trend = analysis['trend']
            notes.append(f"Linear regression fitted change: {trend['y_end']-trend['y_start']:+.2f} {unit} across the observed X range; R² = {trend['r_squared']:.3f}.")
            if trend['r_squared'] < .1:
                notes.append('The linear fit explains less than 10% of the observed variation; it provides weak evidence of a consistent linear trend.')
        if spec['kind'] != 'scatter':
            notes.append('Trend/correlation compares the metric with calendar time, in days.')
    if count > 2000:
        notes.append(f'Display reduced evenly to 2,000 of {count} observations.')
    return {'spec': spec, 'points': points, 'unit': unit, 'x_unit': x_unit, 'count': count,
            'excluded': excluded, 'unpaired': unpaired, 'latest': latest, 'notes': notes,
            'sources': sorted({p['source'] for p in points}), 'analysis': analysis}


def read_layout(path=None):
    with connect(path) as c:
        row = c.execute('SELECT widgets_json FROM dashboard_widget_layout WHERE id=1').fetchone()
    return json.loads(row[0]) if row else None


def save_layout(widgets, path=None):
    if not isinstance(widgets, list) or len(widgets) > 40:
        raise ValueError('Use at most 40 dashboard graphs')
    validated = [validate_spec(w, path) for w in widgets]
    ids = [w.get('id') for w in validated]
    if any(not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Each widget needs a unique ID')
    with connect(path) as c:
        c.execute('''INSERT INTO dashboard_widget_layout(id,widgets_json) VALUES(1,?)
            ON CONFLICT(id) DO UPDATE SET widgets_json=excluded.widgets_json,updated_at=CURRENT_TIMESTAMP''', (json.dumps(validated),))
    return validated


def add_weight(day, value, unit='kg', path=None):
    date.fromisoformat(day)
    if unit not in {'kg', 'lb'} or not _valid(value):
        raise ValueError('Enter a valid weight and unit')
    kg = value if unit == 'kg' else value * .45359237
    if not 20 <= kg <= 500:
        raise ValueError('Weight must be between 20 and 500 kg')
    identifier = str(uuid.uuid4())
    with connect(path) as c:
        c.execute('''INSERT INTO metric_readings(id,source_name,source_record_id,metric_type,recorded_at,value,unit)
                     VALUES(?, 'manual', ?, 'weight', ?, ?, 'kg')''', (identifier, identifier, day, kg))
    return {'id': identifier, 'date': day, 'value': kg, 'source': 'manual'}


def create_plot_tool(arguments, path=None):
    plots = arguments.get('plots')
    if not isinstance(plots, list) or not 1 <= len(plots) <= 4:
        raise ValueError('Request between one and four plots')
    return {'tool': 'create_plots', 'plots': [chart_data(p, path) for p in plots]}
