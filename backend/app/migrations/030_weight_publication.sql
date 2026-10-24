CREATE TABLE weight_publications (
    reading_id TEXT PRIMARY KEY REFERENCES metric_readings(id),
    status TEXT NOT NULL,
    local_timestamp TEXT NOT NULL,
    utc_timestamp TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
