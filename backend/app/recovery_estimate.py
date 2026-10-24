"""Transparent app recovery estimates, distinct from Garmin observations.

Load-ratio projections are a tuning heuristic, not an injury-risk predictor.
Training Effect ranges supply provisional session demand, not measured EPOC.
"""
import math
from datetime import datetime, timedelta, timezone


def instant(value):
    try:
        value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (ValueError, TypeError):
        return None


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def advance_load(acute, chronic, hours):
    """App EWMA trajectory: seven-day acute, 28-day chronic time constants."""
    days = max(0, hours) / 24
    a = math.exp(-days / 7)
    c = math.exp(-days / 28)
    return acute * a, chronic * c + acute / 3 * (c - a)


def settling_hours(acute, chronic, threshold=1.3):
    if not finite(acute) or not finite(chronic) or chronic <= 0:
        return None
    if acute / chronic <= threshold:
        return 0.
    low, high = 0., 24. * 28
    for _ in range(32):
        mid = (low + high) / 2
        a, c = advance_load(acute, chronic, mid)
        if a / c > threshold:
            low = mid
        else:
            high = mid
    return high


def sleep_adjustment(sleep, series, target):
    """A bounded experimental adjustment; not a clinical conversion to hours."""
    day = sleep['wake_date']
    quality = series.get('sleep_score', {}).get(day)
    if not quality:
        return 0.
    hours = sleep['value'] / 3600
    duration_signal = max(-1., min(1., (hours - target) / 2))
    quality_signal = max(-1., min(1., (quality['value'] - 80) / 20))
    # An excellent score cannot cancel inadequate duration. Adequate duration
    # and excellent quality may earn a small bonus; unresolved debt suppresses it.
    q = min(quality_signal, 1 + duration_signal) if hours >= target else min(duration_signal, quality_signal)
    recent = [r['value'] / 3600 for key, r in series.get('sleep_duration', {}).items()
              if 0 <= (datetime.fromisoformat(day) - datetime.fromisoformat(key)).days <= 2]
    if q > 0 and (len(recent) < 3 or sum(recent) / len(recent) < target - .25):
        q = 0.
    return q


def session_recovery(session, as_of, series, config):
    end = session['end']
    elapsed = (as_of - end).total_seconds() / 3600
    effect = session.get('training_effect')
    load = session.get('load')
    if finite(effect) and effect <= 5:
        # Interpolated TE-based starting ranges; not a peak-EPOC conversion.
        knots = [(0, 0), (1, 4), (2, 12), (3, 24), (4, 36), (5, 60)]
        assigned = 0.
        for (x, y), (xx, yy) in zip(knots, knots[1:]):
            if x <= effect <= xx:
                assigned = y + (effect - x) / (xx - x) * (yy - y)
                break
        method = 'training_effect_heuristic'
    elif finite(load):
        # Explicit fallback, deliberately broad uncertainty reported by caller.
        assigned = min(72., 2 * math.sqrt(load))
        method = 'exercise_load_heuristic'
    else:
        return {'id': session['id'], 'remaining_hours': None, 'reason': 'Missing session load and Training Effect.'}
    adjustments = []
    correction = 0.
    sleeps = sorted(series.get('sleep_duration', {}).values(), key=lambda row: row['wake_date'])
    for sleep in sleeps:
        wake = instant(sleep.get('period_end'))
        if not wake or not end < wake <= as_of:
            continue
        before = max(0., assigned - (wake - end).total_seconds() / 3600 + correction)
        if before <= 0:
            break
        q = sleep_adjustment(sleep, series, config['sleep_target_hours'])
        delta = -q * min(config['sleep_recovery_cap_hours'], config['sleep_recovery_fraction'] * before)
        correction += delta
        if delta:
            adjustments.append({'sleep_id': sleep['id'], 'at': wake.isoformat(), 'hours': round(delta, 3),
                                'projected': sleep.get('source_name') == 'projection'})
    remaining = max(0., assigned - elapsed + correction)
    return {'id': session['id'], 'ended_at': end.isoformat(), 'assigned_hours': round(assigned, 2),
            'elapsed_hours': round(elapsed, 3), 'remaining_hours': round(remaining, 3),
            'method': method, 'sleep_adjustments': adjustments,
            'recovery_until': (as_of + timedelta(hours=remaining)).isoformat()}


