-- Keep only retry identities after a meal is permanently deleted.
CREATE TABLE nutrition_deleted_operations (
    operation_id TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO nutrition_deleted_operations(operation_id)
SELECT operation_id FROM meals WHERE deleted_at IS NOT NULL AND operation_id IS NOT NULL;
UPDATE nutrition_chat_operations SET result_json = '{"deleted":true,"logged":false,"ingredients":[],"uncertainties":[],"saved_meals":[],"reply":"This food log was permanently deleted. Send a new message to log it again."}'
WHERE EXISTS (
    SELECT 1 FROM json_each(result_json, '$.saved_meals') AS ref
    JOIN meals ON meals.id = json_extract(ref.value, '$.id')
    WHERE meals.deleted_at IS NOT NULL
);
-- Remove stale saved-meal pointers from Telegram without retaining a food snapshot.
UPDATE telegram_conversation_state
SET context_json = json_set(context_json, '$.nutrition.saved_meals', json(COALESCE((
    SELECT json_group_array(json(ref.value))
    FROM json_each(telegram_conversation_state.context_json, '$.nutrition.saved_meals') AS ref
    WHERE json_extract(ref.value, '$.id') NOT IN (SELECT id FROM meals WHERE deleted_at IS NOT NULL)
), '[]')))
WHERE json_type(context_json, '$.nutrition.saved_meals') = 'array';
DELETE FROM meals WHERE deleted_at IS NOT NULL;
