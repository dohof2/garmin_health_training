"""Recover summaries omitted by older sync/import versions without duplicating records.

Run `PYTHONPATH=backend .venv/bin/python -m app.sync_repair --live` to also
backfill Garmin HRV history and reconcile stripped live activity summaries.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .activity_metrics import normalize_activity_metrics, preserve_fit_summary
from .database import connect, migrate
from .fit_import import _activity_fit_members, build_fit_inventory
from .garmin_import import default_archive_path
from .sync import run_sync


def recover_stored_summaries(path: Path | None = None):
    migrate(path)
    with connect(path) as connection:
        connection.execute('BEGIN IMMEDIATE')
        for row in connection.execute('SELECT id, raw_json FROM activities').fetchall():
            normalize_activity_metrics(connection, row['id'], json.loads(row['raw_json'] or '{}'))
        return connection.execute("SELECT COUNT(*) FROM activity_metrics WHERE metric_type='exercise_load'").fetchone()[0]


def recover_fit_summaries(path: Path | None = None, archive_path: Path | None = None):
    migrate(path)
    with connect(path) as connection:
        rows = connection.execute('''SELECT f.nested_archive, f.member_name, f.activity_id
            FROM fit_import_files f JOIN activities a ON a.id=f.activity_id
            WHERE f.status='completed' AND a.fit_detail_version<1''').fetchall()
    if not rows:
        return {'recovered': 0, 'failed': 0}
    archive = archive_path or default_archive_path()
    inventory = build_fit_inventory(archive)
    identities = {(row['nested_archive'], row['member_name']): row['activity_id'] for row in rows}
    skipped = {(str(item['nested_archive']), str(item['member'])) for item in inventory['activity_files']
               if (str(item['nested_archive']), str(item['member'])) not in identities}
    recovered = failed = 0
    for metadata, _, messages, errors in _activity_fit_members(archive, inventory, skipped):
        if errors:
            failed += 1
            continue
        activity_id = identities[(metadata['nested_archive'], metadata['member'])]
        with connect(path) as connection:
            connection.execute('BEGIN IMMEDIATE')
            preserve_fit_summary(connection, activity_id, messages)
        recovered += 1
        if recovered % 100 == 0:
            print(f'Recovered {recovered} preserved activity FIT summaries', flush=True)
    return {'recovered': recovered, 'failed': failed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--skip-fit', action='store_true')
    parser.add_argument('--through', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    print('Stored exercise-load coverage:', recover_stored_summaries(), flush=True)
    if not args.skip_fit:
        print('FIT recovery:', recover_fit_summaries(), flush=True)
    if args.live:
        from .garmin_connection import GarminConnectProvider
        provider = GarminConnectProvider.from_saved_session()
        with connect() as connection:
            first = connection.execute("SELECT MIN(substr(started_at,1,10)) FROM activities WHERE json_type(raw_json,'$.source_record_id') IS NOT NULL").fetchone()[0]
        if first:
            result = run_sync(provider, args.through, data_types=('activities',), reconcile_from=date.fromisoformat(first), request_delay_seconds=.1)
            print('Activity reconciliation:', json.dumps(result), flush=True)
        result = run_sync(provider, args.through, data_types=('hrv_metrics',), request_delay_seconds=.01)
        print('HRV backfill:', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
