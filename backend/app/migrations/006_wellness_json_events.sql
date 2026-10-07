CREATE TABLE hydration_events (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    source_record_id TEXT NOT NULL,
    calendar_date TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    local_recorded_at TEXT,
    hydration_source TEXT NOT NULL,
    value_ml REAL NOT NULL,
    estimated_sweat_loss_ml REAL
        CHECK (estimated_sweat_loss_ml IS NULL OR estimated_sweat_loss_ml >= 0),
    measured_sweat_loss_ml REAL
        CHECK (measured_sweat_loss_ml IS NULL OR measured_sweat_loss_ml >= 0),
    duration_seconds REAL
        CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    activity_source_record_id TEXT,
    capped INTEGER NOT NULL DEFAULT 0 CHECK (capped IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_record_id)
);

CREATE INDEX hydration_events_date_idx ON hydration_events(calendar_date);
CREATE INDEX hydration_events_recorded_at_idx ON hydration_events(recorded_at);

CREATE TABLE abnormal_heart_rate_events (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    source_record_id TEXT NOT NULL,
    calendar_date TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    heart_rate_bpm INTEGER NOT NULL CHECK (heart_rate_bpm BETWEEN 20 AND 300),
    threshold_bpm INTEGER NOT NULL CHECK (threshold_bpm BETWEEN 20 AND 300),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_record_id)
);

CREATE INDEX abnormal_hr_events_date_idx
    ON abnormal_heart_rate_events(calendar_date);
CREATE INDEX abnormal_hr_events_recorded_at_idx
    ON abnormal_heart_rate_events(recorded_at);

CREATE TABLE wellness_json_import_files (
    id TEXT PRIMARY KEY,
    archive_source_file_id TEXT NOT NULL
        REFERENCES source_files(id) ON DELETE CASCADE,
    member_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (category IN ('hydration', 'abnormal_hr')),
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    source_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (source_record_count >= 0),
    normalized_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (normalized_record_count >= 0),
    error_message TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX wellness_json_import_status_idx
    ON wellness_json_import_files(category, status);
