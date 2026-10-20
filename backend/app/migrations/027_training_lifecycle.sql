ALTER TABLE training_plans ADD COLUMN deleted_at TEXT;
ALTER TABLE training_plans ADD COLUMN plan_revision INTEGER NOT NULL DEFAULT 1;
CREATE TABLE training_review_gate (
    plan_id TEXT PRIMARY KEY REFERENCES training_plans(id),
    local_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    input_revision TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);
