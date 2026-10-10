import { useEffect, useRef, useState } from "react";

export type MaintenanceEvent = {
  id: string;
  equipment_label: string;
  action: string;
  event_date: string;
  category: string;
  part: string | null;
  quantity: number | null;
  cost_amount: number | null;
  cost_currency: string | null;
  provider: string | null;
  usage_value: number | null;
  usage_unit: string | null;
  details: string | null;
  revision: number;
  deleted_at: string | null;
};
export type MaintenanceResult = {
  tool: string;
  events?: MaintenanceEvent[];
  equipment?: Array<{ id: string; label: string }>;
  total_matches?: number;
  truncated?: boolean;
  saved?: boolean;
  operation_id?: string;
  undo_available?: boolean;
  clarification_id?: string;
  question?: string;
  message?: string;
  download_url?: string;
  cost_totals?: Array<{ currency: string | null; amount: number; event_count: number }>;
};
type CSVPreview = {
  preview_id: string | null;
  columns: string[];
  mapping: Record<string, string>;
  errors: string[];
  counts?: Record<string, number>;
  rows: Array<{ row: number; id: string; status: string; values: MaintenanceEvent; before: MaintenanceEvent | null }>;
};
const fields = ["equipment_label", "action", "event_date", "category", "part", "quantity", "cost_amount", "cost_currency", "provider", "usage_value", "usage_unit", "details"] as const;
const numericFields = new Set<string>(["quantity", "cost_amount", "usage_value"]);
const labels: Record<typeof fields[number], string> = {
  equipment_label: "Equipment or item", action: "Work performed", event_date: "Completed date", category: "Category",
  part: "Part", quantity: "Quantity", cost_amount: "Cost", cost_currency: "Currency (e.g. EUR)",
  provider: "Service provider", usage_value: "Manual usage", usage_unit: "Usage unit (e.g. km)", details: "Notes",
};
const categories = ["general", "replacement", "service", "repair", "inspection"];
type Draft = Record<typeof fields[number], string>;
const emptyDraft = (timezone: string): Draft => ({
  equipment_label: "", action: "", event_date: new Date().toLocaleDateString("en-CA", { timeZone: timezone }), category: "general",
  part: "", quantity: "", cost_amount: "", cost_currency: "", provider: "", usage_value: "", usage_unit: "", details: "",
});
function EventDetails({ event }: { event: MaintenanceEvent }) {
  return <dl>{fields.map((field) => <div key={field}><dt>{labels[field]}</dt><dd>{event[field] == null ? "Not recorded" : String(event[field])}</dd></div>)}
    {event.deleted_at && <div><dt>Status</dt><dd>Removed (recoverable)</dd></div>}</dl>;
}
async function api(url: string, body?: unknown, method = "POST") {
  const response = await fetch(url, body === undefined ? undefined : {
    method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: unknown };
    throw new Error(typeof payload.detail === "string" ? payload.detail : "The maintenance request could not be completed.");
  }
  return response.json();
}

