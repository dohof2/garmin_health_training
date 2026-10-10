CREATE TABLE ai_settings_actions (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL CHECK(target IN ('profile', 'goals')),
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'saved')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    saved_at TEXT
);
CREATE TABLE goal_revisions (
    id INTEGER PRIMARY KEY,
    goal_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER goal_created_revision AFTER INSERT ON goals BEGIN
    INSERT INTO goal_revisions(goal_id, snapshot_json) VALUES (NEW.id,
        json_object('title', NEW.title, 'goal_type', NEW.goal_type, 'target_value', NEW.target_value,
        'target_unit', NEW.target_unit, 'target_date', NEW.target_date, 'status', NEW.status, 'notes', NEW.notes));
END;
CREATE TRIGGER goal_updated_revision AFTER UPDATE ON goals
WHEN OLD.title IS NOT NEW.title OR OLD.goal_type IS NOT NEW.goal_type
    OR OLD.target_value IS NOT NEW.target_value OR OLD.target_unit IS NOT NEW.target_unit
    OR OLD.target_date IS NOT NEW.target_date OR OLD.status IS NOT NEW.status OR OLD.notes IS NOT NEW.notes
BEGIN
    INSERT INTO goal_revisions(goal_id, snapshot_json) VALUES (NEW.id,
        json_object('title', NEW.title, 'goal_type', NEW.goal_type, 'target_value', NEW.target_value,
        'target_unit', NEW.target_unit, 'target_date', NEW.target_date, 'status', NEW.status, 'notes', NEW.notes));
END;
INSERT INTO goal_revisions(goal_id, snapshot_json)
SELECT id, json_object('title', title, 'goal_type', goal_type, 'target_value', target_value,
    'target_unit', target_unit, 'target_date', target_date, 'status', status, 'notes', notes) FROM goals;
