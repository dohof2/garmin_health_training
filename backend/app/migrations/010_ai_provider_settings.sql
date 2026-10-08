CREATE TABLE ai_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_provider TEXT NOT NULL DEFAULT 'ollama' CHECK (
        active_provider IN ('ollama', 'openai')
    ),
    ollama_model TEXT NOT NULL DEFAULT 'qwen3.5:2b',
    openai_model TEXT NOT NULL DEFAULT 'gpt-6-astra',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO ai_settings(id) VALUES (1);
