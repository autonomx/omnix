import type {
  RpgAuthoringEntityCard,
  RpgAuthoringTopic,
} from '../../api/rpgWorldAuthoringClient';
import { RpgWorldEntityEditor } from './RpgWorldEntityEditor';

interface RpgWorldEntityCardProps {
  entity: RpgAuthoringEntityCard;
  imageAssetId?: string;
  topic?: RpgAuthoringTopic;
  worldId: string;
}

function humanize(value: string): string {
  const candidate = value.includes(':') ? value.split(':').slice(1).join(':') : value;
  return candidate
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function assetUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}

export function formatAuthoringValue(value: unknown): string {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return new Intl.NumberFormat().format(value);
  if (typeof value === 'string') {
    return value.includes(':') || /[_-]/.test(value) ? humanize(value) : value;
  }
  if (Array.isArray(value)) return value.map(formatAuthoringValue).join(', ');
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const label = record.label ?? record.name ?? record.resource ?? record.type;
    const amount = record.value ?? record.amount ?? record.count ?? record.quantity;
    if (label != null && amount != null) {
      return `${formatAuthoringValue(label)}: ${formatAuthoringValue(amount)}`;
    }
    if (label != null) return formatAuthoringValue(label);
    return Object.entries(record)
      .map(([key, item]) => `${humanize(key)}: ${formatAuthoringValue(item)}`)
      .join(' · ');
  }
  return String(value);
}

export function RpgWorldEntityCard({ entity, imageAssetId, topic, worldId }: RpgWorldEntityCardProps) {
  const presentation = entity.presentation ?? {
    variant: entity.card_type || entity.kind,
    eyebrow: humanize(entity.card_type || entity.kind),
    badges: [],
    highlights: [],
    groups: [],
  };
  return (
    <article className={`rpg-authoring-entity-card is-${presentation.variant}`}>
      <div
        className={`rpg-authoring-entity-placeholder${imageAssetId ? ' has-image' : ''}`}
        aria-hidden="true"
        style={imageAssetId ? {
          backgroundImage: `url(${JSON.stringify(assetUrl(imageAssetId))})`,
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          backgroundSize: 'cover',
        } : undefined}
      >
        {!imageAssetId ? entity.title.slice(0, 1).toUpperCase() : null}
      </div>
      <div className="rpg-authoring-entity-card-copy">
        <p className="rpg-authoring-card-eyebrow">{presentation.eyebrow}</p>
        <h3>{entity.title}</h3>
        {presentation.badges.length ? (
          <div className="rpg-authoring-card-badges">
            {presentation.badges.map((badge, index) => (
              <span key={`${formatAuthoringValue(badge)}:${index}`}>{formatAuthoringValue(badge)}</span>
            ))}
          </div>
        ) : null}
        <p>{entity.summary}</p>
        {presentation.highlights.length ? (
          <dl className="rpg-authoring-card-highlights">
            {presentation.highlights.map((highlight) => (
              <div key={highlight.label}>
                <dt>{highlight.label}</dt>
                <dd>{formatAuthoringValue(highlight.value)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {presentation.groups.map((group) => (
          <section className={`rpg-authoring-card-group is-${group.style}`} key={group.label}>
            <h4>{group.label}</h4>
            {group.style === 'chips' ? (
              <div className="rpg-authoring-card-chip-list">
                {group.items.map((item, index) => (
                  <span key={`${formatAuthoringValue(item)}:${index}`}>{formatAuthoringValue(item)}</span>
                ))}
              </div>
            ) : (
              <ul>
                {group.items.map((item, index) => (
                  <li key={`${formatAuthoringValue(item)}:${index}`}>{formatAuthoringValue(item)}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
        <small>{humanize(entity.kind)} · {entity.id}</small>
      </div>
      <details className="rpg-authoring-card-structured">
        <summary>Structured details</summary>
        <pre>{JSON.stringify(entity.metadata, null, 2)}</pre>
      </details>
      {topic ? <RpgWorldEntityEditor entity={entity} topic={topic} worldId={worldId} /> : null}
    </article>
  );
}
