import { useRef, useState } from 'react';
import type { RpgAuthoringSection } from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import {
  RpgWorldGenerationPanel,
  type RpgWorldGenerationPanelHandle,
} from './RpgWorldGenerationPanel';
import './RpgWorldGenerationDashboardDesign.css';

interface RpgWorldGenerationDashboardProps {
  generation?: RpgWorldGenerationRun | Record<string, never>;
  onOpenImages?: () => void;
  onOpenSection?: (sectionId: string) => void;
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

function statusIcon(status: string): string {
  if (status === 'complete') return '✓';
  if (status === 'failed') return '!';
  if (status === 'generating') return '↗';
  return '◷';
}

export function RpgWorldGenerationDashboard({
  generation,
  onOpenImages,
  onOpenSection,
  sections,
  worldId,
}: RpgWorldGenerationDashboardProps) {
  const [view, setView] = useState<'board' | 'timeline'>('board');
  const [controlsOpen, setControlsOpen] = useState(false);
  const panelRef = useRef<RpgWorldGenerationPanelHandle>(null);
  const run = generation && 'run_id' in generation ? generation as RpgWorldGenerationRun : undefined;
  const progress = record(run?.progress);
  const percent = Number(progress.percent ?? 0);
  const active = new Set(stringArray(progress.active_topic_ids));
  const failed = new Set(stringArray(progress.failed_topic_ids));
  const topicRows = sections.filter((section) => section.supports_generation);
  const complete = topicRows.filter((section) => section.operational_status === 'complete').length;
  const waiting = topicRows.filter((section) => ['waiting', 'empty'].includes(section.operational_status)).length;
  const provider = String(record(run?.settings).provider_route ?? record(run?.context).provider_route ?? 'configured');
  const model = String(record(run?.settings).model ?? record(run?.context).model ?? 'configured');
  const runError = record(run?.error);
  const errorText = String(runError.message ?? runError.error ?? runError.detail ?? 'A topic exhausted its automatic retries.');
  const imageSections = sections.filter((section) => section.supports_images);
  const imageReady = imageSections.filter((section) => section.operational_status === 'complete').length;

  const rows = topicRows.map((section) => {
    const status = active.has(section.id)
      ? 'generating'
      : failed.has(section.id)
        ? 'failed'
        : section.operational_status;
    return {
      ...section,
      displayStatus: status,
    };
  });

  const openControls = () => {
    setControlsOpen(true);
    window.requestAnimationFrame(() => {
      document.getElementById('generation-controls')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  return (
    <div className="rpg-generation-dashboard is-operational-dashboard">
      <section className="rpg-generation-dashboard-header" aria-label="Generation status dashboard">
        <div className="rpg-generation-dashboard-title">
          <span className="rpg-generation-dashboard-emblem" aria-hidden="true">✥</span>
          <div>
            <p className="eyebrow">World forge</p>
            <h2>World Generation</h2>
            <div className="rpg-generation-dashboard-live-status">
              <strong>{run ? label(run.status) : 'Not started'}</strong>
              <span>·</span>
              <span>{run ? `Generating world content across ${topicRows.length} topics` : 'Configure a generation run to begin.'}</span>
              <div aria-label={`${Math.round(percent)} percent complete`}><i style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} /></div>
              <b>{Math.round(percent)}%</b>
            </div>
          </div>
        </div>
        <aside className="rpg-generation-provider-card">
          <span>Provider</span><strong>{label(provider)}</strong>
          <span>Model</span><strong>{model || 'Provider default'}</strong>
          <small>{run?.run_id ?? 'No active run'}</small>
        </aside>
      </section>

      <div className="rpg-generation-primary-actions">
        <button type="button" onClick={() => panelRef.current?.generateWorld()}>✦ Generate World</button>
        <button type="button" onClick={openControls}>Generate Selected</button>
        <button type="button" onClick={() => panelRef.current?.regenerateStale()}>Regenerate Stale</button>
        <button type="button" disabled={!failed.size} onClick={() => panelRef.current?.retryFailed()}>Retry Failed{failed.size ? ` (${failed.size})` : ''}</button>
        <button type="button" disabled={run?.status !== 'review'} onClick={() => panelRef.current?.publish()}>Publish World</button>
        {onOpenImages ? <button type="button" onClick={onOpenImages}>Generate Images</button> : null}
      </div>

      <div className="rpg-generation-dashboard-layout">
        <section className="rpg-generation-topic-board">
          <header>
            <h3>Topic Generation Progress</h3>
            <div className="rpg-generation-status-chips">
              <span>Total <b>{topicRows.length}</b></span>
              <span className="is-complete">Completed <b>{complete}</b></span>
              <span className="is-generating">In Progress <b>{active.size}</b></span>
              <span className="is-failed">Failed <b>{failed.size}</b></span>
              <span>Queued <b>{waiting}</b></span>
            </div>
            <div className="rpg-generation-view-toggle">
              <button className={view === 'board' ? 'is-active' : ''} type="button" onClick={() => setView('board')}>Board</button>
              <button className={view === 'timeline' ? 'is-active' : ''} type="button" onClick={() => setView('timeline')}>Timeline</button>
            </div>
          </header>

          {view === 'board' ? (
            <div className="rpg-generation-topic-table" role="table" aria-label="Topic generation progress">
              <div className="rpg-generation-topic-table-head" role="row">
                <span role="columnheader">Topic</span><span role="columnheader">Status</span><span role="columnheader">Progress</span><span role="columnheader">Last Updated</span><span role="columnheader">Details</span><span role="columnheader">Actions</span>
              </div>
              {rows.map((section) => {
                const completeRow = section.displayStatus === 'complete';
                const generatingRow = section.displayStatus === 'generating';
                return (
                  <div className={`rpg-generation-topic-table-row is-${section.displayStatus}`} role="row" key={section.id}>
                    <div role="cell"><span className="rpg-generation-topic-icon">{statusIcon(section.displayStatus)}</span><strong>{section.label}</strong></div>
                    <span role="cell" className="rpg-generation-topic-status">{label(section.displayStatus)}</span>
                    <div role="cell" className={`rpg-generation-row-progress${generatingRow ? ' is-indeterminate' : ''}`}><i style={{ width: completeRow || generatingRow ? '100%' : '0%' }} /><small>{completeRow ? '100%' : generatingRow ? 'Provider call in progress' : '0%'}</small></div>
                    <span role="cell">{active.has(section.id) || failed.has(section.id) ? (run?.updated_at ? new Date(run.updated_at).toLocaleString() : '—') : '—'}</span>
                    <span role="cell">{section.entity_count ? `${section.entity_count} structured entries` : section.displayStatus === 'failed' ? errorText : 'Queued for generation'}</span>
                    <div role="cell">
                      <button type="button" aria-label={`View ${section.label}`} onClick={() => onOpenSection?.(section.id)}>◉</button>
                      <button type="button" aria-label={`Generation settings for ${section.label}`} onClick={openControls}>⋮</button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <ol className="rpg-generation-timeline">
              {rows.map((section) => <li className={`is-${section.displayStatus}`} key={section.id}><span>{statusIcon(section.displayStatus)}</span><div><strong>{section.label}</strong><p>{label(section.displayStatus)}{section.entity_count ? ` · ${section.entity_count} entries` : ''}</p></div></li>)}
            </ol>
          )}
        </section>

        <aside className="rpg-generation-dashboard-side">
          <section className="rpg-generation-diagnostics-card">
            <header><h3>Diagnostics &amp; Activity</h3><span>{run?.updated_at ? new Date(run.updated_at).toLocaleTimeString() : '—'}</span></header>
            {failed.size ? (
              <article className="rpg-generation-last-error"><small>Last Error</small><strong>{Array.from(failed).map(label).join(', ')} failed</strong><p>{errorText}</p><button type="button" onClick={() => panelRef.current?.retryFailed()}>Retry Now</button></article>
            ) : <p className="rpg-generation-no-error">No terminal topic failures.</p>}
            <div className="rpg-generation-activity-stream">
              {rows.filter((section) => section.displayStatus !== 'waiting' && section.displayStatus !== 'empty').slice(0, 7).map((section) => <div key={section.id}><span>{statusIcon(section.displayStatus)}</span><p><strong>{section.label}</strong> {label(section.displayStatus).toLowerCase()}</p></div>)}
            </div>
          </section>

          <section className="rpg-generation-image-card">
            <header><h3>Image Generation</h3><button type="button" onClick={onOpenImages}>View all</button></header>
            <div><article><small>Targets</small><strong>{imageSections.length}</strong></article><article><small>Ready</small><strong>{imageReady}</strong></article><article><small>Pending</small><strong>{Math.max(0, imageSections.length - imageReady)}</strong></article></div>
            {onOpenImages ? <button type="button" onClick={onOpenImages}>Go to Images →</button> : null}
          </section>
        </aside>
      </div>

      <details
        className="rpg-generation-dashboard-controls"
        id="generation-controls"
        open={!run || controlsOpen}
        onToggle={(event) => setControlsOpen(event.currentTarget.open)}
      >
        <summary>Generation controls and advanced settings</summary>
        <RpgWorldGenerationPanel
          ref={panelRef}
          generation={generation}
          onOpenImages={onOpenImages}
          sections={sections}
          worldId={worldId}
        />
      </details>
    </div>
  );
}
