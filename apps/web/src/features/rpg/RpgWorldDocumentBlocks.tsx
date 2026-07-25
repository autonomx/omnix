import type { RpgAuthoringDocumentBlock } from '../../api/rpgWorldAuthoringClient';
import { formatAuthoringValue } from './RpgWorldEntityCard';
import './RpgWorldTimeline.css';

const PRIMARY_FIELDS = new Set([
  'id',
  'fact_id',
  'relationship_id',
  'rule_id',
  'thread_id',
  'document_id',
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
  'expanded_description',
  'long_description',
  'lore',
  'context',
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
  const value = item.label ?? item.name ?? item.title ?? item.key ?? item.era ?? item.date;
  return value == null || String(value).trim() === ''
    ? `${fallback} ${index + 1}`
    : humanize(String(value));
}

function recordValue(item: Record<string, unknown>): unknown {
  return item.value
    ?? item.statement
    ?? item.content
    ?? item.fact
    ?? item.description
    ?? item.summary
    ?? item.body
    ?? item.object
    ?? 'No description was provided.';
}

function visibleBadge(value: unknown): unknown | undefined {
  if (!meaningful(value)) return undefined;
  if (typeof value === 'string' && value.includes(':')) return undefined;
  return value;
}

function recordBadges(item: Record<string, unknown>): unknown[] {
  const explicit = Array.isArray(item.badges) ? item.badges : [];
  const authority = visibleBadge(item.approved_authority ?? item.authority);
  return [
    ...explicit,
    item.era,
    item.date,
    item.visibility,
    authority,
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

function readableRecordValue(value: unknown): string {
  return typeof value === 'string' ? value : formatAuthoringValue(value);
}

function proseParagraphs(value: unknown): string[] {
  const rendered = readableRecordValue(value).trim();
  if (!rendered) return [];
  const explicit = rendered
    .split(/\n\s*\n/g)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  return explicit.length ? explicit : [rendered];
}

function Prose({ value, className = '' }: { value: unknown; className?: string }) {
  const paragraphs = proseParagraphs(value);
  return (
    <div className={`rpg-authoring-prose${className ? ` ${className}` : ''}`}>
      {paragraphs.map((paragraph, index) => <p key={`${paragraph.slice(0, 48)}:${index}`}>{paragraph}</p>)}
    </div>
  );
}

function expandedLoreParagraphs(item: Record<string, unknown>): string[] {
  const value = item.expanded_description
    ?? item.long_description
    ?? item.lore
    ?? item.context;
  return value == null ? [] : proseParagraphs(value).slice(0, 2);
}

function ExpandableLore({ item }: { item: Record<string, unknown> }) {
  const paragraphs = expandedLoreParagraphs(item);
  if (!paragraphs.length) return null;
  return (
    <details className="rpg-authoring-record-expansion">
      <summary>
        <span className="rpg-authoring-record-expand-label is-collapsed">Read more</span>
        <span className="rpg-authoring-record-expand-label is-expanded">Show less</span>
      </summary>
      <div className="rpg-authoring-record-expanded-prose">
        {paragraphs.map((paragraph, index) => <p key={`${paragraph.slice(0, 48)}:${index}`}>{paragraph}</p>)}
      </div>
    </details>
  );
}

function MetaChips({ values }: { values: unknown[] }) {
  return values.length ? (
    <div className="rpg-authoring-record-badges">
      {values.map((value, index) => {
        const label = typeof value === 'string' ? humanize(value) : formatAuthoringValue(value);
        return <span key={`${label}:${index}`}>{label}</span>;
      })}
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
      <Prose className="rpg-authoring-record-statement" value={recordValue(item)} />
      <ExpandableLore item={item} />
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

function timelineMarker(item: Record<string, unknown>, index: number): string {
  const start = item.start_year;
  const end = item.end_year;
  if (meaningful(start) && meaningful(end)) return `${String(start)}–${String(end)}`;
  const value = item.date_label
    ?? item.date
    ?? item.year
    ?? item.era
    ?? item.epoch
    ?? item.period
    ?? item.range
    ?? item.season
    ?? item.month;
  return meaningful(value) ? String(value) : `Entry ${index + 1}`;
}

function timelineOrder(item: Record<string, unknown>, index: number): number {
  const value = item.chronology_index
    ?? item.sequence
    ?? item.start_year
    ?? item.year;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : Number.MAX_SAFE_INTEGER + index;
}

function timelineItems(block: RpgAuthoringDocumentBlock): Array<Record<string, unknown>> {
  let items: Array<Record<string, unknown>> = [];
  if (block.items?.length) items = [...block.items];
  else if (block.body) items = [{ title: block.title ?? 'Chronicle entry', body: block.body }];
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => timelineOrder(left.item, left.index) - timelineOrder(right.item, right.index))
    .map(({ item }) => item);
}

function TimelineBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  const items = timelineItems(block);
  return (
    <section className="rpg-authoring-document-block is-record-collection is-timeline">
      {block.title ? <h3>{block.title}</h3> : null}
      <ol className="rpg-authoring-timeline-list">
        {items.map((item, index) => (
          <li key={`${recordLabel(item, index, 'Event')}:${index}`}>
            <div className="rpg-authoring-timeline-marker">
              <span>{timelineMarker(item, index)}</span>
            </div>
            <StructuredRecord fallback="Event" index={index} item={item} />
          </li>
        ))}
      </ol>
    </section>
  );
}

function RecordBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  if (block.kind === 'timeline') return <TimelineBlock block={block} />;
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
  const realmSummary = block.kind === 'realm-summary';
  return (
    <section className={`rpg-authoring-document-block is-prose${realmSummary ? ' is-realm-summary' : ''}`}>
      {block.title ? <h3>{block.title}</h3> : null}
      <Prose value={block.body || ''} />
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
  if (block.kind === 'facts' || block.kind === 'records' || block.kind === 'timeline') return <RecordBlock block={block} />;
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
