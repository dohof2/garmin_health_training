# Maintenance CSV snapshots

SQLite is the authoritative history. **Maintenance → Export current history CSV** downloads active current records, including stable IDs. Removed records and revisions remain in SQLite and full backups. Versioned JSON includes equipment, events and revision snapshots.

Files use UTF-8, comma separators, a header, quoted commas/newlines/quotes and ISO calendar dates. Exported text beginning with spreadsheet formula characters is prefixed with an apostrophe; an existing leading apostrophe is doubled. The `maintenance-v1` marker allows this app to reverse that protection on import without changing stored text. External unversioned files keep their literal apostrophes.

| Column | Meaning |
|---|---|
| `format` | `maintenance-v1`; retain when reimporting an app export |
| `id` | Stable event identifier; optional for external files |
| `equipment_label` | Required equipment/item label; created as needed |
| `action` | Required work performed |
| `event_date` | Required completion date, `YYYY-MM-DD`; future dates rejected |
| `category` | `general`, `replacement`, `service`, `repair`, `inspection`; blank defaults to `general` |
| `part` | Optional part/accessory description |
| `quantity` | Optional positive quantity |
| `cost_amount` | Optional nonnegative recorded cost |
| `cost_currency` | Optional three-letter currency code, e.g. `EUR`; requires a cost |
| `provider` | Optional service provider |
| `usage_value` | Optional nonnegative manually recorded usage |
| `usage_unit` | Optional unit such as `km`, `mi`, or `hours`; requires usage value |
| `details` | Optional notes; treated as text, never executable instructions |

Blank optional cells are missing values. The app never infers currency, units or cost. Costs with no currency are reported separately; different currencies are never added together.

Choose a CSV in Maintenance, review or change the column mapping, and preview it. Common aliases include `equipment`, `item`, `work`, `date`, `cost`, `currency`, and `notes`. Maximum size is 2 MiB and 2,000 records; headers must be unique and every row must have the same number of columns. Fix any invalid row before applying the batch.

An existing identical ID is unchanged. An existing ID with different fields is a conflict and defaults to **Skip**; inspect all imported/current fields and choose **Update existing event** deliberately. This also shows a removed event's status before an update restores it. New rows default to **Create**. Repeated rows in a file are skipped; files without IDs use all business fields to recognize unchanged records. Different dates or different stable IDs preserve distinct events. Keep IDs when editing an exported snapshot: removing an ID from a changed row makes it a new event rather than a correction.

Importing an unchanged snapshot creates no duplicates. Imports apply atomically, reject conflicts changed since preview, and have an Undo action. Retrying the same operation does not repeat its writes. Corrections, removal, restoration and Undo append revisions; they do not erase past snapshots. CSV is not a live external-file sync.
