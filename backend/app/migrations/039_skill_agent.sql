CREATE TABLE ai_settings_skills (
 id INTEGER PRIMARY KEY CHECK(id=1),
 active_provider TEXT NOT NULL CHECK(active_provider IN ('ollama','openai','chatgpt')),
 ollama_model TEXT NOT NULL, openai_model TEXT NOT NULL,
 chatgpt_model TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO ai_settings_skills
 SELECT id,active_provider,ollama_model,openai_model,chatgpt_model,updated_at FROM ai_settings;
DROP TABLE ai_settings;
ALTER TABLE ai_settings_skills RENAME TO ai_settings;

CREATE TABLE assistant_skill_sessions (
 conversation_id TEXT PRIMARY KEY,
 state_json TEXT NOT NULL DEFAULT '{}',
 active_operation TEXT,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE assistant_skill_turns (
 operation_id TEXT PRIMARY KEY,
 conversation_id TEXT NOT NULL REFERENCES assistant_skill_sessions(conversation_id),
 request_hash TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'running',
 events_json TEXT NOT NULL DEFAULT '[]',
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE assistant_skill_calls (
 operation_id TEXT NOT NULL REFERENCES assistant_skill_turns(operation_id),
 signature TEXT NOT NULL,
 result_json TEXT,
 PRIMARY KEY(operation_id,signature)
);

INSERT INTO assistant_skill_sessions(conversation_id,state_json)
 SELECT t.conversation_id,json_object(
   'memory',json_object('previous_task',json_object('request',t.request,'status',t.status,
      'resolved_request',json_extract(t.state_json,'$.resolved_request'))),
   'nutrition',json(COALESCE(json_extract(t.state_json,'$.nutrition_context'),'{}')))
 FROM assistant_tasks t
 WHERE t.rowid=(SELECT MAX(t2.rowid) FROM assistant_tasks t2 WHERE t2.conversation_id=t.conversation_id);
