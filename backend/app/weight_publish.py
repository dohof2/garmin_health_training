"""Explicit publication of one saved manual weight, with no blind write retries."""
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import connect
from .garmin_connection import load_client
from .sync import SyncConnectionRequired


def publish(reading_id, timezone, path=None, client_factory=None, now=None):
    try:
        zone = ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('Choose a valid timezone') from None
    current = (now or datetime.now(UTC)).astimezone(zone)
    with connect(path) as c:
        row = c.execute("SELECT * FROM metric_readings WHERE id=? AND source_name='manual' AND metric_type='weight'", (reading_id,)).fetchone()
        if row is None:
            raise ValueError('Saved manual weight was not found')
        day = datetime.fromisoformat(row['recorded_at']).date()
        if day > current.date():
            raise ValueError('Future weight measurements cannot be sent to Garmin')
        existing = c.execute('SELECT status FROM weight_publications WHERE reading_id=?', (reading_id,)).fetchone()
        if existing and existing['status'] in {'sent', 'sending', 'unknown'}:
            return result(existing['status'])
    try:
        client = (client_factory or load_client)(path)
    except SyncConnectionRequired:
        return result('not_connected')
    except Exception:
        return result('unavailable')
    stamp = current if day == current.date() else datetime.combine(day, time(12), zone)
    local_stamp = stamp.strftime('%Y-%m-%dT%H:%M:%S.000')
    utc_stamp = stamp.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.000')
    # Claim before the network write, so concurrent requests never publish twice.
    with connect(path) as c:
        inserted = c.execute("INSERT OR IGNORE INTO weight_publications(reading_id,status,local_timestamp,utc_timestamp) VALUES(?,'sending',?,?)", (reading_id, local_stamp, utc_stamp)).rowcount
        if not inserted:
            return result(c.execute('SELECT status FROM weight_publications WHERE reading_id=?', (reading_id,)).fetchone()['status'])
    try:
        # The library timestamp helper converts to the host timezone. Send the
        # documented payload directly to preserve the browser's measurement date.
        response = client.client.post('connectapi', f'{client.garmin_connect_weight_url}/user-weight', json={
            'dateTimestamp': local_stamp, 'gmtTimestamp': utc_stamp,
            'unitKey': 'kg', 'sourceType': 'MANUAL', 'value': row['value'],
        })
        response.raise_for_status()
        status = 'sent' if response.status_code in {200, 201, 204} else 'unknown'
    except Exception:
        # Garmin may have accepted a write whose response was lost. Never retry it.
        status = 'unknown'
    with connect(path) as c:
        c.execute('UPDATE weight_publications SET status=?,updated_at=CURRENT_TIMESTAMP WHERE reading_id=?', (status, reading_id))
    return result(status)


def result(status):
    messages = {
        'sent': 'Saved locally and sent to Garmin Connect.',
        'not_connected': 'Saved locally. Sign in to Garmin Connect before sending.',
        'unavailable': 'Saved locally. Garmin is unavailable; nothing was sent.',
        'sending': 'Saved locally. Garmin delivery is unconfirmed; check Garmin Connect before sending another copy.',
        'unknown': 'Saved locally. Garmin delivery is unconfirmed; check Garmin Connect before sending another copy.',
    }
    return {'status': status, 'message': messages[status]}
