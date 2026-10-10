"""Preserve source summaries and normalize explicit activity/FIT scalar fields."""
from __future__ import annotations

import json
import math
from datetime import date, datetime

PRIVATE_KEYS = {'userprofileid', 'userprofilepk', 'profileid', 'ownerid',
                'ownerdisplayname', 'deviceid', 'serialnumber', 'primarytrainingdevice'}


def source_payload(value):
    if isinstance(value, dict):
        return {str(k): source_payload(v) for k, v in value.items()
                if str(k).lower().replace('_', '') not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [source_payload(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def encoded(value):
    return json.dumps(source_payload(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


SUMMARY_FIELDS = {
    'activityTrainingLoad': ('exercise_load', 'garmin_load'),
    'aerobicTrainingEffect': ('aerobic_training_effect', 'score'),
    'trainingEffect': ('aerobic_training_effect', 'score'),
    'anaerobicTrainingEffect': ('anaerobic_training_effect', 'score'),
    'trainingStressScore': ('training_stress_score', 'score'),
    'intensityFactor': ('intensity_factor', 'ratio'),
    'normalizedPower': ('normalized_power', 'W'),
    'averagePower': ('average_power', 'W'),
    'maxPower': ('maximum_power', 'W'),
    'averageHR': ('average_heart_rate', 'bpm'),
    'maxHR': ('maximum_heart_rate', 'bpm'),
    'totalWork': ('total_work', 'J'),
}
FIT_FIELDS = {
    'training_load_peak': ('exercise_load', 'garmin_load'),
    'total_training_effect': ('aerobic_training_effect', 'score'),
    'total_anaerobic_training_effect': ('anaerobic_training_effect', 'score'),
    'training_stress_score': ('training_stress_score', 'score'),
    'intensity_factor': ('intensity_factor', 'ratio'),
    'normalized_power': ('normalized_power', 'W'),
    'avg_power': ('average_power', 'W'),
    'max_power': ('maximum_power', 'W'),
    'avg_heart_rate': ('average_heart_rate', 'bpm'),
    'max_heart_rate': ('maximum_heart_rate', 'bpm'),
    'total_work': ('total_work', 'J'),
}


def normalize_activity_metrics(connection, activity_id: str, payload: dict, method='garmin_summary'):
    values = dict(payload)
    if isinstance(payload.get('summaryDTO'), dict):
        values.update(payload['summaryDTO'])
    fields = FIT_FIELDS if method == 'fit_session' else SUMMARY_FIELDS
    saved = 0
    for field, (metric, unit) in fields.items():
        value = values.get(field)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            continue
        connection.execute('''INSERT INTO activity_metrics(activity_id, metric_type, value, unit, source_method, source_field)
            VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(activity_id, metric_type) DO UPDATE SET
            value=excluded.value, unit=excluded.unit, source_method=excluded.source_method,
            source_field=excluded.source_field, updated_at=CURRENT_TIMESTAMP
            WHERE activity_metrics.source_method='fit_session' OR excluded.source_method!='fit_session' ''',
            (activity_id, metric, value, unit, method, field))
        saved += 1
    return saved


def preserve_fit_summary(connection, activity_id: str, messages: dict):
    sessions = messages.get('session_mesgs') or []
    current = connection.execute('SELECT raw_json FROM activities WHERE id=?', (activity_id,)).fetchone()
    payload = json.loads(current['raw_json'] or '{}')
    payload['fit_sessions'] = source_payload(sessions)
    # Do not silently assign the first session's load to an entire multisport activity.
    if len(sessions) == 1:
        normalize_activity_metrics(connection, activity_id, sessions[0], 'fit_session')
    connection.execute('UPDATE activities SET raw_json=?, fit_detail_version=1 WHERE id=?', (encoded(payload), activity_id))
