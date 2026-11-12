export type EvidenceRecord = {
  id?: string | number;
  name?: string;
  activity_type?: string;
  local_date?: string;
  url?: string;
  category?: string;
  exercise?: string;
  planning_metadata?: {equipment?: string};
  similarity_score?: number;
  route_overlap_percent?: number;
  direction?: string;
};

export function evidenceDate(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const day = value.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  const date = new Date(`${day}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== day) return null;
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  }).format(date);
}

export default function ChatEvidenceRecords({tool, records = [], reference}: {
  tool: string;
  records?: EvidenceRecord[];
  reference?: EvidenceRecord;
}) {
  const items = Array.isArray(records)
    ? records.filter(record => record && typeof record === 'object').slice(0, 6)
    : [];
  if (!items.length && !reference) return null;

  function recordText(record: EvidenceRecord) {
    const name = typeof record.name === 'string' ? record.name
      : typeof record.activity_type === 'string' ? record.activity_type.replaceAll('_', ' ')
      : typeof record.exercise === 'string' ? record.exercise.replaceAll('_', ' ')
      : 'Record';
    if (tool === 'get_garmin_strength_catalog') {
      return <>{name}
        {typeof record.category === 'string' ? ` · ${record.category.replaceAll('_', ' ').toLowerCase()}` : ''}
        {typeof record.planning_metadata?.equipment === 'string' ? ` · ${record.planning_metadata.equipment.replaceAll('_', ' ')}` : ''}
      </>;
    }
    const date = evidenceDate(record.local_date);
    return <>{name}{date ? ` · ${date}` : ''}
      {typeof record.similarity_score === 'number' && Number.isFinite(record.similarity_score) ? ` · ${record.similarity_score.toFixed(0)}% similarity` : ''}
      {typeof record.route_overlap_percent === 'number' && Number.isFinite(record.route_overlap_percent) ? ` · ${record.route_overlap_percent.toFixed(0)}% route overlap` : ''}
      {typeof record.direction === 'string' ? ` · ${record.direction}` : ''}
    </>;
  }

  return <div className="evidence-links">
    {reference && <span>Reference: {recordText(reference)}</span>}
    {items.map((record, index) => <span key={record.id ?? `${record.category ?? ''}:${record.exercise ?? ''}:${index}`}>
      {recordText(record)}
    </span>)}
  </div>;
}
