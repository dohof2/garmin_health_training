CREATE TABLE garmin_nutrition_daily (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    source_record_id TEXT NOT NULL,
    calendar_date TEXT NOT NULL,
    calories_consumed REAL
        CHECK (calories_consumed IS NULL OR calories_consumed >= 0),
    calorie_goal REAL CHECK (calorie_goal IS NULL OR calorie_goal >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_record_id),
    UNIQUE (source_name, calendar_date)
);

CREATE INDEX garmin_nutrition_daily_date_idx
    ON garmin_nutrition_daily(calendar_date);

CREATE TABLE wellness_json_import_files_new (
    id TEXT PRIMARY KEY,
    archive_source_file_id TEXT NOT NULL
        REFERENCES source_files(id) ON DELETE CASCADE,
    member_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL
        CHECK (category IN ('hydration', 'abnormal_hr', 'nutrition')),
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    source_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (source_record_count >= 0),
    normalized_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (normalized_record_count >= 0),
    error_message TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO wellness_json_import_files_new(
    id, archive_source_file_id, member_name, category, content_hash, status,
    source_record_count, normalized_record_count, error_message, imported_at
)
SELECT
    id, archive_source_file_id, member_name, category, content_hash, status,
    source_record_count, normalized_record_count, error_message, imported_at
FROM wellness_json_import_files;

DROP TABLE wellness_json_import_files;
ALTER TABLE wellness_json_import_files_new RENAME TO wellness_json_import_files;

CREATE INDEX wellness_json_import_status_idx
    ON wellness_json_import_files(category, status);
