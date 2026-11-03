CREATE TABLE IF NOT EXISTS assistant_batches (
 operation_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 events_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