def estimate(as_of, zone, sessions, series, coverage, config):
    day = as_of.astimezone(zone).date()
    start = (day - timedelta(days=56)).isoformat()
    covered = bool(coverage.get('coverage_start') and coverage['coverage_start'] <= start
                   and coverage.get('coverage_end', '') >= day.isoformat()
                   and not coverage.get('history_backfill_next'))
    known = [s for s in sessions if s['end'] and s['end'] <= as_of]
    # Recorded Garmin anchors, when available, replace the app's reconstructed
    # load state. Do not combine Garmin acute load with an incompatible CTL.
    anchors = [r for r in coverage.get('load_history', []) if instant(r['observed_at']) <= as_of
               and finite(r.get('acute')) and finite(r.get('chronic'))]
    anchor = max(anchors, key=lambda row: row['observed_at']) if anchors else None
    acute = chronic = 0.
    if anchor:
        at = instant(anchor['observed_at'])
        acute, chronic = anchor['acute'], anchor['chronic']
        additions = sorted((s for s in known if s['end'] > at), key=lambda s: s['end'])
        source = 'Garmin recorded load with app EWMA projection'
    else:
        at = as_of - timedelta(days=84)
        additions = sorted((s for s in known if s['end'] >= at), key=lambda s: s['end'])
        source = 'App reconstructed seven/28-day EWMA load'
    for session in additions:
        acute, chronic = advance_load(acute, chronic, (session['end'] - at).total_seconds() / 3600)
        if finite(session.get('load')):
            acute += session['load']
        at = session['end']
    acute, chronic = advance_load(acute, chronic, (as_of - at).total_seconds() / 3600)
    missing = [s['id'] for s in sessions if s['start'] <= as_of and
               s['start'] >= as_of - timedelta(days=7) and (not s['end'] or s['load'] is None)]
    ratio = acute / chronic if chronic > 0 else None
    # A tiny denominator after prolonged inactivity must not create a precise
    # multi-day countdown. Individual-session demand still applies.
    stable = chronic >= config['chronic_load_floor']
    settling = settling_hours(acute, chronic, config['load_ratio_threshold']) if stable else (0. if acute == 0 else None)
    recent = [s for s in known if s['end'] >= as_of - timedelta(hours=96)]
    demands = [session_recovery(s, as_of, series, config) for s in recent]
    session_hours = max((d['remaining_hours'] for d in demands if d['remaining_hours'] is not None), default=0.)
    # A measured Garmin snapshot is already sleep/stress adjusted. Never modify
    # it again. Only later workouts contribute additional session estimates.
    observed = [r for r in series.get('recovery_time', {}).values()
                if instant(r['recorded_at']) and instant(r['recorded_at']) <= as_of
                and as_of - instant(r['recorded_at']) <= timedelta(hours=24)]
    measured = max(observed, key=lambda r: r['recorded_at']) if observed else None
    if measured:
        at = instant(measured['recorded_at'])
        observed_hours = max(0., measured['value'] / 60 - (as_of - at).total_seconds() / 3600)
        session_hours = max([observed_hours] + [d['remaining_hours'] for d in demands
                           if d['remaining_hours'] is not None and instant(d.get('ended_at')) > at])
    remaining = max(session_hours, settling or 0.)
    unadjusted = max([settling or 0.] + [max(0., d.get('assigned_hours', 0.) - d.get('elapsed_hours', 0.))
                                       for d in demands])
    return {'as_of': as_of.isoformat(), 'remaining_hours': round(remaining, 2),
            'range_hours': {'low': round(max(0., remaining * .75), 1), 'high': round(remaining * 1.25, 1)},
            'session_remaining_hours': round(session_hours, 2), 'unadjusted_remaining_hours': round(unadjusted, 2),
            'load_settling_hours': round(settling, 2) if settling is not None else None,
            'acute': round(acute, 3), 'chronic': round(chronic, 3), 'ratio': round(ratio, 3) if ratio is not None else None,
            'ratio_threshold': config['load_ratio_threshold'], 'baseline_days': 28,
            'load_source': source, 'stable_baseline': stable, 'coverage_complete': covered and not missing,
            'missing_activity_ids': missing, 'sessions': demands,
            'source': 'Garmin snapshot plus app load projection' if measured else 'App estimate',
            'garmin_observation': {'id': measured['id'], 'recorded_at': measured['recorded_at'],
                                   'minutes': measured['value']} if measured else None,
            'estimated': True, 'range_method': 'Heuristic ±25% sensitivity range; not a calibrated confidence interval.',
            'label': 'Estimated recovery demand / time until load settles',
            'limitations': ['Preparation for hard training, not proof of full recovery.',
                            'App decay, session-hour mappings and sleep adjustments are provisional.',
                            'Low chronic load leaves ratio settling unavailable; session estimates remain visible.']}
