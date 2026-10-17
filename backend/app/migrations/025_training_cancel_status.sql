CREATE TABLE active_training_program_new (
    id INTEGER PRIMARY KEY CHECK(id=1),
    plan_id TEXT NOT NULL REFERENCES training_plans(id),
    status TEXT NOT NULL CHECK(status IN ('active','paused','completed','cancelled')),
    revision INTEGER NOT NULL DEFAULT 1,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO active_training_program_new SELECT * FROM active_training_program;
DROP TABLE active_training_program;
ALTER TABLE active_training_program_new RENAME TO active_training_program;
