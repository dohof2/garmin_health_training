ALTER TABLE maintenance_events ADD COLUMN category TEXT NOT NULL DEFAULT 'general';
ALTER TABLE maintenance_events ADD COLUMN part TEXT;
ALTER TABLE maintenance_events ADD COLUMN quantity REAL CHECK(quantity IS NULL OR quantity > 0);
ALTER TABLE maintenance_events ADD COLUMN provider TEXT;
ALTER TABLE maintenance_events ADD COLUMN usage_value REAL CHECK(usage_value IS NULL OR usage_value >= 0);
ALTER TABLE maintenance_events ADD COLUMN usage_unit TEXT;
CREATE INDEX maintenance_date_idx ON maintenance_events(event_date DESC);
CREATE TABLE maintenance_operations (
    id TEXT PRIMARY KEY,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    undone_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE maintenance_pending (
    id TEXT PRIMARY KEY,
    draft_json TEXT NOT NULL,
    missing_field TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE maintenance_csv_previews (
    id TEXT PRIMARY KEY,
    plan_json TEXT NOT NULL,
    applied_operation_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE maintenance_chat_requests (
    id TEXT PRIMARY KEY,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO maintenance_event_revisions(maintenance_event_id, revision_number, snapshot_json)
SELECT m.id, 1, json_object('id', m.id, 'equipment_label', e.label, 'equipment_id', m.equipment_id,
    'action', m.action, 'event_date', m.event_date, 'category', m.category, 'part', m.part,
    'quantity', m.quantity, 'cost_amount', m.cost_amount, 'cost_currency', m.cost_currency,
    'provider', m.provider, 'usage_value', m.usage_value, 'usage_unit', m.usage_unit,
    'details', m.details, 'deleted_at', m.deleted_at, 'operation_id', m.operation_id, 'revision', 1)
FROM maintenance_events m JOIN equipment e ON e.id = m.equipment_id
WHERE NOT EXISTS (SELECT 1 FROM maintenance_event_revisions r WHERE r.maintenance_event_id = m.id);
