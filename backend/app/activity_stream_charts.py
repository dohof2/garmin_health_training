"""Read-only overlays of recorded samples, aligned to each activity's start."""
from __future__ import annotations

import math
import statistics
from .database import connect
from .intervals import stamp, MAX_GAP
from .time_utils import calendar_date

STREAM_FIELDS = {
    'stream:power': ('power_watts', 'Power', 'W', 1),
    'stream:heart_rate': ('heart_rate_bpm', 'Heart rate', 'bpm', 1),
    'stream:cadence': ('cadence_rpm', 'Cadence', 'rpm', 1),
    'stream:speed': ('speed_mps', 'Speed', 'km/h', 3.6),
}
SERIES_COLOURS = [('blue','#356799'), ('orange','#d16b22'), ('teal','#27836b'), ('purple','#8258b6'), ('rose','#ba4768'), ('olive','#767221'), ('cyan','#397f97'), ('brown','#6c5060')]
DISPLAY_TARGET = 2000


def validate(spec):
    identifiers = spec.get('activity_ids')
    if identifiers is not None and (not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 8
            or any(not isinstance(i, str) or not i or len(i) > 160 for i in identifiers)
            or len(set(identifiers)) != len(identifiers)):
        raise ValueError('Choose one to eight distinct activity IDs.')
    if identifiers is None and not (spec.get('start') and spec.get('end')):
        raise ValueError('Choose activity IDs or a start and end date for an elapsed-time plot.')
    if spec['kind'] != 'line' or spec.get('x_metric', 'elapsed_time') != 'elapsed_time':
        raise ValueError('Recorded activity overlays require a line chart with elapsed_time on the X axis.')
    if any(spec.get(key) for key in ('gps_reference_id', 'aggregation', 'rolling_days', 'trend_line', 'correlation', 'reference_lines')):
        raise ValueError('Recorded activity overlays preserve separate raw traces; summary analysis and GPS matching are not applied.')
    return {**spec, 'x_metric': 'elapsed_time'}


