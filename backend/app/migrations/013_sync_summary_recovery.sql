ALTER TABLE activities ADD COLUMN fit_detail_version INTEGER NOT NULL DEFAULT 0;

CREATE TABLE activity_metrics (
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL CHECK(value >= 0),
    unit TEXT NOT NULL,
    source_method TEXT NOT NULL,
    source_field TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(activity_id, metric_type)
);

CREATE TABLE garmin_sync_payloads (
    data_type TEXT NOT NULL,
    calendar_date TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(data_type, calendar_date)
);
