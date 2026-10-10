CREATE TABLE training_preferences (
    id INTEGER PRIMARY KEY CHECK(id=1),
    revision INTEGER NOT NULL,
    answers_json TEXT NOT NULL,
    confirmed_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE training_preference_revisions (
    id INTEGER PRIMARY KEY,
    revision INTEGER NOT NULL UNIQUE,
    answers_json TEXT NOT NULL,
    confirmed_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE planned_workouts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE planned_workouts ADD COLUMN completion_status TEXT NOT NULL DEFAULT 'planned';
CREATE TABLE training_workout_revisions (
    id INTEGER PRIMARY KEY,
    workout_id TEXT NOT NULL REFERENCES planned_workouts(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workout_id,revision)
);
CREATE TABLE training_feedback (
    workout_id TEXT PRIMARY KEY REFERENCES planned_workouts(id) ON DELETE CASCADE,
    effort REAL CHECK(effort BETWEEN 0 AND 10),
    soreness REAL CHECK(soreness BETWEEN 0 AND 10),
    pain_or_illness INTEGER NOT NULL CHECK(pain_or_illness IN (0,1)),
    activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
