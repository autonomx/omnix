import type {
  RpgAuthoringEntityCard,
  RpgAuthoringTopic,
} from '../../api/rpgWorldAuthoringClient';
import { RpgWorldEntityEditor } from './RpgWorldEntityEditor';
import { formatAuthoringValue } from './RpgWorldEntityCard';
import './RpgWorldRichPresentation.css';

interface RpgWorldEntityDetailProps {
  entity: RpgAuthoringEntityCard;
  imageAssetId?: string;
  onClose: () => void;
  topic?: RpgAuthoringTopic;
  worldId: string;
}

const RESERVED_FIELDS = new Set([
  'id',
  'entity_id',
  'name',
  'title',
  'label',
  'kind',
  'description',
  'summary',
  'visibility',
  'schema_version',
]);

function humanize(value: string): string {
  const candidate = value.includes(':') ? value.split(':').slice(1).join(':') : value;
  return candidate
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function assetUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}

function meaningful(value: unknown): boolean {
  if (value == null || value === '') return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function fieldStyle(key: string, value: unknown): 'chips' | 'list' | 'facts' {
  if (!Array.isArray(value)) return 'facts';
  if (/(^|_)(ids?|refs?|tags?|languages?|regions?|locations?|factions?|classes?|schools?)$/.test(key)) {
    return 'chips';
  }
  return value.some((item) => typeof item === 'object') ? 'facts' : 'list';
}

function DetailValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <ul>
        {value.map((item, index) => (
          <li key={`${formatAuthoringValue(item)}:${index}`}>{formatAuthoringValue(item)}</li>
        ))}
      </ul>
    );
  }
  if (value && typeof value === 'object') {
    return (
      <dl className="rpg-authoring-detail-nested-facts">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}><dt>{humanize(key)}</dt><dd>{formatAuthoringValue(item)}</dd></div>
        ))}
      </dl>
    );
  }
  return <p>{formatAuthoringValue(value)}</p>;
}

export function RpgWorldEntityDetail({
  entity,
  imageAssetId,
  onClose,
  topic,
  worldId,
}: RpgWorldEntityDetailProps) {
  const presentation = entity.presentation;
  const representedFields = new Set<string>();
  for (const highlight of presentation.highlights) representedFields.add(highlight.label.toLowerCase().replace(/\s+/g, '_'));
  for (const group of presentation.groups) representedFields.add(group.label.toLowerCase().replace(/\s+/g, '_'));

  const remainingFields = Object.entries(entity.metadata)
    .filter(([key, value]) => !RESERVED_FIELDS.has(key) && meaningful(value))
    .filter(([key]) => !representedFields.has(key))
    .sort(([left], [right]) => left.localeCompare(right));

  return (
    <div className="rpg-authoring-detail-backdrop is-routed-subpage">
      <main
        aria-label={`${entity.title} details`}
        className="rpg-authoring-entity-detail"
      >
        <header className="rpg-authoring-entity-detail-header">
          <div>
            <button className="rpg-authoring-detail-breadcrumb" type="button" onClick={onClose}>← Back to {humanize(entity.card_type || entity.kind)}</button>
            <p className="rpg-authoring-card-eyebrow">{presentation.eyebrow}</p>
            <h2>{entity.title}</h2>
          </div>
          <button aria-label={`Close ${entity.title} details`} className="rpg-secondary-button" type="button" onClick={onClose}>Close</button>
        </header>

        <div className="rpg-authoring-entity-detail-hero">
          <div
            className={`rpg-authoring-entity-detail-art${imageAssetId ? ' has-image' : ''}`}
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
          <div className="rpg-authoring-entity-detail-intro">
            {presentation.badges.length ? (
              <div className="rpg-authoring-card-badges">
                {presentation.badges.map((badge, index) => (
                  <span key={`${formatAuthoringValue(badge)}:${index}`}>{formatAuthoringValue(badge)}</span>
                ))}
              </div>
            ) : null}
            <p>{entity.summary || 'No overview has been written yet.'}</p>
            <small>{humanize(entity.kind)} · {entity.id}</small>
          </div>
        </div>

        {presentation.highlights.length ? (
          <section className="rpg-authoring-detail-section">
            <h3>At a glance</h3>
            <dl className="rpg-authoring-card-highlights">
              {presentation.highlights.map((highlight) => (
                <div key={highlight.label}><dt>{highlight.label}</dt><dd>{formatAuthoringValue(highlight.value)}</dd></div>
              ))}
            </dl>
          </section>
        ) : null}

        {presentation.groups.map((group) => (
          <section className="rpg-authoring-detail-section" key={group.label}>
            <h3>{group.label}</h3>
            {group.style === 'chips' ? (
              <div className="rpg-authoring-card-chip-list">
                {group.items.map((item, index) => (
                  <span key={`${formatAuthoringValue(item)}:${index}`}>{formatAuthoringValue(item)}</span>
                ))}
              </div>
            ) : (
              <DetailValue value={group.items} />
            )}
          </section>
        ))}

        {remainingFields.length ? (
          <section className="rpg-authoring-detail-section">
            <h3>Additional details</h3>
            <div className="rpg-authoring-detail-field-grid">
              {remainingFields.map(([key, value]) => (
                <article className={`is-${fieldStyle(key, value)}`} key={key}>
                  <h4>{humanize(key)}</h4>
                  {fieldStyle(key, value) === 'chips' && Array.isArray(value) ? (
                    <div className="rpg-authoring-card-chip-list">
                      {value.map((item, index) => (
                        <span key={`${formatAuthoringValue(item)}:${index}`}>{formatAuthoringValue(item)}</span>
                      ))}
                    </div>
                  ) : <DetailValue value={value} />}
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {topic ? <RpgWorldEntityEditor entity={entity} topic={topic} worldId={worldId} /> : null}
        <details className="rpg-authoring-structured-data">
          <summary>Advanced structured data</summary>
          <pre>{JSON.stringify(entity.metadata, null, 2)}</pre>
        </details>
      </main>
    </div>
  );
}