def reduce_segments(segments):
    """Keep endpoints and each bucket's extrema; never join across missing data."""
    count = sum(len(segment) for segment in segments)
    if count <= DISPLAY_TARGET:
        return [point for segment in segments for point in segment]
    bucket_size = max(1, math.ceil(count / (DISPLAY_TARGET / 2)))
    displayed = []
    for segment in segments:
        chosen = {0, len(segment) - 1}
        for start in range(0, len(segment), bucket_size):
            indices = range(start, min(len(segment), start + bucket_size))
            chosen.add(min(indices, key=lambda i: segment[i]['y']))
            chosen.add(max(indices, key=lambda i: segment[i]['y']))
        displayed.extend(segment[i] for i in sorted(chosen))
    # Bound even highly fragmented recordings. Keep original segment IDs so
    # omitted short segments cannot cause interpolation across a data gap.
    if len(displayed) > DISPLAY_TARGET:
        bucket_size = math.ceil(len(displayed) / (DISPLAY_TARGET // 2 - 1))
        chosen = {0, len(displayed) - 1}
        for start in range(0, len(displayed), bucket_size):
            indices = range(start, min(len(displayed), start + bucket_size))
            chosen.add(min(indices, key=lambda i: displayed[i]['y']))
            chosen.add(max(indices, key=lambda i: displayed[i]['y']))
        displayed = [displayed[i] for i in sorted(chosen)]
    return displayed


def chart(spec, path=None):
    field, label, unit, multiplier = STREAM_FIELDS[spec['metric']]
    identifiers = spec.get('activity_ids')
    with connect(path) as c:
        if identifiers:
            placeholders = ','.join('?' for _ in identifiers)
            rows = c.execute(f"SELECT * FROM activities WHERE id IN ({placeholders}) AND deleted_at IS NULL AND source_name != 'synthetic_fixture'", identifiers).fetchall()
            by_id = {r['id']: r for r in rows}
            if any(i not in by_id for i in identifiers):
                raise ValueError('A selected activity is unavailable, removed or synthetic. Choose recorded activities.')
            activities = [by_id[i] for i in identifiers]
        else:
            activities = c.execute("SELECT * FROM activities WHERE deleted_at IS NULL AND source_name != 'synthetic_fixture' ORDER BY started_at,id").fetchall()
        selected = []
        for activity in activities:
            day = calendar_date(activity['started_at'], spec.get('timezone')).isoformat()
            in_period = (not spec.get('start') or day >= spec['start']) and (not spec.get('end') or day <= spec['end'])
            sport = spec.get('sport', 'all')
            kind = activity['activity_type']
            matches = sport == 'all' or sport == kind or (sport == 'cycling' and kind in ('cycling','gravel_cycling','indoor_cycling','mountain_biking','virtual_ride'))
            if in_period and matches:
                selected.append((activity, day))
            elif identifiers:
                raise ValueError('A selected activity is outside the requested date or sport filter.')
        if len(selected) > 8:
            raise ValueError(f'{len(selected)} activities match. Choose up to eight activity IDs or narrow the dates; no activities were silently omitted.')
        points, series, notes = [], [], []
        count = excluded = 0
        for activity, day in selected:
            origin = stamp(activity['started_at'])
            samples = c.execute(f'SELECT recorded_at,{field} AS value FROM activity_samples WHERE activity_id=? ORDER BY recorded_at,rowid', (activity['id'],)).fetchall()
            segments, values = [], []
            previous = None
            break_line = True
            missing = 0
            gaps = 0
            for sample in samples:
                value = sample['value']
                try:
                    elapsed = stamp(sample['recorded_at']) - origin
                except (ValueError, TypeError):
                    missing += 1; break_line = True; continue
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0 or elapsed < 0:
                    missing += 1; break_line = True; continue
                if previous is not None and (elapsed - previous > MAX_GAP or elapsed <= previous):
                    break_line = True
                if break_line:
                    if segments: gaps += 1
                    segments.append([])
                point = {'x': elapsed, 'y': value * multiplier, 'date': day, 'source': activity['source_name'],
                         'id': activity['id'], 'series_id': activity['id'], 'segment': len(segments) - 1,
                         'recorded_at': sample['recorded_at']}
                segments[-1].append(point)
                values.append(point['y'])
                previous = elapsed; break_line = False
            displayed = reduce_segments(segments)
            points.extend(displayed)
            name = activity['name'] or activity['activity_type'].replace('_', ' ').title()
            colour_name, colour = SERIES_COLOURS[len(series)]
            series.append({'id': activity['id'], 'label': name, 'color': colour, 'color_name': colour_name, 'started_at': activity['started_at'], 'date': day,
                           'source': activity['source_name'], 'count': len(values), 'display_count': len(displayed),
                           'missing_samples': missing, 'gap_count': gaps,
                           'mean': statistics.fmean(values) if values else None,
                           'minimum': min(values) if values else None, 'maximum': max(values) if values else None,
                           'evidence_url': f"/api/activities/{activity['id']}"})
            count += len(values); excluded += missing
            if not values: notes.append(f'{name}: no recorded {label.lower()} samples; no trace can be drawn.')
            if len(displayed) < len(values):
                notes.append(f'{name}: display reduced from {len(values)} to {len(displayed)} recorded points using bucket minima/maxima and endpoints without joining gap boundaries; some short segments may be omitted in fragmented recordings. Export contains displayed points.')
    normalized = {**spec, 'activity_ids': [a['id'] for a, _ in selected]} if selected else dict(spec)
    normalized.setdefault('title', f'{label} by elapsed time · activity comparison')
    return {'spec': normalized, 'points': points, 'series': series, 'unit': unit, 'x_unit': 's', 'count': count,
            'excluded': excluded, 'unpaired': 0, 'latest': max(points, key=lambda p: p['recorded_at'], default=None),
            'sources': sorted({s['source'] for s in series}),
            'notes': ['Each activity starts at elapsed 0 seconds on the same axes; elapsed time includes pauses. No GPS matching or resampling is performed.',
                      f'Only recorded samples are plotted. Zero values are retained; missing values and gaps over {MAX_GAP:g} seconds break the line.',
                      'Legend colours identify separate recordings. Similar timings do not prove two activities are the same session. Per-trace means are sample means, not time-weighted averages.', *notes]}
