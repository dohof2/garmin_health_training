CREATE TABLE telegram_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    enabled INTEGER NOT NULL DEFAULT 0,
    bot_id INTEGER,
    bot_username TEXT,
    owner_user_id INTEGER,
    owner_chat_id INTEGER,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    pairing_hash TEXT,
    pairing_expires REAL,
    pairing_attempts INTEGER NOT NULL DEFAULT 0,
    next_offset INTEGER NOT NULL DEFAULT 0,
    conversation_id TEXT NOT NULL DEFAULT '',
    last_poll_at TEXT,
    last_error TEXT
);
INSERT INTO telegram_settings(id) VALUES(1);
CREATE TABLE telegram_updates (
    bot_id INTEGER NOT NULL,
    update_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    sent_at REAL NOT NULL,
    text TEXT NOT NULL,
    reply_to INTEGER,
    state TEXT NOT NULL DEFAULT 'queued',
    reply TEXT,
    conversation_id TEXT,
    PRIMARY KEY(bot_id,update_id)
);
CREATE TABLE telegram_outbox (
    id INTEGER PRIMARY KEY,
    bot_id INTEGER NOT NULL,
    update_id INTEGER NOT NULL,
    part INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    telegram_message_id INTEGER,
    UNIQUE(bot_id,update_id,part),
    FOREIGN KEY(bot_id,update_id) REFERENCES telegram_updates(bot_id,update_id)
);
CREATE TABLE telegram_turns (
    id INTEGER PRIMARY KEY,
    bot_id INTEGER NOT NULL,
    conversation_id TEXT NOT NULL,
    update_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content TEXT NOT NULL,
    UNIQUE(bot_id,update_id,role)
);
CREATE INDEX telegram_queue ON telegram_updates(bot_id,state,update_id);
