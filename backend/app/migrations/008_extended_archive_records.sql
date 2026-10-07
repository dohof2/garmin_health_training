CREATE TABLE garmin_archive_records (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    record_date TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, category, source_record_id)
);

CREATE INDEX garmin_archive_records_category_date_idx
    ON garmin_archive_records(category, record_date);

CREATE TABLE extended_archive_import_files (
    id TEXT PRIMARY KEY,
    archive_source_file_id TEXT NOT NULL
        REFERENCES source_files(id) ON DELETE CASCADE,
    member_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    media_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    source_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (source_record_count >= 0),
    normalized_record_count INTEGER NOT NULL DEFAULT 0
        CHECK (normalized_record_count >= 0),
    error_message TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX extended_archive_import_status_idx
    ON extended_archive_import_files(category, status);

CREATE TABLE garmin_archive_file_catalog (
    member_name TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    classification TEXT NOT NULL CHECK (
        classification IN (
            'imported', 'handled_elsewhere', 'excluded', 'container', 'unsupported'
        )
    ),
    reason TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX garmin_archive_catalog_classification_idx
    ON garmin_archive_file_catalog(classification, category);
