ALTER TABLE meals ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE meals ADD COLUMN deleted_at TEXT;
ALTER TABLE meals ADD COLUMN operation_id TEXT;
ALTER TABLE meals ADD COLUMN operation_payload_json TEXT;
CREATE UNIQUE INDEX meal_operation_identity ON meals(operation_id) WHERE operation_id IS NOT NULL;
ALTER TABLE meal_items ADD COLUMN detail_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE nutrition_targets ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE nutrition_targets ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
CREATE TABLE meal_revisions (
 id INTEGER PRIMARY KEY, meal_id TEXT NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, UNIQUE(meal_id,revision)
);
CREATE TABLE food_library (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('recipe','meal')),
 servings REAL NOT NULL CHECK(servings>0), definition_json TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE food_library_revisions (
 id INTEGER PRIMARY KEY, library_id TEXT NOT NULL REFERENCES food_library(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, UNIQUE(library_id,revision)
);
CREATE TABLE nutrition_day_targets (
 calendar_date TEXT NOT NULL, timezone TEXT NOT NULL, target_id TEXT REFERENCES nutrition_targets(id),
 snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(calendar_date,timezone)
);
