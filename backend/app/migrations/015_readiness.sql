CREATE TABLE readiness_configs (
    version TEXT PRIMARY KEY,
    formula_version TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE readiness_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    config_version TEXT NOT NULL REFERENCES readiness_configs(version)
);
CREATE TABLE readiness_calculations (
    id INTEGER PRIMARY KEY,
    calendar_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    config_version TEXT NOT NULL REFERENCES readiness_configs(version),
    input_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(calendar_date, timezone, config_version, input_hash)
);
CREATE INDEX readiness_date_idx ON readiness_calculations(calendar_date);
