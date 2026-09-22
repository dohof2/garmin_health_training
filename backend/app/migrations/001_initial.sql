CREATE TABLE source_files (
    id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    media_type TEXT,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    stored_path TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    progress_current INTEGER NOT NULL DEFAULT 0 CHECK (progress_current >= 0),
    progress_total INTEGER CHECK (progress_total IS NULL OR progress_total >= 0),
    checkpoint_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE activities (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_record_id TEXT,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    activity_type TEXT NOT NULL,
    name TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    timezone TEXT,
    duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    distance_meters REAL CHECK (distance_meters IS NULL OR distance_meters >= 0),
    calories_kcal REAL CHECK (calories_kcal IS NULL OR calories_kcal >= 0),
    elevation_gain_meters REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_record_id)
);

CREATE INDEX activities_started_at_idx ON activities(started_at);
CREATE INDEX activities_type_idx ON activities(activity_type);

CREATE TABLE activity_samples (
    id INTEGER PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    recorded_at TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    elevation_meters REAL,
    heart_rate_bpm INTEGER,
    cadence_rpm REAL,
    power_watts REAL,
    speed_mps REAL,
    raw_json TEXT,
    UNIQUE (activity_id, recorded_at)
);

CREATE INDEX activity_samples_activity_time_idx
    ON activity_samples(activity_id, recorded_at);

CREATE TABLE metric_readings (
    id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_record_id TEXT,
    source_file_id TEXT REFERENCES source_files(id) ON DELETE SET NULL,
    metric_type TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_record_id, metric_type)
);

CREATE INDEX metric_readings_type_time_idx
    ON metric_readings(metric_type, recorded_at);

CREATE TABLE user_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    display_name TEXT,
    timezone TEXT,
    preferred_distance_unit TEXT,
    preferred_weight_unit TEXT,
    birth_date TEXT,
    sex TEXT,
    height_cm REAL,
    weight_kg REAL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE goals (
    id TEXT PRIMARY KEY,
    goal_type TEXT NOT NULL,
    title TEXT NOT NULL,
    target_value REAL,
    target_unit TEXT,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dashboard_cards (
    id TEXT PRIMARY KEY,
    card_type TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    settings_json TEXT NOT NULL DEFAULT '{}',
    is_visible INTEGER NOT NULL DEFAULT 1 CHECK (is_visible IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE training_plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    starts_on TEXT,
    ends_on TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE planned_workouts (
    id TEXT PRIMARY KEY,
    training_plan_id TEXT REFERENCES training_plans(id) ON DELETE SET NULL,
    sport TEXT NOT NULL,
    title TEXT NOT NULL,
    scheduled_for TEXT,
    definition_json TEXT NOT NULL,
    garmin_workout_id TEXT,
    publish_status TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE nutrition_targets (
    id TEXT PRIMARY KEY,
    effective_from TEXT NOT NULL,
    calories_kcal REAL CHECK (calories_kcal IS NULL OR calories_kcal >= 0),
    protein_grams REAL CHECK (protein_grams IS NULL OR protein_grams >= 0),
    fat_grams REAL CHECK (fat_grams IS NULL OR fat_grams >= 0),
    carbohydrate_grams REAL CHECK (carbohydrate_grams IS NULL OR carbohydrate_grams >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE meals (
    id TEXT PRIMARY KEY,
    eaten_at TEXT NOT NULL,
    meal_type TEXT,
    notes TEXT,
    photo_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE meal_items (
    id TEXT PRIMARY KEY,
    meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    calories_kcal REAL CHECK (calories_kcal IS NULL OR calories_kcal >= 0),
    protein_grams REAL CHECK (protein_grams IS NULL OR protein_grams >= 0),
    fat_grams REAL CHECK (fat_grams IS NULL OR fat_grams >= 0),
    carbohydrate_grams REAL CHECK (carbohydrate_grams IS NULL OR carbohydrate_grams >= 0),
    confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE equipment (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    equipment_type TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE maintenance_events (
    id TEXT PRIMARY KEY,
    equipment_id TEXT NOT NULL REFERENCES equipment(id) ON DELETE RESTRICT,
    action TEXT NOT NULL,
    event_date TEXT NOT NULL,
    cost_amount REAL CHECK (cost_amount IS NULL OR cost_amount >= 0),
    cost_currency TEXT,
    details TEXT,
    operation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE maintenance_event_revisions (
    id INTEGER PRIMARY KEY,
    maintenance_event_id TEXT NOT NULL REFERENCES maintenance_events(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
    snapshot_json TEXT NOT NULL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (maintenance_event_id, revision_number)
);
