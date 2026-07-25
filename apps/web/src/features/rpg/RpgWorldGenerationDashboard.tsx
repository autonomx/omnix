import { useRef, useState } from 'react';
import type { RpgAuthoringSection, RpgWorldTokenUsage } from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import {
  RpgWorldGenerationPanel,
  type RpgWorldGenerationPanelHandle,
} from './RpgWorldGenerationPanel';
import { RpgWorldProfilePreview } from './RpgWorldProfilePreview';
import './RpgWorldGenerationDashboardDesign.css';

interface RpgWorldGenerationDashboardProps {
  generation?: RpgWorldGenerationRun | Record<string, never>;
  onOpenImages?: () => void;
  onOpenSection?: (sectionId: string) => void;
  sections: RpgAuthoringSection[];
  tokenUsage?: RpgWorldTokenUsage;
  worldId: string;
}

type PrimaryAction = 'full' | 'selected' | 'stale' | 'retry' | 'continue' | 'publish' | 'images';

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

function isPartialReviewRun(run: RpgWorldGenerationRun | undefined): boolean {
  if (run?.status !== 'review') return false;
  const planned = stringArray(record(run.plan).topic_ids);
  const nodes = record(run.graph).nodes;
  return planned.length > 0 && Array.isArray(nodes) && nodes.length > planned.length;
}

function primaryActionLabel(action: PrimaryAction): string {
  return {
    full: 'Generate World',
    selected: 'Generate Selected',
    stale: 'Regenerate Stale',
    retry: 'Retry Failed',
    continue: 'Continue Generation',
    publish: 'Publish World',
    images: 'Generate Images',
  }[action];
}

function tokenLabel(value: number): string {
  return new Intl.NumberFormat().format(Math.max(0, Math.round(value)));
}

