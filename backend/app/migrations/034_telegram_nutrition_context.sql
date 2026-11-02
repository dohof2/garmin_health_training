CREATE TABLE telegram_conversation_state (
    bot_id INTEGER NOT NULL,
    conversation_id TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(bot_id,conversation_id)
);
