CREATE TABLE fit_import_files (
    id TEXT PRIMARY KEY,
    archive_source_file_id TEXT NOT NULL
        REFERENCES source_files(id) ON DELETE CASCADE,
    fit_source_file_id TEXT NOT NULL
        REFERENCES source_files(id) ON DELETE CASCADE,
    nested_archive TEXT NOT NULL,
    member_name TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL,
    activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL,
    status TEXT NOT NULL
        CHECK (status IN ('completed', 'unmatched', 'failed')),
    record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    imported_samples INTEGER NOT NULL DEFAULT 0 CHECK (imported_samples >= 0),
    error_message TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (nested_archive, member_name)
);

CREATE INDEX fit_import_files_activity_idx
    ON fit_import_files(activity_id);

CREATE INDEX fit_import_files_status_idx
    ON fit_import_files(status);