export function RpgWorldGenerationDashboard({
  generation,
  onOpenImages,
  onOpenSection,
  sections,
  tokenUsage,
  worldId,
}: RpgWorldGenerationDashboardProps) {
  const [view, setView] = useState<'board' | 'timeline'>('board');
  const [controlsOpen, setControlsOpen] = useState(false);
  const [selectedAction, setSelectedAction] = useState<PrimaryAction | null>(null);
  const [profileApproved, setProfileApproved] = useState(false);
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
      const controls = document.getElementById('generation-controls');
      controls?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    });
  };

  const runPrimaryAction = (action: PrimaryAction, invoke: () => void) => {
    setSelectedAction(action);
    setControlsOpen(true);
    invoke();
    window.requestAnimationFrame(() => {
      const controls = document.getElementById('generation-controls');
      controls?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    });
  };

  const isSelectedAction = (action: PrimaryAction) => selectedAction === action;
  const profileLocked = !profileApproved;

  return (
    <div className="rpg-generation-dashboard is-operational-dashboard">
      <RpgWorldProfilePreview onApprovalChange={setProfileApproved} worldId={worldId} />

      <section className="rpg-generation-dashboard-header" aria-label="Generation status dashboard">
        <div className="rpg-generation-dashboard-title">
          <span className="rpg-generation-dashboard-emblem" aria-hidden="true">✥</span>
          <div>
            <p className="eyebrow">World forge</p>
            <h2>World Generation</h2>
            <div className="rpg-generation-dashboard-live-status">
              <strong>{profileLocked ? 'Profile review' : run ? label(run.status) : 'Ready'}</strong>
              <span>·</span>
              <span>{profileLocked ? 'Approve the proposed topic catalogue before content generation.' : run ? `Generating world content across ${topicRows.length} topics` : 'The approved profile is ready for generation.'}</span>
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
        <button className={isSelectedAction('full') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('full')} disabled={profileLocked} onClick={() => runPrimaryAction('full', () => panelRef.current?.generateWorld())}>✦ Generate World</button>
        <button className={isSelectedAction('selected') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('selected')} disabled={profileLocked} onClick={() => { setSelectedAction('selected'); openControls(); }}>Generate Selected</button>
        <button className={isSelectedAction('stale') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('stale')} disabled={profileLocked} onClick={() => runPrimaryAction('stale', () => panelRef.current?.regenerateStale())}>Regenerate Stale</button>
        <button className={isSelectedAction('retry') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('retry')} disabled={profileLocked || !failed.size} onClick={() => runPrimaryAction('retry', () => panelRef.current?.retryFailed())}>Retry Failed{failed.size ? ` (${failed.size})` : ''}</button>
        <button className={isSelectedAction('continue') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('continue')} disabled={profileLocked || (run?.status !== 'failed' && !isPartialReviewRun(run))} onClick={() => runPrimaryAction('continue', () => panelRef.current?.continueGeneration())}>Continue Generation</button>
        <button className={isSelectedAction('publish') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('publish')} disabled={run?.status !== 'review'} onClick={() => runPrimaryAction('publish', () => panelRef.current?.publish())}>Publish World</button>
        {onOpenImages ? <button className={isSelectedAction('images') ? 'is-active' : ''} type="button" aria-pressed={isSelectedAction('images')} onClick={() => runPrimaryAction('images', onOpenImages)}>Generate Images</button> : null}
      </div>
      {profileLocked ? <p className="rpg-generation-primary-action-feedback" aria-live="polite">Generation is locked while the profile is awaiting approval.</p> : selectedAction ? <p className="rpg-generation-primary-action-feedback" aria-live="polite">{primaryActionLabel(selectedAction)} selected. Generation controls are open below with the operation result.</p> : null}

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
                    <span role="cell">{section.entity_count ? `${section.entity_count} structured entries` : section.displayStatus === 'failed' ? errorText : profileLocked ? 'Awaiting profile approval' : 'Queued for generation'}</span>
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
              <article className="rpg-generation-last-error"><small>Last Error</small><strong>{Array.from(failed).map(label).join(', ')} failed</strong><p>{errorText}</p><button type="button" disabled={profileLocked} onClick={() => panelRef.current?.retryFailed()}>Retry Now</button></article>
            ) : <p className="rpg-generation-no-error">No terminal topic failures.</p>}
            <div className="rpg-generation-activity-stream">
              {rows.filter((section) => section.displayStatus !== 'waiting' && section.displayStatus !== 'empty').slice(0, 7).map((section) => <div key={section.id}><span>{statusIcon(section.displayStatus)}</span><p><strong>{section.label}</strong> {label(section.displayStatus).toLowerCase()}</p></div>)}
            </div>
          </section>

          <section className="rpg-generation-token-card" aria-label="World generation token usage">
            <header><h3>Token usage</h3><span>{tokenUsage?.topic_count ?? 0} completed{tokenUsage?.in_flight_topics ? ` · ${tokenUsage.in_flight_topics} active` : ''}</span></header>
            <div className="rpg-generation-token-total">
              <strong>{tokenLabel(tokenUsage?.total_tokens ?? 0)}</strong><span>tokens accounted</span>
            </div>
            <div className="rpg-generation-token-breakdown">
              <span><small>Prompt</small><b>{tokenLabel(tokenUsage?.prompt_tokens ?? 0)}</b></span>
              <span><small>Completion</small><b>{tokenLabel(tokenUsage?.completion_tokens ?? 0)}</b></span>
            </div>
            <p>
              {tokenUsage?.provider_reported_topics ?? 0} provider-reported
              {tokenUsage?.estimated_topics ? ` · ${tokenUsage.estimated_topics} estimated` : ''}
              {tokenUsage?.unavailable_topics ? ` · ${tokenUsage.unavailable_topics} unavailable` : ''}
              {tokenUsage?.in_flight_topics ? <small> (live batches included)</small> : null}
            </p>
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
          profileApproved={profileApproved}
          sections={sections}
          worldId={worldId}
        />
      </details>
    </div>
  );
}
