import type { RpgAuthoringDocumentBlock } from '../../api/rpgWorldAuthoringClient';
import { formatAuthoringValue } from './RpgWorldEntityCard';

const PRIMARY_FIELDS = new Set([
  'label',
  'name',
  'title',
  'key',
  'value',
  'statement',
  'content',
  'fact',
  'object',
  'description',
  'summary',
  'badges',
  'references',
  'details',
  'entity_refs',
  'entities',
  'visibility',
  'authority',
  'approved_authority',
  'status',
]);

function humanize(value: string): string {
  const candidate = value.includes(':') ? value.split(':').slice(1).join(':') : value;
  return candidate
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function meaningful(value: unknown): boolean {
  if (value == null || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function recordLabel(item: Record<string, unknown>, index: number, fallback: string): string {
  const value = item.label
    ?? item.name
    ?? item.title
    ?? item.key
    ?? item.fact_id
    ?? item.relationship_id
    ?? item.rule_id
    ?? item.thread_id
    ?? item.id;
  return value == null || String(value).trim() === '' ? `${fallback} ${index + 1}` : humanize(String(value));
}

function recordValue(item: Record<string, unknown>): unknown {
  return item.value
    ?? item.statement
    ?? item.content
    ?? item.fact
    ?? item.description
    ?? item.summary
    ?? item.object
    ?? 'No description was provided.';
}

function recordBadges(item: Record<string, unknown>): unknown[] {
  const explicit = Array.isArray(item.badges) ? item.badges : [];
  return [
    ...explicit,
    item.visibility,
    item.approved_authority ?? item.authority,
    item.status,
  ].filter(meaningful);
}

function referenceRows(value: unknown): Array<{ id: string; role: string }> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (item && typeof item === 'object') {
      const row = item as Record<string, unknown>;
      const id = row.id ?? row.entity_id ?? row.ref;
      if (!meaningful(id)) return [];
      return [{
        id: String(id),
        role: meaningful(row.role ?? row.relationship ?? row.kind)
          ? String(row.role ?? row.relationship ?? row.kind)
          : '',
      }];
    }
    return meaningful(item) ? [{ id: String(item), role: '' }] : [];
  });
}

function detailRows(item: Record<string, unknown>): Array<{ label: string; value: unknown }> {
  if (Array.isArray(item.details)) {
    return item.details.flatMap((entry) => {
      if (!entry || typeof entry !== 'object') return [];
      const detail = entry as Record<string, unknown>;
      return meaningful(detail.value)
        ? [{ label: String(detail.label ?? 'Detail'), value: detail.value }]
        : [];
    });
  }
  return Object.entries(item)
    .filter(([key, value]) => !PRIMARY_FIELDS.has(key) && meaningful(value))
    .map(([key, value]) => ({ label: humanize(key), value }));
}

function MetaChips({ values }: { values: unknown[] }) {
  return values.length ? (
    <div className="rpg-authoring-record-badges">
      {values.map((value, index) => (
        <span key={`${formatAuthoringValue(value)}:${index}`}>{formatAuthoringValue(value)}</span>
      ))}
    </div>
  ) : null;
}

function StructuredRecord({
  fallback,
  index,
  item,
}: {
  fallback: string;
  index: number;
  item: Record<string, unknown>;
}) {
  const references = referenceRows(item.references ?? item.entity_refs ?? item.entities);
  const details = detailRows(item);
  return (
    <article className="rpg-authoring-record-card">
      <header>
        <p className="rpg-authoring-card-eyebrow">{recordLabel(item, index, fallback)}</p>
        <MetaChips values={recordBadges(item)} />
      </header>
      <p className="rpg-authoring-record-statement">{formatAuthoringValue(recordValue(item))}</p>
      {references.length ? (
        <section className="rpg-authoring-record-references">
          <h4>References</h4>
          <div className="rpg-authoring-card-chip-list">
            {references.map((reference) => (
              <span key={`${reference.id}:${reference.role}`}>
                {humanize(reference.id)}{reference.role ? ` · ${humanize(reference.role)}` : ''}
              </span>
            ))}
          </div>
        </section>
      ) : null}
      {details.length ? (
        <dl className="rpg-authoring-record-details">
          {details.map((detail) => (
            <div key={detail.label}><dt>{detail.label}</dt><dd>{formatAuthoringValue(detail.value)}</dd></div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}

function RecordBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  const items = block.items ?? [];
  const fallback = block.kind === 'facts' ? 'Fact' : 'Entry';
  return (
    <section className="rpg-authoring-document-block is-record-collection">
      {block.title ? <h3>{block.title}</h3> : null}
      <div className="rpg-authoring-record-grid">
        {items.map((item, index) => (
          <StructuredRecord fallback={fallback} index={index} item={item} key={`${recordLabel(item, index, fallback)}:${index}`} />
        ))}
      </div>
    </section>
  );
}

function SectionBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  const metadata = (block.items ?? []).filter((item) => meaningful(item.value));
  return (
    <section className="rpg-authoring-document-block is-prose">
      {block.title ? <h3>{block.title}</h3> : null}
      <div className="rpg-authoring-prose" style={{ whiteSpace: 'pre-line' }}>{block.body || ''}</div>
      {metadata.length ? (
        <dl className="rpg-authoring-section-metadata">
          {metadata.map((item, index) => (
            <div key={`${String(item.label ?? index)}`}>
              <dt>{String(item.label ?? `Detail ${index + 1}`)}</dt>
              <dd>{formatAuthoringValue(item.value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

export function RpgWorldDocumentBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  if (block.kind === 'facts' || block.kind === 'records') return <RecordBlock block={block} />;
  if (block.kind === 'json') {
    return (
      <details className="rpg-authoring-structured-data">
        <summary>{block.title || 'Advanced structured canon'}</summary>
        <pre>{JSON.stringify(block.value, null, 2)}</pre>
      </details>
    );
  }
  return <SectionBlock block={block} />;
}
