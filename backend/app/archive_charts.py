"""Discover numeric archive fields without accepting SQL from callers."""
import re
from .database import connect
from .read_cache import versioned_read


@versioned_read
def archive_metrics(path=None):
    return _discover(path)


def _discover(path):
    with connect(path) as c:
        rows = c.execute("""SELECT DISTINCT r.category,j.fullkey FROM garmin_archive_records r,
            json_tree(r.payload_json) j WHERE r.record_date IS NOT NULL
            AND r.source_name != 'synthetic_fixture' AND j.type IN ('integer','real')
            AND j.fullkey NOT LIKE '%[%]%' ORDER BY r.category,j.fullkey""").fetchall()
    metrics = []
    for category, field in rows:
        # Record IDs and timestamps are retained but are not physiological measurements.
        if re.search(r'(?:timestamp|calendarDate|[._]id\b|Id\b|[._]pk\b)', field):
            continue
        identifier = 'archive:' + category + ':' + field
        label = re.sub(r'([a-z])([A-Z])',r'\1 \2',category+' '+field.lstrip('$.')).replace('_',' ').replace('"','')
        metrics.append({'id': identifier, 'label': label.capitalize(), 'unit': 'source units', 'count': None})
    return metrics
