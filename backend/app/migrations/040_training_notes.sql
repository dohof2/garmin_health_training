CREATE TABLE training_notes (
 activity TEXT NOT NULL,
 workout_type TEXT NOT NULL DEFAULT 'all',
 topic TEXT NOT NULL,
 text TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 160),
 settings_json TEXT NOT NULL DEFAULT '{}',
 revision INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(activity,workout_type,topic)
);
INSERT INTO training_notes(activity,workout_type,topic,text,settings_json)
 SELECT 'strength','all','sets',
 'Use ' || json_extract(state_json,'$.strength_set_policy.sets') || ' sets per exercise, including recovery weeks.',
 json_object('sets',json_extract(state_json,'$.strength_set_policy.sets'))
 FROM active_training_program
 WHERE json_extract(state_json,'$.strength_set_policy.sets') BETWEEN 1 AND 5;
