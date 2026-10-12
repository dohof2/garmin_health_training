ALTER TABLE activities ADD COLUMN locally_removed_at TEXT;

-- Local removal survives remote sync/import refreshes. Recorded data remains recoverable.
CREATE TRIGGER preserve_local_activity_removal
AFTER UPDATE OF deleted_at ON activities
WHEN NEW.locally_removed_at IS NOT NULL AND NEW.deleted_at IS NULL
BEGIN
    UPDATE activities SET deleted_at=NEW.locally_removed_at WHERE id=NEW.id;
END;
