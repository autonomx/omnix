import type { RpgAuthoringSection } from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import { RpgWorldGenerationPanel } from './RpgWorldGenerationPanel';

interface RpgWorldGenerationDashboardProps {
  generation?: RpgWorldGenerationRun | Record<string, never>;
  onOpenImages?: () => void;
  sections: RpgAuthoringSection[];
  worldId: string;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function label(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RpgWorldGenerationDashboard({
  generation,
  onOpenImages,
  sections,
  worldId,
}: RpgWorldGenerationDashboardProps) {
  const run = generation && 'run_id' in generation ? generation as RpgWorldGenerationRun : undefined;
  const progress = record(run?.progress);
  const percent = Number(progress.percent ?? 0);
  const active = new Set(stringArray(progress.active_topic_ids));
  const failed = new Set(stringArray(progress.failed_topic_ids));
  const complete = sections.filter((section) => section.operational_status === 'complete').length;
  const waiting = sections.filter((section) => ['waiting', 'empty'].includes(section.operational_status)).length;
  const topicRows = sections.filter((section) => section.supports_generation);
  const provider = String(record(run?.settings).provider_route ?? record(run?.context).provider_route ?? 'configured');
  const model = String(record(run?.settings).model ?? record(run?.context).model ?? 'configured');

  return (
    <div className="rpg-generation-dashboard">
      <section className="rpg-authoring-page rpg-generation-dashboard-summary" aria-label="Generation status dashboard">
        <div className="rpg-authoring-page-heading">
          <div><p className="eyebrow">World forge</p><h2>Generation Dashboard</h2><p>Track every topic, retry failures, and inspect the active provider without reading raw run data.</p></div>
          <span>{run ? label(run.status) : 'Not started'} · {Math.round(percent)}%</span>
        </div>
        <div className="rpg-generation-dashboard-metrics">
          <article><strong>{complete}</strong><span>Complete</span></article>
          <article><strong>{active.size}</strong><span>Generating</span></article>
          <article><strong>{failed.size}</strong><span>Failed</span></article>
          <article><strong>{waiting}</strong><span>Waiting</span></article>
        </div>
        <div className="rpg-generation-dashboard-progress" aria-label={`${Math.round(percent)} percent complete`}><span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} /></div>
        <div className="rpg-generation-dashboard-layout">
          <section>
            <h3>Topic progress</h3>
            <div className="rpg-generation-dashboard-topic-list">
              {topicRows.map((section) => (
                <article className={`is-${section.operational_status}`} key={section.id}>
                  <div><strong>{section.label}</strong><small>{label(section.editorial_status)}</small></div>
                  <span>{active.has(section.id) ? 'Generating' : failed.has(section.id) ? 'Failed' : label(section.operational_status)}</span>
                </article>
              ))}
            </div>
          </section>
          <aside>
            <h3>Active route</h3>
            <dl>
              <div><dt>Provider</dt><dd>{provider}</dd></div>
              <div><dt>Model</dt><dd>{model}</dd></div>
              <div><dt>Run ID</dt><dd>{run?.run_id ?? '—'}</dd></div>
              <div><dt>Updated</dt><dd>{run?.updated_at ? new Date(run.updated_at).toLocaleString() : '—'}</dd></div>
            </dl>
            {failed.size ? <p className="rpg-world-catalog-error">{failed.size} topic{failed.size === 1 ? '' : 's'} exhausted automatic retries.</p> : <p>No terminal topic failures.</p>}
          </aside>
        </div>
      </section>
      <details className="rpg-generation-dashboard-controls" open={!run}>
        <summary>Generation controls and advanced settings</summary>
        <RpgWorldGenerationPanel generation={generation} onOpenImages={onOpenImages} sections={sections} worldId={worldId} />
      </details>
    </div>
  );
}
