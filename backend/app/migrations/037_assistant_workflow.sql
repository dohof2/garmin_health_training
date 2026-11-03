ALTER TABLE ai_settings ADD COLUMN assistant_workflow TEXT NOT NULL DEFAULT 'efficient' CHECK(assistant_workflow IN ('efficient','legacy'));
CREATE TABLE assistant_tasks (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL,
 kind TEXT NOT NULL, status TEXT NOT NULL, request TEXT NOT NULL,
 timezone TEXT NOT NULL, anchor_date TEXT NOT NULL, state_json TEXT NOT NULL DEFAULT '{}',
 model_calls INTEGER NOT NULL DEFAULT 0, input_estimate INTEGER NOT NULL DEFAULT 0,
 output_estimate INTEGER NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
 output_tokens INTEGER NOT NULL DEFAULT 0, usage_reported INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX assistant_tasks_conversation ON assistant_tasks(conversation_id,updated_at);
CREATE TABLE assistant_turns (
 operation_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 task_id TEXT NOT NULL REFERENCES assistant_tasks(id), events_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
