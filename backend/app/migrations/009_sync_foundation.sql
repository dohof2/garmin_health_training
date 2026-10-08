ALTER TABLE activities ADD COLUMN source_updated_at TEXT;
ALTER TABLE activities ADD COLUMN deleted_at TEXT;
ALTER TABLE metric_readings ADD COLUMN source_updated_at TEXT;

CREATE TABLE sync_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider_name TEXT NOT NULL DEFAULT 'garmin_connect',
    connection_status TEXT NOT NULL DEFAULT 'not_connected' CHECK (
        connection_status IN ('not_connected', 'connected', 'reconnect_required')
    ),
    overlap_days INTEGER NOT NULL DEFAULT 3 CHECK (overlap_days BETWEEN 0 AND 30),
    schedule_enabled INTEGER NOT NULL DEFAULT 0 CHECK (schedule_enabled IN (0, 1)),
    last_scheduled_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO sync_settings(id) VALUES (1);

CREATE TABLE sync_checkpoints (
    data_type TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    coverage_start TEXT,
    coverage_end TEXT,
    seeded_from_import INTEGER NOT NULL DEFAULT 0 CHECK (seeded_from_import IN (0, 1)),
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_source_updated_at TEXT,
    last_reconciled_start TEXT,
    last_reconciled_end TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'syncing', 'synced', 'failed', 'reconnect_required')
    ),
    error_message TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sync_intervals (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    data_type TEXT NOT NULL REFERENCES sync_checkpoints(data_type) ON DELETE CASCADE,
    interval_start TEXT NOT NULL,
    interval_end TEXT NOT NULL,
    interval_kind TEXT NOT NULL CHECK (
        interval_kind IN ('gap', 'overlap', 'reconciliation')
    ),
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    records_received INTEGER NOT NULL DEFAULT 0 CHECK (records_received >= 0),
    records_created INTEGER NOT NULL DEFAULT 0 CHECK (records_created >= 0),
    records_updated INTEGER NOT NULL DEFAULT 0 CHECK (records_updated >= 0),
    records_unchanged INTEGER NOT NULL DEFAULT 0 CHECK (records_unchanged >= 0),
    empty_result INTEGER NOT NULL DEFAULT 0 CHECK (empty_result IN (0, 1)),
    error_message TEXT,
    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (job_id, data_type, interval_start, interval_end, interval_kind)
);

CREATE INDEX sync_intervals_type_date_idx
    ON sync_intervals(data_type, interval_start, status);
CREATE INDEX sync_intervals_job_idx ON sync_intervals(job_id);
