CREATE TABLE training_strength_performance (
    workout_id TEXT NOT NULL REFERENCES planned_workouts(id) ON DELETE CASCADE,
    exercise_id TEXT NOT NULL,
    set_index INTEGER NOT NULL CHECK(set_index>=1),
    load_kg REAL CHECK(load_kg>=0),
    repetitions INTEGER NOT NULL CHECK(repetitions>=0),
    repetitions_in_reserve REAL CHECK(repetitions_in_reserve BETWEEN 0 AND 10),
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(workout_id,exercise_id,set_index)
);
