CREATE TABLE ai_settings_new (
 id INTEGER PRIMARY KEY CHECK(id=1),
 active_provider TEXT NOT NULL CHECK(active_provider IN ('ollama','openai','chatgpt')),
 ollama_model TEXT NOT NULL,
 openai_model TEXT NOT NULL,
 chatgpt_model TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO ai_settings_new(id,active_provider,ollama_model,openai_model,updated_at)
 SELECT id,active_provider,ollama_model,openai_model,updated_at FROM ai_settings;
DROP TABLE ai_settings;
ALTER TABLE ai_settings_new RENAME TO ai_settings;
