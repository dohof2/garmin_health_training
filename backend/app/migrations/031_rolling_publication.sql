ALTER TABLE garmin_publication_jobs ADD COLUMN rolling_root TEXT;
ALTER TABLE garmin_publication_jobs ADD COLUMN rolling_requested INTEGER NOT NULL DEFAULT 0 CHECK(rolling_requested IN (0,1));
CREATE TABLE garmin_rolling_publication (
 id INTEGER PRIMARY KEY CHECK(id=1),
 enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
 account_key TEXT NOT NULL,
 root_plan_id TEXT NOT NULL,
 timezone TEXT NOT NULL,
 running INTEGER NOT NULL DEFAULT 0,
 last_job_id TEXT,
 status TEXT NOT NULL DEFAULT 'enabled',
 detail_json TEXT NOT NULL DEFAULT '{}',
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
