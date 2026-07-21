import type {
  RpgAuthoringDocumentPage,
  RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldSummary } from '../../api/rpgWorldLibraryClient';
import { RpgWorldDocumentBlock } from './RpgWorldDocumentBlocks';

interface RpgWorldOverviewDashboardProps {
  bannerAssetId?: string;
  onEdit: () => void;
  onOpenSection?: (sectionId: string) => void;
  page: RpgAuthoringDocumentPage;
  sections: RpgAuthoringSection[];
  world: RpgWorldSummary;
}

function assetUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}

function label(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RpgWorldOverviewDashboard({
  bannerAssetId,
  onEdit,
  onOpenSection,
  page,
  sections,
  world,
}: RpgWorldOverviewDashboardProps) {
  const generated = sections.filter((section) => section.operational_status === 'complete').length;
  const failed = sections.filter((section) => section.operational_status === 'failed').length;
  const totalEntities = sections.reduce((total, section) => total + section.entity_count, 0);
  const lore = sections.filter((section) => section.group === 'lore');
  const loreComplete = lore.filter((section) => section.operational_status === 'complete').length;
  const featured = sections
    .filter((section) => section.group === 'world' && section.entity_count > 0)
    .sort((left, right) => right.entity_count - left.entity_count)
    .slice(0, 4);
  const generation = world.generation;
  const progress = generation?.progress ?? {};
  const percent = Number(progress.percent ?? (generated / Math.max(1, sections.length)) * 100);

  return (
    <section className="rpg-authoring-page rpg-world-overview-dashboard">
      <div
        className={`rpg-world-overview-hero${bannerAssetId ? ' has-image' : ''}`}
        style={bannerAssetId ? {
          backgroundImage: `linear-gradient(90deg, rgba(3, 6, 18, 0.94), rgba(3, 6, 18, 0.28)), url(${JSON.stringify(assetUrl(bannerAssetId))})`,
        } : undefined}
      >
        <div>
          <p className="eyebrow">World overview</p>
          <h2>{world.title}</h2>
          <p>{world.description || page.summary || 'No world summary has been written yet.'}</p>
          <div className="rpg-world-overview-badges">
            <span>{label(world.genre)}</span><span>{label(world.tone)}</span><span>{label(world.status)}</span>
          </div>
        </div>
        <button className="rpg-secondary-button" type="button" onClick={onEdit}>Edit overview</button>
      </div>

      <div className="rpg-world-overview-metrics" aria-label="World statistics">
        <article><strong>{Math.round(percent)}%</strong><span>Generation progress</span></article>
        <article><strong>{generated}/{sections.length}</strong><span>Sections complete</span></article>
        <article><strong>{totalEntities}</strong><span>Structured entries</span></article>
        <article><strong>{loreComplete}/{lore.length}</strong><span>Lore chapters complete</span></article>
      </div>

      <div className="rpg-world-overview-columns">
        <section className="rpg-world-overview-panel">
          <div className="rpg-authoring-page-heading"><div><p className="eyebrow">Canon</p><h3>World dossier</h3></div></div>
          {page.body.length ? page.body.map((block, index) => (
            <RpgWorldDocumentBlock block={block} key={`${block.kind}:${index}`} />
          )) : <p>No overview canon has been generated.</p>}
        </section>

        <aside className="rpg-world-overview-panel">
          <div className="rpg-authoring-page-heading"><div><p className="eyebrow">Status</p><h3>Authoring health</h3></div></div>
          <dl className="rpg-world-overview-status-list">
            <div><dt>Generation</dt><dd>{label(generation?.status || 'not started')}</dd></div>
            <div><dt>Draft revision</dt><dd>{world.draft_revision}</dd></div>
            <div><dt>Failed sections</dt><dd>{failed}</dd></div>
            <div><dt>Last updated</dt><dd>{new Date(world.updated_at).toLocaleString()}</dd></div>
          </dl>
          <div className="rpg-world-overview-progress"><span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} /></div>
          {onOpenSection ? <button type="button" onClick={() => onOpenSection('generation')}>Open generation dashboard</button> : null}
        </aside>
      </div>

      <section className="rpg-world-overview-panel">
        <div className="rpg-authoring-page-heading"><div><p className="eyebrow">Explore</p><h3>Featured collections</h3></div></div>
        <div className="rpg-world-overview-feature-grid">
          {featured.map((section) => (
            <button key={section.id} type="button" onClick={() => onOpenSection?.(section.id)}>
              <span>{section.label}</span><strong>{section.entity_count}</strong><small>{label(section.operational_status)}</small>
            </button>
          ))}
          {!featured.length ? <p>Generate world collections to populate this area.</p> : null}
        </div>
      </section>
    </section>
  );
}
