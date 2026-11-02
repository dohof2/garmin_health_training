CREATE TABLE nutrition_chat_operations (
    operation_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
