CREATE TABLE active_training_program (
    id INTEGER PRIMARY KEY CHECK(id=1),
    plan_id TEXT NOT NULL REFERENCES training_plans(id),
    status TEXT NOT NULL CHECK(status IN ('active','paused','completed')),
    revision INTEGER NOT NULL DEFAULT 1,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE training_program_reviews (
    id INTEGER PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES training_plans(id),
    fingerprint TEXT NOT NULL,
    review_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plan_id,fingerprint)
);
