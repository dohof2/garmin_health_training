CREATE TABLE dashboard_widget_layout (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    widgets_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
