"""Versioned, past-only readiness estimate. Model parameters are provisional."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from .database import connect
from .time_utils import timezone_info

FORMULA_VERSION = 'readiness-v1'
DEFAULTS = {
    'sleep_target_hours': 8.0, 'load_half_life_hours': 36.0,
    'autonomic_weight': 40.0, 'sleep_weight': 35.0, 'workload_weight': 25.0,
    'hrv_scale_floor': .05, 'rhr_scale_floor': 2.0,
    'baseline_days': 28, 'baseline_min_nights': 21,
    'load_reference_days': 56, 'load_min_mornings': 28,
    'deviation_tolerance': .5, 'morning_hour': 8,
}
LIMITS = {
    'sleep_target_hours': (6, 10), 'load_half_life_hours': (24, 48),
    'autonomic_weight': (20, 60), 'sleep_weight': (20, 60), 'workload_weight': (10, 40),
    'hrv_scale_floor': (.02, .2), 'rhr_scale_floor': (1, 5),
    'baseline_days': (21, 42), 'baseline_min_nights': (14, 35),
    'load_reference_days': (28, 84), 'load_min_mornings': (21, 56),
    'deviation_tolerance': (.25, 1), 'morning_hour': (5, 12),
}
INTEGER_KEYS = {'baseline_days', 'baseline_min_nights', 'load_reference_days', 'load_min_mornings', 'morning_hour'}
CAUTION = 'Prototype estimate for endurance training. A high result means few measured adverse signals; it does not prove recovery or change a workout. Consider how you feel.'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def parameters(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Unknown readiness parameter')
    result = {**DEFAULTS, **values}
    for key, value in result.items():
        low, high = LIMITS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}')
        if key in INTEGER_KEYS and type(value) is not int:
            raise ValueError(f'{key} must be an integer')
    if abs(sum(result[k] for k in ('autonomic_weight', 'sleep_weight', 'workload_weight')) - 100) > 1e-8:
        raise ValueError('Readiness weights must total 100')
    if result['baseline_min_nights'] > result['baseline_days'] or result['load_min_mornings'] > result['load_reference_days']:
        raise ValueError('Minimum history cannot exceed its reference window')
    return result


def _config(connection, values):
    payload = canonical(parameters(values))
    version = FORMULA_VERSION + '-' + hashlib.sha256(payload.encode()).hexdigest()[:16]
    connection.execute('INSERT OR IGNORE INTO readiness_configs(version,formula_version,parameters_json) VALUES (?,?,?)', (version, FORMULA_VERSION, payload))
    return version


def get_readiness_settings(path: Path | None = None):
    with connect(path) as c:
        version = _config(c, {})
        c.execute('INSERT OR IGNORE INTO readiness_settings(id,config_version) VALUES (1,?)', (version,))
        row = c.execute('SELECT r.* FROM readiness_configs r JOIN readiness_settings s ON s.config_version=r.version WHERE s.id=1').fetchone()
        return {'config_version': row['version'], 'formula_version': row['formula_version'], 'parameters': json.loads(row['parameters_json']), 'caution': CAUTION}


def save_readiness_settings(values, path: Path | None = None):
    validated = parameters(values)
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        version = _config(c, validated)
        c.execute('INSERT INTO readiness_settings(id,config_version) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET config_version=excluded.config_version', (version,))
    return get_readiness_settings(path)


def stamp(value):
    if not value or len(str(value)) <= 10:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _positive(value, allow_zero=False):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (value >= 0 if allow_zero else value > 0)


def robust(values, floor, minimum):
    if len(values) < minimum:
        return None
    center = median(values)
    return {'center': center, 'scale': max(floor, 1.4826 * median(abs(v-center) for v in values)), 'count': len(values)}


def clip(value):
    return max(0., min(1., value))


def band(value):
    return 'lower' if value < 50 else 'mixed' if value < 80 else 'higher'


def _series(rows, zone):
    result = {}
    units = {'hrv_last_night_average': 'ms', 'resting_heart_rate': 'bpm', 'sleep_duration': 's', 'sleep_score': 'score'}
    for row in rows:
        kind = row['metric_type']
        if kind not in units or row.get('unit') != units[kind]:
            continue
        day = str(row['recorded_at'])[:10]
        ended = stamp(row.get('period_end'))
        if kind.startswith('sleep_') and ended:
            day = ended.astimezone(zone).date().isoformat()
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        if not _positive(row['value'], allow_zero=kind == 'sleep_score'):
            continue
        if kind == 'sleep_score' and row['value'] > 100:
            continue
        if kind == 'sleep_duration' and row['value'] > 86400:
            continue
        # Deterministically prefer the current live stream over overlapping archive records.
        priority = (row['source_name'] == 'garmin_connect', row.get('source_updated_at') or '', row['id'])
        old = result.setdefault(kind, {}).get(day)
        if old is None or priority > old['_priority']:
            result[kind][day] = {**row, 'wake_date': day, '_priority': priority}
    return result


def _sessions(rows):
    result = []
    for row in rows:
        start = stamp(row['started_at'])
        if not start:
            continue
        payload = json.loads(row.get('raw_json') or '{}')
        end = stamp(row.get('ended_at'))
        method = 'recorded_end'
        if not end:
            fits = [stamp(s.get('timestamp')) for s in payload.get('fit_sessions', [])]
            fits = [v for v in fits if v and v >= start]
            if fits:
                end, method = max(fits), 'fit_session_end'
        if not end:
            dto = payload.get('summaryDTO') or payload
            elapsed = dto.get('elapsedDuration')
            if _positive(elapsed):
                end, method = start + timedelta(seconds=elapsed), 'garmin_elapsed_duration'
        if not end:
            method = 'end_unavailable'
        valid_load = _positive(row.get('load'), allow_zero=True)
        result.append({'id': row['id'], 'start': start, 'end': end if end and end >= start else None,
                       'load': row.get('load') if valid_load else None, 'end_method': method,
                       'load_method': row.get('load_method'), 'source_field': row.get('source_field')})
    return result


def _exposure(sessions, cutoff, half_life, coverage, zone):
    beginning = cutoff - timedelta(days=7)
    covered = bool(coverage.get('coverage_start') and coverage.get('coverage_end') and
                   coverage['coverage_start'] <= beginning.astimezone(zone).date().isoformat() and
                   coverage['coverage_end'] >= cutoff.astimezone(zone).date().isoformat() and
                   not coverage.get('history_backfill_next'))
    total = 0.
    selected, missing = [], []
    for session in sessions:
        if session['start'] >= cutoff:
            continue
        end = session['end']
        if end is None:
            if session['start'] >= beginning:
                missing.append(session['id'])
            continue
        if end >= cutoff or end < beginning:
            continue
        selected.append(session)
        if session['load'] is None:
            missing.append(session['id'])
        else:
            total += session['load'] * 2 ** (-(cutoff-end).total_seconds()/3600/half_life)
    return total, covered and not missing, selected, missing


def calculate(day, zone_name, rows, activity_rows, coverage, config, *, now=None):
    """Pure calculation: dates after the observation never enter references."""
    zone = ZoneInfo(zone_name)
    p = parameters(config)
    series = _series(rows, zone)
    sessions = _sessions(activity_rows)
    key = day.isoformat()
    sleep = series.get('sleep_duration', {}).get(key)
    wake = stamp(sleep.get('period_end')) if sleep else None
    cutoff = datetime.combine(day, time(p['morning_hour']), zone).astimezone(timezone.utc)
    if wake and wake > cutoff:
        cutoff = wake
    warnings = ['rhr_previous_day_context', 'historical_estimate_uses_current_corrected_records']
    inputs = {}

    def reading(kind, offset=0):
        return series.get(kind, {}).get((day-timedelta(days=offset)).isoformat())

    def evidence(row):
        if not row:
            return None
        return {k: row.get(k) for k in ('id','value','unit','wake_date','source_name','period_start','period_end')}

    h = reading('hrv_last_night_average')
    r = reading('resting_heart_rate', 1)  # completed day only; never today's whole-day RHR
    q = reading('sleep_score')
    inputs.update(hrv=evidence(h), rhr_previous_day=evidence(r), sleep=evidence(sleep), sleep_score=evidence(q))
    baseline_start = day-timedelta(days=p['baseline_days']+2)
    baseline_end = day-timedelta(days=3)
    h_values, r_values, baseline_ids = [], [], []
    for offset in range(3, p['baseline_days']+3):
        for kind, values, log in [('hrv_last_night_average',h_values,True), ('resting_heart_rate',r_values,False)]:
            row = reading(kind, offset)
            if row:
                values.append(math.log(row['value']) if log else row['value'])
                baseline_ids.append(row['id'])
    hb = robust(h_values, p['hrv_scale_floor'], p['baseline_min_nights'])
    rb = robust(r_values, p['rhr_scale_floor'], p['baseline_min_nights'])
    recent_h = [reading('hrv_last_night_average', i) for i in range(3)]
    recent_h = [row for row in recent_h if row]
    recent_s = [reading('sleep_duration', i) for i in range(3)]
    recent_s = [row for row in recent_s if row]
    inputs['recent_hrv'] = [evidence(row) for row in recent_h]
    inputs['recent_sleep'] = [evidence(row) for row in recent_s]
    hp = rp = dp = qp = None
    zh = zr = None
    if h and hb and len(recent_h) >= 2:
        zh = min((math.log(h['value'])-hb['center'])/hb['scale'],
                 (sum(math.log(row['value']) for row in recent_h)/len(recent_h)-hb['center'])/hb['scale'])
        hp = clip((-zh-p['deviation_tolerance'])/2)
        if (math.log(h['value'])-hb['center'])/hb['scale'] > 2.5:
            warnings.append('unusually_high_hrv_no_bonus')
    else:
        warnings.append('hrv_missing_or_insufficient_baseline')
    if r and rb:
        zr = (r['value']-rb['center'])/rb['scale']
        rp = clip((zr-p['deviation_tolerance'])/2)
    else:
        warnings.append('rhr_missing_or_insufficient_baseline')
    sleep_complete = bool(sleep and wake and wake <= cutoff)
    if sleep_complete:
        shortfall = max(p['sleep_target_hours']-sleep['value']/3600,
                        p['sleep_target_hours']-sum(row['value'] for row in recent_s)/len(recent_s)/3600)
        dp = clip(shortfall/3)
    else:
        warnings.append('completed_sleep_missing')
    if q and sleep_complete:
        qp = clip((80-q['value'])/50)
    if not q:
        warnings.append('sleep_score_missing')
    if len(recent_s) < 2:
        warnings.append('sleep_trend_insufficient')
    exposure, covered, selected, missing = _exposure(sessions, cutoff, p['load_half_life_hours'], coverage, zone)
    reference, reference_ids = [], set()
    for offset in range(1,p['load_reference_days']+1):
        morning = datetime.combine(day-timedelta(days=offset),time(p['morning_hour']),zone).astimezone(timezone.utc)
        value, complete, used, _ = _exposure(sessions, morning, p['load_half_life_hours'], coverage, zone)
        if complete:
            reference.append(value)
            reference_ids.update(s['id'] for s in used)
    percentile = None
    wp = None
    if covered and len(reference) >= p['load_min_mornings']:
        tied = [math.isclose(v,exposure,rel_tol=1e-10,abs_tol=1e-10) for v in reference]
        percentile = (sum(v < exposure and not tie for v,tie in zip(reference,tied)) + .5*sum(tied))/len(reference)
        wp = clip((percentile-.7)/.3)
    else:
        warnings.append('workload_coverage_or_reference_incomplete')
    groups = []

    def group(name, weight, values, extra):
        observed = [v for v in values if v is not None]
        minimum = max(observed, default=0.)*weight
        complete = all(v is not None for v in values)
        maximum = minimum if complete else weight
        groups.append({'name':name,'budget':weight,'penalty_min':round(minimum,2),'penalty_max':round(maximum,2),'complete':complete,**extra})

    group('autonomic',p['autonomic_weight'],[hp,rp], {'hrv_z':zh,'rhr_z':zr,'hrv_baseline':hb,'rhr_baseline':rb,
        'baseline_start':baseline_start.isoformat(),'baseline_end':baseline_end.isoformat(),'baseline_input_ids':sorted(baseline_ids)})
    # A missing short sleep trend leaves the duration portion uncertain.
    group('sleep',p['sleep_weight'],[dp,qp,dp if len(recent_s)>=2 else None], {'target_hours':p['sleep_target_hours'],'recent_nights':len(recent_s)})
    group('workload',p['workload_weight'],[wp], {'exposure':round(exposure,3),'percentile':percentile,'reference_mornings':len(reference),
        'half_life_hours':p['load_half_life_hours'],'coverage':coverage,'missing_activity_ids':missing,'reference_activity_ids':sorted(reference_ids),
        'sessions':[{'id':s['id'],'ended_at':s['end'].isoformat(),'load':s['load'],'load_method':s['load_method'],'source_field':s['source_field'],'end_method':s['end_method'],
                     'hours_since_end':round((cutoff-s['end']).total_seconds()/3600,2)} for s in selected]})
    lower = max(0,round(100-sum(g['penalty_max'] for g in groups)))
    upper = min(100,round(100-sum(g['penalty_min'] for g in groups)))
    ready = all(g['complete'] for g in groups)
    status = 'complete' if ready else 'partial'
    if not sleep_complete or not hb:
        status = 'insufficient_data'
    if now and cutoff > now.astimezone(timezone.utc):
        status = 'awaiting_morning'
        warnings.append('morning_observation_not_finished')
    return {'date':key,'timezone':zone_name,'cutoff':cutoff.isoformat(),'formula_version':FORMULA_VERSION,
            'status':status,'score':upper if status=='complete' else None,
            'score_range':{'low':lower,'high':upper} if status not in {'insufficient_data','awaiting_morning'} else None,
            'band':band(upper) if status=='complete' else None,
            'data_quality':'complete' if status=='complete' else 'limited', 'inputs':inputs,'groups':groups,
            'warnings':warnings,'parameters':p,'caution':CAUTION}


def _load(c, start, end):
    rows = [dict(r) for r in c.execute('''SELECT * FROM metric_readings WHERE metric_type IN
        ('hrv_last_night_average','resting_heart_rate','sleep_duration','sleep_score') AND substr(recorded_at,1,10) BETWEEN ? AND ?''',
        ((start-timedelta(days=2)).isoformat(),(end+timedelta(days=1)).isoformat()))]
    activities = [dict(r) for r in c.execute('''SELECT a.*,m.value AS load,m.source_method AS load_method,m.source_field FROM activities a
        LEFT JOIN activity_metrics m ON m.activity_id=a.id AND m.metric_type='exercise_load' AND m.unit='garmin_load'
        WHERE a.deleted_at IS NULL AND substr(a.started_at,1,10) BETWEEN ? AND ?''',
        ((start-timedelta(days=2)).isoformat(),(end+timedelta(days=1)).isoformat()))]
    checkpoint = c.execute("SELECT coverage_start,coverage_end,history_backfill_next FROM sync_checkpoints WHERE data_type='activities'").fetchone()
    return rows, activities, dict(checkpoint) if checkpoint else {}


def readiness_history(end_date=None, days=14, timezone_name='UTC', path: Path | None = None, config_version=None, now=None):
    timezone_info(timezone_name)
    if type(days) is not int or not 1 <= days <= 90:
        raise ValueError('Readiness history must contain 1–90 days')
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(timezone_name)).date()
    end_date = end_date or today
    if end_date > today:
        raise ValueError('Readiness cannot be calculated for a future date')
    settings = get_readiness_settings(path)
    version = config_version or settings['config_version']
    start = end_date-timedelta(days=days-1)
    with connect(path) as c:
        c.execute('BEGIN')
        row = c.execute('SELECT * FROM readiness_configs WHERE version=?',(version,)).fetchone()
        if row is None or row['formula_version'] != FORMULA_VERSION:
            raise ValueError('Unknown or unsupported readiness formula version')
        config = json.loads(row['parameters_json'])
        lookback = max(config['baseline_days']+3,config['load_reference_days']+7)
        rows,activities,coverage = _load(c,start-timedelta(days=lookback),end_date)
    results=[]
    for offset in range(days):
        day = start+timedelta(days=offset)
        result = calculate(day,timezone_name,rows,activities,coverage,config,now=now)
        result['config_version']=version
        if result['status']=='complete':
            variants=[]
            for altered in [{'load_half_life_hours':24.}, {'load_half_life_hours':48.},
                            {'sleep_target_hours':max(6.,config['sleep_target_hours']-.5)},
                            {'sleep_target_hours':min(10.,config['sleep_target_hours']+.5)},
                            {'autonomic_weight':35.,'sleep_weight':35.,'workload_weight':30.},
                            {'autonomic_weight':45.,'sleep_weight':30.,'workload_weight':25.},
                            {'deviation_tolerance':.25},{'deviation_tolerance':.75}]:
                alternative=calculate(day,timezone_name,rows,activities,coverage,{**config,**altered},now=now)
                if alternative['score'] is not None:
                    variants.append(alternative['score'])
            result['sensitivity']={'low':min(variants+[result['score']]),'high':max(variants+[result['score']]),
                                   'band_changes':any(band(v)!=result['band'] for v in variants)}
            if result['sensitivity']['band_changes']:
                result['warnings'].append('band_sensitive_to_provisional_parameters')
        results.append(result)
    # Persist only after calculation; do not hold a write lock during sensitivity checks.
    with connect(path) as c:
        c.execute('BEGIN IMMEDIATE')
        for result in results:
            digest=hashlib.sha256(canonical(result).encode()).hexdigest()
            c.execute('''INSERT OR IGNORE INTO readiness_calculations(calendar_date,timezone,config_version,input_hash,result_json)
                VALUES (?,?,?,?,?)''',(result['date'],timezone_name,version,digest,canonical(result)))
            saved=c.execute('SELECT id,calculated_at FROM readiness_calculations WHERE calendar_date=? AND timezone=? AND config_version=? AND input_hash=?',
                            (result['date'],timezone_name,version,digest)).fetchone()
            result.update(calculation_id=saved['id'],calculated_at=saved['calculated_at'])
    return {'latest':results[-1], 'trend':results,'settings':settings,'reconstruction':'Past-only references using currently stored corrected observations; not a record of what was available at that time.'}


def get_readiness_tool(arguments, path=None):
    day = date.fromisoformat(arguments['date']) if arguments.get('date') else None
    result = readiness_history(day,1,arguments.get('timezone') or 'UTC',path)
    return {'tool':'get_training_readiness',**result['latest'],'reconstruction':result['reconstruction'],'advisory_only':True}
