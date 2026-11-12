import { type ReactNode } from 'react';
import { CaretDown } from './JournalIcons';

/** A current-value summary with the existing, mounted editor behind it. */
export default function SettingsGroup({ title, value, description, children, hidden = false, defaultOpen = false }: { title: string; value?: string; description?: string; children: ReactNode; hidden?: boolean; defaultOpen?: boolean }) {
  return <details className="journal-settings-group" hidden={hidden} open={defaultOpen || undefined}>
    <summary><span><strong>{title}</strong>{description && <small>{description}</small>}</span><span className="settings-current-value">{value}</span><CaretDown size={18} aria-hidden="true" /></summary>
    <div className="journal-settings-editor">{children}</div>
  </details>;
}