export default function MaintenancePanel({ refreshToken, timezone, onChanged }: {
  refreshToken: number; timezone: string; onChanged: () => void;
}) {
  const [history, setHistory] = useState<MaintenanceResult | null>(null);
  const [filters, setFilters] = useState({ equipment: "", query: "", category: "", start_date: "", end_date: "", include_deleted: false });
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(timezone));
  const [editing, setEditing] = useState<MaintenanceEvent | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<{ event: MaintenanceEvent; revisions: MaintenanceEvent[] } | null>(null);
  const [csvContent, setCSVContent] = useState("");
  const [preview, setPreview] = useState<CSVPreview | null>(null);
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const retry = useRef<{ key: string; id: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value !== "") params.set(key, String(value));
    fetch(`/api/maintenance?${params}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Maintenance history could not be loaded.");
        setHistory(await response.json() as MaintenanceResult);
      })
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === "AbortError")) setMessage(error instanceof Error ? error.message : "Maintenance history could not be loaded."); });
    return () => controller.abort();
  }, [refreshToken, filters]);

  const mutate = async (url: string, body: Record<string, unknown>, method = "POST") => {
    const key = JSON.stringify({ url, body, method });
    if (retry.current?.key !== key) retry.current = { key, id: crypto.randomUUID() };
    const result = await api(url, { ...body, operation_id: retry.current.id }, method) as MaintenanceResult;
    retry.current = null;
    setLastAction(result.operation_id ?? null);
    setMessage(result.message ?? "Saved locally.");
    onChanged();
    return result;
  };
  const perform = async (action: () => Promise<unknown>) => {
    setBusy(true); setMessage(null);
    try { await action(); } catch (error) { setMessage(error instanceof Error ? error.message : "The change could not be saved."); }
    finally { setBusy(false); }
  };
  const save = () => perform(async () => {
    const values = Object.fromEntries(fields.map((field) => [field,
      draft[field] === "" ? null : numericFields.has(field) ? Number(draft[field]) : draft[field]]));
    if (editing) await mutate(`/api/maintenance/events/${encodeURIComponent(editing.id)}`, { changes: values, expected_revision: editing.revision, timezone }, "PATCH");
    else await mutate("/api/maintenance", { events: [values], timezone });
    setDraft(emptyDraft(timezone)); setEditing(null); setRevisions(null);
  });
  const edit = (event: MaintenanceEvent) => {
    setEditing(event); setDraft(Object.fromEntries(fields.map((field) => [field, event[field] == null ? "" : String(event[field])])) as Draft);
    setMessage(null);
  };
  const previewCSV = async (content: string, mapping?: Record<string, string>) => {
    const result = await api("/api/maintenance/csv/preview", { content, mapping }) as CSVPreview;
    setPreview(result);
    setDecisions(Object.fromEntries(result.rows.map((row) => [String(row.row), row.status === "new" ? "create" : "skip"])));
  };

  return <section id="maintenance" className="maintenance" aria-labelledby="maintenance-title">
    <div className="section-heading"><div><p>Maintenance and replacements</p><h2 id="maintenance-title">Keep your equipment history</h2></div>
      <a className="export-link" href="/api/maintenance/export.csv">Export current history CSV</a></div>
    <p>Log completed work here or in chat. Equipment labels are created as needed. Costs and manual usage are optional.</p>
    {message && <p role="status" className="maintenance-message">{message}</p>}
    {lastAction && <button type="button" disabled={busy} onClick={() => void perform(async () => {
      await mutate(`/api/maintenance/operations/${encodeURIComponent(lastAction)}/undo`, {}); setLastAction(null); setRevisions(null);
    })}>Undo last saved action</button>}

    <form className="maintenance-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <h3>{editing ? "Edit maintenance event" : "Log completed work"}</h3>
      <div className="maintenance-fields">{fields.map((field) => <label key={field}>{labels[field]}
        {field === "category" ? <select value={draft[field]} onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}>
          {categories.map((category) => <option key={category}>{category}</option>)}</select>
        : field === "details" ? <textarea value={draft[field]} onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} maxLength={2000} />
        : <input type={field === "event_date" ? "date" : numericFields.has(field) ? "number" : "text"}
            list={field === "equipment_label" ? "maintenance-equipment-labels" : undefined}
            required={["equipment_label", "action", "event_date"].includes(field)}
            min={field === "quantity" ? 0.0001 : numericFields.has(field) ? 0 : undefined} step="any"
            maxLength={field === "cost_currency" ? 3 : undefined} value={draft[field]}
            onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} />}
      </label>)}</div>
      <datalist id="maintenance-equipment-labels">{history?.equipment?.map((item) => <option key={item.id} value={item.label} />)}</datalist>
      <div className="maintenance-actions"><button type="submit" disabled={busy}>{busy ? "Saving…" : editing ? "Save correction" : "Save completed work"}</button>
        {editing && <button type="button" onClick={() => { setEditing(null); setDraft(emptyDraft(timezone)); }}>Cancel edit</button>}</div>
    </form>

    <div className="maintenance-filters" aria-label="Maintenance filters">
      <label>Equipment<select value={filters.equipment} onChange={(event) => setFilters({ ...filters, equipment: event.target.value })}>
        <option value="">All equipment</option>{history?.equipment?.map((item) => <option key={item.id}>{item.label}</option>)}</select></label>
      <label>Search work or part<input value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} /></label>
      <label>Category<select value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })}>
        <option value="">All categories</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
      <label>From<input type="date" value={filters.start_date} onChange={(event) => setFilters({ ...filters, start_date: event.target.value })} /></label>
      <label>To<input type="date" value={filters.end_date} onChange={(event) => setFilters({ ...filters, end_date: event.target.value })} /></label>
      <label><input type="checkbox" checked={filters.include_deleted} onChange={(event) => setFilters({ ...filters, include_deleted: event.target.checked })} /> Include removed events</label>
    </div>
    <div className="maintenance-totals">{history?.cost_totals?.map((total) => <span key={total.currency ?? "unknown"}>{total.amount.toLocaleString()} {total.currency ?? "currency not recorded"} · {total.event_count} events</span>)}</div>
    {!history ? <p>Loading maintenance history…</p> : !history.events?.length ? <p>No matching maintenance records. Start with an equipment label, completed work and date.</p> : <>
      <p>{history.total_matches} matching events{history.truncated ? ` · ${history.events.length} shown; narrow the filters to see other records` : ""}. Cost totals exclude removed events.</p>
      <div className="maintenance-table"><table><thead><tr><th>Date</th><th>Equipment / work</th><th>Cost</th><th>Actions</th></tr></thead><tbody>
        {history.events.map((event) => <tr key={event.id}>
          <td>{event.event_date}{event.deleted_at && <small>Removed</small>}</td>
          <td><strong>{event.equipment_label}</strong><span>{event.action}</span><small>{event.category}{event.part ? ` · ${event.part}` : ""}</small>
            {event.quantity != null && <small>Quantity: {event.quantity}</small>}{event.provider && <small>Provider: {event.provider}</small>}
            {event.details && <small>{event.details}</small>}{event.usage_value != null && <small>Manual usage: {event.usage_value} {event.usage_unit ?? "unit not recorded"}</small>}
            <small>Event ID: {event.id}</small></td>
          <td>{event.cost_amount == null ? "Not recorded" : `${event.cost_amount} ${event.cost_currency ?? "currency not recorded"}`}</td>
          <td><div className="maintenance-actions"><button type="button" disabled={busy || !!event.deleted_at} onClick={() => edit(event)}>Edit</button>
            <button type="button" disabled={busy} onClick={() => void perform(async () => {
              await mutate(`/api/maintenance/events/${encodeURIComponent(event.id)}`, { changes: {}, expected_revision: event.revision, deleted: !event.deleted_at }, "PATCH");
            })}>{event.deleted_at ? "Restore" : "Remove"}</button>
            <button type="button" onClick={() => void perform(async () => setRevisions(await api(`/api/maintenance/events/${encodeURIComponent(event.id)}`)))}>Revisions</button></div></td>
        </tr>)}
      </tbody></table></div>
    </>}
    {revisions && <div className="maintenance-revisions"><h3>Revision history · {revisions.event.equipment_label}</h3>
      <button type="button" onClick={() => setRevisions(null)}>Close revisions</button>
      {revisions.revisions.map((revision) => <details key={revision.revision}><summary>Revision {revision.revision} · {revision.event_date} · {revision.action}{revision.deleted_at ? " · removed" : ""}</summary><EventDetails event={revision} /></details>)}
    </div>}

    <div className="maintenance-csv"><h3>Import a CSV snapshot</h3>
      <p>UTF-8 CSV. Map your columns, preview all rows, and choose how to handle conflicts. Unchanged and duplicate rows are skipped.</p>
      <label>Choose maintenance CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => {
        const file = event.target.files?.[0]; if (!file) return;
        void perform(async () => {
          if (file.size > 2 * 1024 * 1024) throw new Error("CSV files must be no more than 2 MiB.");
          const content = await file.text(); setCSVContent(content); await previewCSV(content);
        });
      }} /></label>
      {preview && <>
        <div className="maintenance-fields">{["id", ...fields].map((field) => <label key={field}>{field === "id" ? "Event ID (optional)" : labels[field as typeof fields[number]]}
          <select value={preview.mapping[field] ?? ""} onChange={(event) => setPreview({ ...preview, preview_id: null, rows: [], mapping: { ...preview.mapping, [field]: event.target.value } })}>
            <option value="">Not mapped</option>{preview.columns.map((column) => <option key={column}>{column}</option>)}</select></label>)}</div>
        <button type="button" disabled={busy} onClick={() => void perform(() => previewCSV(csvContent, Object.fromEntries(Object.entries(preview.mapping).filter(([, column]) => column))))}>Preview mapped rows</button>
        {preview.errors.map((error, index) => <p role="alert" key={index}>{error}</p>)}
        {preview.counts && <p>{preview.counts.new} new · {preview.counts.unchanged} unchanged · {preview.counts.duplicate} duplicate · {preview.counts.conflict} conflicting rows</p>}
        {preview.rows.length > 0 && <div className="maintenance-table"><table><thead><tr><th>Row / status</th><th>Imported event</th><th>Current event</th><th>Decision</th></tr></thead><tbody>
          {preview.rows.map((row) => <tr key={row.row}><td>{row.row} · {row.status}</td>
            <td>{row.values.event_date} · {row.values.equipment_label} · {row.values.action}<small>Cost: {row.values.cost_amount ?? "not recorded"} {row.values.cost_currency ?? ""}</small><details><summary>All imported fields</summary><EventDetails event={row.values} /></details></td>
            <td>{row.before ? `${row.before.event_date} · ${row.before.equipment_label} · ${row.before.action}` : "No existing event"}{row.before && <details><summary>All current fields</summary><EventDetails event={row.before} /></details>}</td>
            <td><select aria-label={`Decision for row ${row.row}`} value={decisions[String(row.row)] ?? "skip"} disabled={["duplicate", "unchanged"].includes(row.status)} onChange={(event) => setDecisions({ ...decisions, [String(row.row)]: event.target.value })}>
              <option value="skip">Skip</option>{row.status === "new" && <option value="create">Create</option>}{row.status === "conflict" && <option value="update">Update existing event</option>}</select></td>
          </tr>)}
        </tbody></table></div>}
        <button type="button" disabled={busy || !preview.preview_id || preview.errors.length > 0} onClick={() => void perform(async () => {
          const result = await mutate("/api/maintenance/csv/apply", { preview_id: preview.preview_id, decisions });
          setMessage(`${result.events?.length ?? 0} maintenance rows imported. Unchanged and skipped rows were preserved.`); setPreview(null); setCSVContent("");
        })}>Import reviewed rows</button>
      </>}
    </div>
  </section>;
}
