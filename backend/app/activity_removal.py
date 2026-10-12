"""Recoverable app-only removal. Never delete Garmin account records or FIT data."""
from datetime import datetime, timezone
from .database import connect


def set_removed(identifier,removed,path=None):
    if type(removed) is not bool:
        raise ValueError('Removal must be true or false')
    with connect(path) as c:
        row=c.execute("SELECT id,deleted_at,locally_removed_at FROM activities WHERE id=? AND source_name!='synthetic_fixture'",(identifier,)).fetchone()
        if row is None:raise LookupError('Activity not found')
        if removed:
            if row['deleted_at'] and not row['locally_removed_at']:
                raise ValueError('This activity is already unavailable from its source.')
            stamp=row['locally_removed_at'] or datetime.now(timezone.utc).isoformat()
            c.execute('UPDATE activities SET locally_removed_at=?,deleted_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(stamp,stamp,identifier))
        elif row['locally_removed_at']:
            c.execute('UPDATE activities SET locally_removed_at=NULL,deleted_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?',(identifier,))
    return {'id':identifier,'removed':removed}


def removed_activities(path=None):
    with connect(path) as c:
        return [dict(row) for row in c.execute("SELECT id,name,activity_type,started_at,locally_removed_at FROM activities WHERE locally_removed_at IS NOT NULL AND source_name!='synthetic_fixture' ORDER BY started_at DESC,id")]
