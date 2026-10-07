CREATE TABLE health_samples (
    id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    recorded_at TEXT NOT NULL,
    heart_rate_bpm INTEGER
        CHECK (heart_rate_bpm IS NULL OR heart_rate_bpm BETWEEN 20 AND 250),
    stress_level INTEGER
        CHECK (stress_level IS NULL OR stress_level BETWEEN 0 AND 100),
    respiration_rate REAL
        CHECK (respiration_rate IS NULL OR respiration_rate > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, recorded_at)
);

CREATE INDEX health_samples_time_idx ON health_samples(recorded_at);

CREATE TABLE monitoring_fit_import_files (
    id TEXT PRIMARY KEY,
    archive_source_file_id TEXT NOT NULL
        REFERENCES source_files(id) ON DELETE CASCADE,
    nested_archive TEXT NOT NULL,
    member_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    sample_count INTEGER NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    error_message TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (nested_archive, member_name)
);

CREATE INDEX monitoring_fit_import_status_idx
    ON monitoring_fit_import_files(status);
