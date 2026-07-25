import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { RpgAuthoringSection, RpgWorldTokenUsage } from '../../api/rpgWorldAuthoringClient';
import {
  rpgWorldGenerationReviewClient,
  type RpgWorldGenerationTopicResult,
} from '../../api/rpgWorldGenerationReviewClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import {
  RpgWorldGenerationPanel,
  type RpgWorldGenerationPanelHandle,
} from './RpgWorldGenerationPanel';
import { RpgWorldProfilePreview } from './RpgWorldProfilePreview';
import './RpgWorldGenerationDashboardDesign.css';
import './RpgWorldGenerationReview.css';

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
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && Boolean(item))
    : [];
}

function label(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusIcon(status: string): string {
  if (status === 'complete' || status === 'accepted') return '✓';
  if (status === 'needs_review') return '⚑';
  if (status === 'failed') return '!';
  if (status === 'blocked') return '⊘';
  if (status === 'generating') return '↗';
  return '◷';
}

function primaryActionLabel(action: PrimaryAction): string {
  return {
    full: 'Generate World',
    selected: 'Generate Selected',
    stale: 'Regenerate Stale',
    retry: 'Retry Review',
    continue: 'Continue Generation',
    publish: 'Publish World',
    images: 'Generate Images',
  }[action];
}

function tokenLabel(value: number): string {
  return new Intl.NumberFormat().format(Math.max(0, Math.round(value)));
}

function resultDisplayStatus(result: RpgWorldGenerationTopicResult | undefined): string | undefined {
  if (!result) return undefined;
  return result.status === 'accepted' ? 'complete' : result.status;
}

export function RpgWorldGenerationDashboard({
  generation,
  onOpenImages,
  onOpenSection,
  sections,
  tokenUsage,
  worldId,
}: RpgWorldGenerationDashboardProps) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<'board' | 'timeline'>('board');
  const [controlsOpen, setControlsOpen] = useState(false);
  const [selectedAction, setSelectedAction] = useState<PrimaryAction | null>(null);
  const [profileApproved, setProfileApproved] = useState(false);
  const [selectedReviewTopics, setSelectedReviewTopics] = useState<string[]>([]);
  const [inspectedTopicId, setInspectedTopicId] = useState('');
  const [reviewFeedback, setReviewFeedback] = useState('');
  const panelRef = useRef<RpgWorldGenerationPanelHandle>(null);
  const run = generation && 'run_id' in generation ? generation as RpgWorldGenerationRun : undefined;
  const progress = record(run?.progress);
  const percent = Number(progress.percent ?? 0);
  const active = new Set(stringArray(progress.active_topic_ids));
  const accepted = new Set(stringArray(progress.accepted_topic_ids));
  const flagged = new Set(stringArray(progress.flagged_topic_ids));
  const failed = new Set(stringArray(progress.failed_topic_ids));
  const blocked = new Set(stringArray(progress.blocked_topic_ids));
  const retryable = new Set([...flagged, ...failed, ...blocked]);
  const topicRows = sections.filter((section) => section.supports_generation);
  const waiting = topicRows.filter((section) => ['waiting', 'empty'].includes(section.operational_status)).length;
  const provider = String(record(run?.settings).provider_route ?? record(run?.context).provider_route ?? 'configured');
  const model = String(record(run?.settings).model ?? record(run?.context).model ?? 'configured');
  const imageSections = sections.filter((section) => section.supports_images);
  const imageReady = imageSections.filter((section) => section.operational_status === 'complete').length;

  const reviewQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-generation-review', run?.run_id],
    queryFn: () => rpgWorldGenerationReviewClient.list(run!.run_id),
    enabled: Boolean(run?.run_id),
    staleTime: run?.status === 'running' ? 2_000 : 10_000,
    refetchInterval: run?.status === 'running' ? 2_000 : false,
  });
  const results = reviewQuery.data?.topic_results ?? [];
  const resultByTopic = useMemo(
    () => new Map(results.map((result) => [result.topic_id, result])),
    [results],
  );
  const inspectedResult = resultByTopic.get(inspectedTopicId);
  const issueCounts = record(progress.issue_counts);
  const issueCountsByCode = record(issueCounts.by_code);

  const retryReview = useMutation({
    mutationFn: (topicIds: string[]) => {
      if (!run) throw new Error('No completed generation run is available.');
      return rpgWorldGenerationReviewClient.retry(
        run.run_id,
        topicIds.length ? { topic_ids: topicIds } : {},
      );
    },
    onSuccess: async () => {
      setReviewFeedback('Manual retry child run started. The original candidates and reports remain unchanged.');
      setSelectedReviewTopics([]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-generation-review'] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-workspace'] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
      ]);
    },
    onError: (cause) => setReviewFeedback(
      cause instanceof Error ? cause.message : 'The selected topics could not be retried.',
    ),
  });

  const rows = topicRows.map((section) => {
    const result = resultByTopic.get(section.id);
    const status = active.has(section.id)
      ? 'generating'
      : resultDisplayStatus(result)
        ?? (flagged.has(section.id) ? 'needs_review'
          : failed.has(section.id) ? 'failed'
            : blocked.has(section.id) ? 'blocked'
              : accepted.has(section.id) ? 'complete'
                : section.operational_status);
    return { ...section, result, displayStatus: status };
  });

  const openControls = () => {
    setControlsOpen(true);
    window.requestAnimationFrame(() => {
      document.getElementById('generation-controls')?.scrollIntoView?.({
        behavior: 'smooth',
        block: 'start',
      });
    });
  };

  const runPrimaryAction = (action: PrimaryAction, invoke: () => void) => {
    setSelectedAction(action);
    invoke();
  };

  const isSelectedAction = (action: PrimaryAction) => selectedAction === action;
  const profileLocked = !profileApproved;
  const publicationBlocked = retryable.size > 0 || Boolean(progress.publication_blocked);
  const toggleReviewSelection = (topicId: string, checked: boolean) => {
    setSelectedReviewTopics((current) => checked
      ? Array.from(new Set([...current, topicId]))
      : current.filter((value) => value !== topicId));
  };

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
              <span>{profileLocked ? 'Approve the topic catalogue before generation.' : run ? `${accepted.size} accepted · ${flagged.size} flagged · ${failed.size} failed · ${blocked.size} blocked` : 'The approved profile is ready for generation.'}</span>
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
        <button className={isSelectedAction('full') ? 'is-active' : ''} type="button" disabled={profileLocked} onClick={() => runPrimaryAction('full', () => panelRef.current?.generateWorld())}>✦ Generate World</button>
        <button className={isSelectedAction('selected') ? 'is-active' : ''} type="button" disabled={profileLocked} onClick={() => { setSelectedAction('selected'); openControls(); }}>Generate Selected</button>
        <button className={isSelectedAction('stale') ? 'is-active' : ''} type="button" disabled={profileLocked} onClick={() => runPrimaryAction('stale', () => panelRef.current?.regenerateStale())}>Regenerate Stale</button>
        <button className={isSelectedAction('retry') ? 'is-active' : ''} type="button" disabled={profileLocked || !retryable.size || retryReview.isPending} onClick={() => runPrimaryAction('retry', () => retryReview.mutate([]))}>Retry Review{retryable.size ? ` (${retryable.size})` : ''}</button>
        <button className={isSelectedAction('continue') ? 'is-active' : ''} type="button" disabled={profileLocked || !retryable.size} onClick={() => runPrimaryAction('continue', () => retryReview.mutate([]))}>Retry All Remaining</button>
        <button className={isSelectedAction('publish') ? 'is-active' : ''} type="button" disabled={run?.status !== 'review' || publicationBlocked} onClick={() => runPrimaryAction('publish', () => panelRef.current?.publish())}>Publish World</button>
        {onOpenImages ? <button className={isSelectedAction('images') ? 'is-active' : ''} type="button" onClick={() => runPrimaryAction('images', onOpenImages)}>Generate Images</button> : null}
      </div>
      {profileLocked ? <p className="rpg-generation-primary-action-feedback">Generation is locked while the profile is awaiting approval.</p> : selectedAction ? <p className="rpg-generation-primary-action-feedback">{primaryActionLabel(selectedAction)} selected.</p> : null}
      {reviewFeedback ? <p className="rpg-generation-primary-action-feedback" aria-live="polite">{reviewFeedback}</p> : null}

      <div className="rpg-generation-dashboard-layout">
        <section className="rpg-generation-topic-board">
          <header>
            <h3>Topic Generation Progress</h3>
            <div className="rpg-generation-status-chips">
              <span>Total <b>{topicRows.length}</b></span>
              <span className="is-complete">Accepted <b>{accepted.size}</b></span>
              <span className="is-review">Needs review <b>{flagged.size}</b></span>
              <span className="is-generating">In progress <b>{active.size}</b></span>
              <span className="is-failed">Failed <b>{failed.size}</b></span>
              <span className="is-blocked">Blocked <b>{blocked.size}</b></span>
              <span>Queued <b>{waiting}</b></span>
            </div>
            <div className="rpg-generation-view-toggle">
              <button className={view === 'board' ? 'is-active' : ''} type="button" onClick={() => setView('board')}>Board</button>
              <button className={view === 'timeline' ? 'is-active' : ''} type="button" onClick={() => setView('timeline')}>Timeline</button>
            </div>
          </header>

          {selectedReviewTopics.length ? (
            <div className="rpg-generation-review-selection">
              <strong>{selectedReviewTopics.length} selected</strong>
              <button type="button" disabled={retryReview.isPending} onClick={() => retryReview.mutate(selectedReviewTopics)}>Retry selected</button>
              <button type="button" onClick={() => setSelectedReviewTopics([])}>Clear</button>
            </div>
          ) : null}

          {view === 'board' ? (
            <div className="rpg-generation-topic-table" role="table" aria-label="Topic generation progress">
              <div className="rpg-generation-topic-table-head" role="row">
                <span role="columnheader">Topic</span><span role="columnheader">Status</span><span role="columnheader">Progress</span><span role="columnheader">Updated</span><span role="columnheader">Details</span><span role="columnheader">Actions</span>
              </div>
              {rows.map((section) => {
                const terminal = ['complete', 'needs_review', 'failed', 'blocked'].includes(section.displayStatus);
                const generating = section.displayStatus === 'generating';
                const result = section.result;
                const reasonCodes = result?.validation.reason_codes ?? [];
                return (
                  <div className={`rpg-generation-topic-table-row is-${section.displayStatus}`} role="row" key={section.id}>
                    <div role="cell">
                      {retryable.has(section.id) ? <input aria-label={`Select ${section.label} for retry`} type="checkbox" checked={selectedReviewTopics.includes(section.id)} onChange={(event) => toggleReviewSelection(section.id, event.currentTarget.checked)} /> : null}
                      <span className="rpg-generation-topic-icon">{statusIcon(section.displayStatus)}</span><strong>{section.label}</strong>
                    </div>
                    <span role="cell" className="rpg-generation-topic-status">{label(section.displayStatus)}</span>
                    <div role="cell" className={`rpg-generation-row-progress${generating ? ' is-indeterminate' : ''}`}><i style={{ width: terminal || generating ? '100%' : '0%' }} /><small>{terminal ? 'Attempt complete' : generating ? 'Provider call in progress' : 'Queued'}</small></div>
                    <span role="cell">{result?.updated_at ? new Date(result.updated_at).toLocaleString() : run?.updated_at ? new Date(run.updated_at).toLocaleString() : '—'}</span>
                    <span role="cell">{reasonCodes.length ? reasonCodes.map(label).join(', ') : result?.status === 'accepted' ? `${section.entity_count || 0} structured entries` : section.entity_count ? `${section.entity_count} structured entries` : 'Queued for generation'}</span>
                    <div role="cell">
                      {result ? <button type="button" aria-label={`Inspect ${section.label} generation result`} onClick={() => setInspectedTopicId(section.id)}>◎</button> : null}
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
            <header><h3>Validation analytics</h3><span>{results.length} attempted</span></header>
            {Object.keys(issueCountsByCode).length ? (
              <div className="rpg-generation-review-reasons">
                {Object.entries(issueCountsByCode).map(([code, count]) => <span key={code}><strong>{label(code)}</strong><b>{Number(count)}</b></span>)}
              </div>
            ) : <p className="rpg-generation-no-error">No blocking validation issues recorded.</p>}
            {retryable.size ? <button type="button" disabled={retryReview.isPending} onClick={() => retryReview.mutate([])}>Retry all review items</button> : null}
          </section>

          <section className="rpg-generation-token-card" aria-label="World generation token usage">
            <header><h3>Token usage</h3><span>{tokenUsage?.topic_count ?? 0} completed{tokenUsage?.in_flight_topics ? ` · ${tokenUsage.in_flight_topics} active` : ''}</span></header>
            <div className="rpg-generation-token-total"><strong>{tokenLabel(tokenUsage?.total_tokens ?? 0)}</strong><span>tokens accounted</span></div>
            <div className="rpg-generation-token-breakdown"><span><small>Prompt</small><b>{tokenLabel(tokenUsage?.prompt_tokens ?? 0)}</b></span><span><small>Completion</small><b>{tokenLabel(tokenUsage?.completion_tokens ?? 0)}</b></span></div>
            <p>{tokenUsage?.provider_reported_topics ?? 0} provider-reported{tokenUsage?.estimated_topics ? ` · ${tokenUsage.estimated_topics} estimated` : ''}{tokenUsage?.unavailable_topics ? ` · ${tokenUsage.unavailable_topics} unavailable` : ''}</p>
          </section>

          <section className="rpg-generation-image-card">
            <header><h3>Image Generation</h3>{onOpenImages ? <button type="button" onClick={onOpenImages}>View all</button> : null}</header>
            <div><article><small>Targets</small><strong>{imageSections.length}</strong></article><article><small>Ready</small><strong>{imageReady}</strong></article><article><small>Pending</small><strong>{Math.max(0, imageSections.length - imageReady)}</strong></article></div>
            {onOpenImages ? <button type="button" onClick={onOpenImages}>Go to Images →</button> : null}
          </section>
        </aside>
      </div>

      {inspectedResult ? (
        <section className="rpg-generation-review-inspector" aria-label="Generation candidate review">
          <header>
            <div><p className="eyebrow">Retained candidate</p><h3>{label(inspectedResult.topic_id)}</h3><span className={`is-${inspectedResult.status}`}>{label(inspectedResult.status)}</span></div>
            <button type="button" onClick={() => setInspectedTopicId('')}>Close</button>
          </header>
          <div className="rpg-generation-review-inspector-grid">
            <article>
              <h4>Validation issues</h4>
              {inspectedResult.validation.issues.length ? inspectedResult.validation.issues.map((issue, index) => (
                <div className="rpg-generation-review-issue" key={`${issue.code}-${issue.entity_id}-${issue.field_id}-${index}`}>
                  <strong>{label(issue.code)}</strong>
                  <span>{[issue.entity_id, issue.field_id].filter(Boolean).join(' · ') || inspectedResult.topic_id}</span>
                  <p>{issue.message || inspectedResult.validation.summary}</p>
                </div>
              )) : <p>No blocking issues.</p>}
            </article>
            <article>
              <h4>Candidate JSON</h4>
              <pre>{JSON.stringify(inspectedResult.candidate, null, 2)}</pre>
            </article>
          </div>
          {retryable.has(inspectedResult.topic_id) ? <button type="button" disabled={retryReview.isPending} onClick={() => retryReview.mutate([inspectedResult.topic_id])}>Retry this topic</button> : null}
        </section>
      ) : null}

      <details className="rpg-generation-dashboard-controls" id="generation-controls" open={!run || controlsOpen} onToggle={(event) => setControlsOpen(event.currentTarget.open)}>
        <summary>Generation controls and advanced settings</summary>
        <RpgWorldGenerationPanel ref={panelRef} generation={generation} onOpenImages={onOpenImages} profileApproved={profileApproved} sections={sections} worldId={worldId} />
      </details>
    </div>
  );
}
