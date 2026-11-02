-- Preserve qualifying observations when the daily Garmin snapshot is replaced.
-- This evidence is used only by the until-sleep deduction, never as a live timer.
CREATE TABLE recovery_time_observations (
    reading_id TEXT NOT NULL REFERENCES metric_readings(id) ON DELETE CASCADE,
    recorded_at TEXT NOT NULL,
    value REAL NOT NULL,
    source_name TEXT NOT NULL,
    PRIMARY KEY (reading_id, recorded_at)
);
INSERT INTO recovery_time_observations
SELECT id,recorded_at,value,source_name FROM metric_readings
WHERE metric_type='recovery_time' AND unit='min' AND value>1440
  AND source_name NOT IN ('synthetic_fixture','projection');
CREATE TRIGGER retain_high_recovery_insert AFTER INSERT ON metric_readings
WHEN NEW.metric_type='recovery_time' AND NEW.unit='min' AND NEW.value>1440
 AND NEW.source_name NOT IN ('synthetic_fixture','projection')
BEGIN
 INSERT INTO recovery_time_observations VALUES(NEW.id,NEW.recorded_at,NEW.value,NEW.source_name)
 ON CONFLICT(reading_id,recorded_at) DO UPDATE SET value=MAX(value,excluded.value);
END;
CREATE TRIGGER retain_high_recovery_update AFTER UPDATE ON metric_readings
WHEN NEW.metric_type='recovery_time' AND NEW.unit='min' AND NEW.value>1440
 AND NEW.source_name NOT IN ('synthetic_fixture','projection')
BEGIN
 INSERT INTO recovery_time_observations VALUES(NEW.id,NEW.recorded_at,NEW.value,NEW.source_name)
 ON CONFLICT(reading_id,recorded_at) DO UPDATE SET value=MAX(value,excluded.value);
END;
