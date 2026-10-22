CREATE TABLE garmin_publication_jobs (
 id TEXT PRIMARY KEY,
 account_key TEXT NOT NULL,
 account_label TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'preview',
 timezone TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 approved_at TEXT,
 error TEXT
);
CREATE TABLE garmin_publication_items (
 id TEXT PRIMARY KEY,
 job_id TEXT NOT NULL REFERENCES garmin_publication_jobs(id),
 account_key TEXT NOT NULL,
 identity_key TEXT NOT NULL,
 workout_id TEXT REFERENCES planned_workouts(id),
 workout_revision INTEGER,
 snapshot_json TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 scheduled_date TEXT,
 action TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'preview',
 remote_workout_id TEXT,
 remote_schedule_id TEXT,
 error TEXT,
 UNIQUE(job_id, identity_key)
);
CREATE UNIQUE INDEX garmin_one_publication_in_flight ON garmin_publication_items(account_key,identity_key)
 WHERE state IN ('queued','creating','created','updating','scheduling','verifying','unknown','retryable');
CREATE TABLE garmin_publication_links (
 account_key TEXT NOT NULL,
 identity_key TEXT NOT NULL,
 workout_id TEXT REFERENCES planned_workouts(id),
 remote_workout_id TEXT NOT NULL,
 remote_schedule_id TEXT,
 scheduled_date TEXT,
 verified_hash TEXT,
 verified_payload_json TEXT,
 PRIMARY KEY(account_key, identity_key)
);
