import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldAuthoringClient,
  type RpgAuthoringSection,
  type RpgWorldTokenUsage,
} from '../../api/rpgWorldAuthoringClient';
import {
  rpgWorldGenerationReviewClient,
  type RpgWorldGenerationTopicResult,
} from '../../api/rpgWorldGenerationReviewClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import { RpgWorldGenerationCandidateReview } from './RpgWorldGenerationCandidateReview';
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

type RetryScope = 'topic' | 'entities' | 'entity_fields';
interface RetryRequest {
  topicIds: string[];
  retryScopes?: Record<string, Record<string, unknown>>;
}

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

function splitValues(value: string): string[] {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
}

function label(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusIcon(status: string): string {
  if (['complete', 'accepted', 'accept', 'replaced'].includes(status)) return '✓';
  if (status === 'pending_decision' || status === 'needs_review') return '⚑';
  if (status === 'kept') return '↶';
  if (status === 'failed') return '!';
  if (status === 'blocked') return '⊘';
  if (status === 'generating') return '↗';
  return '◷';
}

function tokenLabel(value: number): string {
  return new Intl.NumberFormat().format(Math.max(0, Math.round(value)));
}

function durationLabel(value: number): string {
  const totalSeconds = Math.max(0, Math.round(value / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingMinutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours) return `${hours}h ${remainingMinutes}m ${seconds}s`;
  if (minutes) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function hasManualDecisionIssue(result: RpgWorldGenerationTopicResult): boolean {
  return result.validation.reason_codes.includes('manual_retry_decision_required');
}

function isPromoted(result: RpgWorldGenerationTopicResult): boolean {
  return result.status === 'accepted'
    || result.decision?.decision === 'accept'
    || result.decision?.decision === 'replace';
}

function resultStatus(result: RpgWorldGenerationTopicResult | undefined): string | undefined {
  if (!result) return undefined;
  if (result.decision?.decision === 'accept') return 'complete';
  if (result.decision?.decision === 'replace') return 'replaced';
  if (result.decision?.decision === 'keep') return 'kept';
  if (hasManualDecisionIssue(result)) return 'pending_decision';
  return result.status === 'accepted' ? 'complete' : result.status;
}

function AnalyticsGroup({ title, values }: { title: string; values: Record<string, number> }) {
  const rows = Object.entries(values);
  if (!rows.length) return null;
  return (
    <div className="rpg-generation-review-analytics-group">
      <h4>{title}</h4>
      <div className="rpg-generation-review-reasons">
        {rows.map(([key, count]) => <span key={key}><strong>{label(key)}</strong><b>{count}</b></span>)}
      </div>
    </div>
  );
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
  const [profileApproved, setProfileApproved] = useState(false);
  const [selectedReviewTopics, setSelectedReviewTopics] = useState<string[]>([]);
  const [inspectedTopicId, setInspectedTopicId] = useState('');
  const [reviewFeedback, setReviewFeedback] = useState('');
  const [acceptAllArmed, setAcceptAllArmed] = useState(false);
  const [acceptAllDossiersArmed, setAcceptAllDossiersArmed] = useState(false);
  const [retryScope, setRetryScope] = useState<RetryScope>('topic');
  const [retryEntityIds, setRetryEntityIds] = useState('');
  const [retryFields, setRetryFields] = useState('');
  const [retryInstructions, setRetryInstructions] = useState('');
  const panelRef = useRef<RpgWorldGenerationPanelHandle>(null);
  const run = generation && 'run_id' in generation ? generation as RpgWorldGenerationRun : undefined;
  const progress = record(run?.progress);
  const active = new Set(stringArray(progress.active_topic_ids));
  const topicRows = sections.filter((section) => section.supports_generation);
  const provider = String(record(run?.settings).provider_route ?? 'Not configured');
  const model = String(record(run?.settings).model ?? 'Not configured');
  const imageSections = sections.filter((section) => section.supports_images);
  const imageReady = imageSections.filter((section) => section.operational_status === 'complete').length;

  const reviewQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-generation-review', run?.run_id],
    queryFn: () => rpgWorldGenerationReviewClient.list(run!.run_id),
    enabled: Boolean(run?.run_id),
    staleTime: run?.status === 'running' ? 2_000 : 10_000,
    refetchInterval: run?.status === 'running' ? 2_000 : false,
  });
  const dossierQualityQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-dossier-quality', worldId],
    queryFn: () => rpgWorldAuthoringClient.dossierQuality(worldId),
    enabled: Boolean(run?.run_id),
    staleTime: 10_000,
  });
  const results = reviewQuery.data?.topic_results ?? [];
  const analytics = reviewQuery.data?.analytics;
  const resultByTopic = useMemo(
    () => new Map(results.map((result) => [result.topic_id, result])),
    [results],
  );
  const inspectedResult = resultByTopic.get(inspectedTopicId);
  const inspectedSection = sections.find((section) => section.id === inspectedTopicId);
  const accepted = new Set(results.filter(isPromoted).map((result) => result.topic_id));
  const pendingDecision = new Set(results
    .filter((result) => hasManualDecisionIssue(result) && !result.decision)
    .map((result) => result.topic_id));
  const kept = new Set(results
    .filter((result) => result.decision?.decision === 'keep')
    .map((result) => result.topic_id));
  const flagged = new Set(results
    .filter((result) => result.status === 'needs_review' && !result.decision && !hasManualDecisionIssue(result))
    .map((result) => result.topic_id));
  const failed = new Set(results.filter((result) => result.status === 'failed').map((result) => result.topic_id));
  const blocked = new Set(results.filter((result) => result.status === 'blocked').map((result) => result.topic_id));
  const retryable = new Set([...flagged, ...failed, ...blocked]);
  const acceptAllEligible = results.filter((result) => (
    result.status === 'needs_review' && Boolean(result.candidate) && !result.decision
  ));
  const dossierCandidates = dossierQualityQuery.data?.enrichment_candidates ?? [];
  const allTopicsAccepted = topicRows.length > 0 && accepted.size >= topicRows.length;
  const publicationBlocked = Boolean(retryable.size || pendingDecision.size || kept.size);
  const terminalCount = accepted.size + pendingDecision.size + kept.size + flagged.size + failed.size + blocked.size;
  const percent = topicRows.length ? Math.round(terminalCount / topicRows.length * 100) : 0;

  const invalidateReview = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-generation-review'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-section', worldId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-workspace'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-dossier-quality', worldId] }),
    ]);
  };

  const retryReview = useMutation({
    mutationFn: ({ topicIds, retryScopes }: RetryRequest) => {
      if (!run) throw new Error('No completed generation run is available.');
      return rpgWorldGenerationReviewClient.retry(run.run_id, {
        ...(topicIds.length ? { topic_ids: topicIds } : {}),
        ...(retryScopes ? { retry_scopes: retryScopes } : {}),
      });
    },
    onSuccess: async () => {
      setReviewFeedback('Manual retry child run started. Affected dependents are included and no candidate is promoted before review.');
      setSelectedReviewTopics([]);
      await invalidateReview();
    },
    onError: (cause) => setReviewFeedback(cause instanceof Error ? cause.message : 'Retry failed.'),
  });

  const acceptAllReview = useMutation({
    mutationFn: () => {
      if (!run) throw new Error('No completed generation run is available.');
      return rpgWorldGenerationReviewClient.acceptAll(run.run_id);
    },
    onSuccess: async () => {
      setAcceptAllArmed(false);
      setInspectedTopicId('');
      setReviewFeedback('All reviewed canon and its generated dossiers were accepted together and promoted to editable world authoring.');
      await invalidateReview();
    },
    onError: (cause) => {
      setAcceptAllArmed(false);
      setReviewFeedback(cause instanceof Error ? cause.message : 'Review candidates could not be accepted.');
    },
  });

  const decideReview = useMutation({
    mutationFn: ({ topicId, decision }: { topicId: string; decision: 'keep' | 'replace' }) => {
      if (!run) throw new Error('No completed generation run is available.');
      return rpgWorldGenerationReviewClient.decide(run.run_id, topicId, decision);
    },
    onSuccess: async (_value, variables) => {
      setReviewFeedback(variables.decision === 'replace'
        ? 'The validated retry candidate was promoted. Publication remains blocked until every affected topic is decided.'
        : 'The previous authoring content was kept. Publication remains blocked for this retry run.');
      setInspectedTopicId('');
      await invalidateReview();
    },
    onError: (cause) => setReviewFeedback(cause instanceof Error ? cause.message : 'Decision failed.'),
  });

  const acceptAllDossiers = useMutation({
    mutationFn: () => rpgWorldAuthoringClient.enrichDossiers(worldId, {
      all_candidates: true,
      dry_run: false,
      directives: {
        generation_dashboard_bulk_acceptance: true,
        focus: 'Write complete, distinct long-form lore from accepted canon without changing structured facts, IDs, mechanics, or relationships.',
      },
    }),
    onMutate: () => {
      setReviewFeedback(`Generating and accepting ${dossierCandidates.length} dossiers. This runs one at a time to preserve canon; keep Omnix open until it finishes.`);
    },
    onSuccess: async (result) => {
      setAcceptAllDossiersArmed(false);
      const completed = result.completed?.length ?? 0;
      const failed = result.failed?.length ?? 0;
      setReviewFeedback(`Accepted ${completed} generated dossier${completed === 1 ? '' : 's'}${failed ? `; ${failed} could not be generated and remain available for individual regeneration.` : '.'}`);
      await invalidateReview();
    },
    onError: (cause) => {
      setAcceptAllDossiersArmed(false);
      setReviewFeedback(cause instanceof Error ? cause.message : 'Dossiers could not be generated and accepted.');
    },
  });

  const rows = topicRows.map((section) => {
    const result = resultByTopic.get(section.id);
    const displayStatus = active.has(section.id)
      ? 'generating'
      : resultStatus(result) ?? section.operational_status;
    return { ...section, result, displayStatus };
  });

  const retryInspectedTopic = () => {
    if (!inspectedResult) return;
    const entityIds = splitValues(retryEntityIds);
    const fields = splitValues(retryFields);
    if (retryScope === 'entities' && !entityIds.length) {
      setReviewFeedback('Enter at least one entity ID.');
      return;
    }
    if (retryScope === 'entity_fields' && (!entityIds.length || !fields.length)) {
      setReviewFeedback('Enter entity IDs and field names.');
      return;
    }
    retryReview.mutate({
      topicIds: [inspectedResult.topic_id],
      retryScopes: {
        [inspectedResult.topic_id]: {
          scope: retryScope,
          entity_ids: entityIds,
          fields,
          instructions: splitValues(retryInstructions),
        },
      },
    });
  };

  const handleAcceptAll = () => {
    if (!acceptAllArmed) {
      setAcceptAllArmed(true);
      setReviewFeedback(`Confirm acceptance of ${acceptAllEligible.length} generated canon-and-dossier candidate${acceptAllEligible.length === 1 ? '' : 's'} by clicking Accept All again.`);
      return;
    }
    acceptAllReview.mutate();
  };

  const handleAcceptAllDossiers = () => {
    if (!acceptAllDossiersArmed) {
      setAcceptAllDossiersArmed(true);
      setReviewFeedback(`Confirm generation and acceptance of ${dossierCandidates.length} dossier${dossierCandidates.length === 1 ? '' : 's'} by clicking Generate & Accept All Dossiers again.`);
      return;
    }
    acceptAllDossiers.mutate();
  };

  if (inspectedResult?.candidate && inspectedSection && run) {
    return (
      <div className="rpg-generation-dashboard is-operational-dashboard">
        {hasManualDecisionIssue(inspectedResult) && !inspectedResult.decision ? (
          <div className="rpg-generation-review-retry-controls">
            <strong>This retry candidate can replace the prior authoring topic, or the prior topic can be kept.</strong>
            <button type="button" disabled={decideReview.isPending} onClick={() => decideReview.mutate({ topicId: inspectedResult.topic_id, decision: 'keep' })}>Keep Previous</button>
          </div>
        ) : null}
        <RpgWorldGenerationCandidateReview
          onAccepted={async () => {
            setInspectedTopicId('');
            setReviewFeedback('Candidate accepted and promoted to editable authoring canon.');
            await invalidateReview();
          }}
          onClose={() => setInspectedTopicId('')}
          onRetryStarted={async () => {
            setReviewFeedback('Targeted retry started.');
            await invalidateReview();
          }}
          result={inspectedResult}
          runId={run.run_id}
          section={inspectedSection}
          worldId={worldId}
        />
      </div>
    );
  }

  return (
    <div className="rpg-generation-dashboard is-operational-dashboard">
      <RpgWorldProfilePreview onApprovalChange={setProfileApproved} worldId={worldId} />
      <section className="rpg-generation-dashboard-header" aria-label="Generation status dashboard">
        <div className="rpg-generation-dashboard-title"><span className="rpg-generation-dashboard-emblem" aria-hidden="true">✥</span><div><p className="eyebrow">World forge</p><h2>World Generation</h2><div className="rpg-generation-dashboard-live-status"><strong>{run ? label(run.status) : 'Ready'}</strong><span>·</span><span>{accepted.size} accepted · {pendingDecision.size} decisions · {flagged.size} flagged · {failed.size} failed · {blocked.size} blocked</span><div aria-label={`${percent} percent complete`}><i style={{ width: `${percent}%` }} /></div><b>{percent}%</b></div></div></div>
        <aside className="rpg-generation-provider-card"><span>Provider</span><strong>{label(provider)}</strong><span>Model</span><strong>{model || 'Provider default'}</strong><small>{run?.run_id ?? 'No active run'}</small></aside>
      </section>

      <div className="rpg-generation-primary-actions">
        <button type="button" disabled={!profileApproved} onClick={() => panelRef.current?.generateWorld()}>✦ Generate World</button>
        <button type="button" disabled={!profileApproved} onClick={() => setControlsOpen(true)}>Generate Selected</button>
        <button type="button" disabled={!profileApproved} onClick={() => panelRef.current?.regenerateStale()}>Regenerate Stale</button>
        <button type="button" disabled={!retryable.size || retryReview.isPending} onClick={() => retryReview.mutate({ topicIds: [] })}>Retry Review ({retryable.size})</button>
        <button type="button" disabled={!acceptAllEligible.length || acceptAllReview.isPending} onClick={handleAcceptAll}>
          {acceptAllReview.isPending
            ? 'Accepting All…'
            : acceptAllArmed
              ? `Confirm Accept All (${acceptAllEligible.length})`
              : `Accept All Canon & Dossiers (${acceptAllEligible.length})`}
        </button>
        <button type="button" disabled={!allTopicsAccepted || !dossierCandidates.length || acceptAllDossiers.isPending} onClick={handleAcceptAllDossiers}>
          {acceptAllDossiers.isPending
            ? `Generating Dossiers (${dossierCandidates.length})…`
            : acceptAllDossiersArmed
              ? `Confirm Generate & Accept (${dossierCandidates.length})`
              : `Repair Missing Dossiers (${dossierCandidates.length})`}
        </button>
        <button type="button" disabled={run?.status !== 'review' || publicationBlocked} onClick={() => panelRef.current?.publish()}>Publish World</button>
        {onOpenImages ? <button type="button" onClick={onOpenImages}>Generate Images</button> : null}
      </div>
      {reviewFeedback ? <p className="rpg-generation-primary-action-feedback" aria-live="polite">{reviewFeedback}</p> : null}

      <div className="rpg-generation-dashboard-layout">
        <section className="rpg-generation-topic-board">
          <header><h3>Topic Generation Progress</h3><div className="rpg-generation-status-chips"><span>Total <b>{topicRows.length}</b></span><span className="is-complete">Accepted <b>{accepted.size}</b></span><span className="is-review">Decision <b>{pendingDecision.size}</b></span><span className="is-review">Flagged <b>{flagged.size}</b></span><span className="is-generating">Active <b>{active.size}</b></span><span className="is-failed">Failed <b>{failed.size}</b></span><span className="is-blocked">Blocked <b>{blocked.size}</b></span></div><div className="rpg-generation-view-toggle"><button className={view === 'board' ? 'is-active' : ''} type="button" onClick={() => setView('board')}>Board</button><button className={view === 'timeline' ? 'is-active' : ''} type="button" onClick={() => setView('timeline')}>Timeline</button></div></header>
          {selectedReviewTopics.length ? <div className="rpg-generation-review-selection"><strong>{selectedReviewTopics.length} selected</strong><button type="button" onClick={() => retryReview.mutate({ topicIds: selectedReviewTopics })}>Retry selected</button><button type="button" onClick={() => setSelectedReviewTopics([])}>Clear</button></div> : null}
          {view === 'board' ? (
            <div className="rpg-generation-topic-table" role="table">
              <div className="rpg-generation-topic-table-head" role="row"><span>Topic</span><span>Status</span><span>Details</span><span>Actions</span></div>
              {rows.map((section) => {
                const result = section.result;
                const selectable = retryable.has(section.id);
                return (
                  <div className={`rpg-generation-topic-table-row is-${section.displayStatus}`} role="row" key={section.id}>
                    <div>{selectable ? <input aria-label={`Select ${section.label} for retry`} type="checkbox" checked={selectedReviewTopics.includes(section.id)} onChange={(event) => { const isChecked = event.currentTarget.checked; setSelectedReviewTopics((current) => isChecked ? [...new Set([...current, section.id])] : current.filter((value) => value !== section.id)); }} /> : null}<span className="rpg-generation-topic-icon">{statusIcon(section.displayStatus)}</span><strong>{section.label}</strong></div>
                    <span className="rpg-generation-topic-status">{label(section.displayStatus)}</span>
                    <span>{result?.decision ? `Decision: ${label(result.decision.decision)}` : result?.validation.reason_codes.map(label).join(', ') || `${section.entity_count || 0} entries`}</span>
                    <div>{result ? <button type="button" onClick={() => setInspectedTopicId(section.id)}>{result.candidate ? 'Review' : 'Inspect'}</button> : null}<button type="button" onClick={() => onOpenSection?.(section.id)}>Open Canon</button></div>
                  </div>
                );
              })}
            </div>
          ) : <ol className="rpg-generation-timeline">{rows.map((section) => <li className={`is-${section.displayStatus}`} key={section.id}><span>{statusIcon(section.displayStatus)}</span><div><strong>{section.label}</strong><p>{label(section.displayStatus)}</p></div></li>)}</ol>}
        </section>

        <aside className="rpg-generation-dashboard-side">
          <section className="rpg-generation-diagnostics-card"><header><h3>Validation analytics</h3><span>{results.length} attempted</span></header><AnalyticsGroup title="Reason code" values={analytics?.by_code ?? {}} /><AnalyticsGroup title="Field" values={analytics?.by_field ?? {}} /><AnalyticsGroup title="Domain" values={analytics?.by_domain ?? {}} /><AnalyticsGroup title="Model" values={analytics?.by_model ?? {}} /><AnalyticsGroup title="Prompt version" values={analytics?.by_prompt_version ?? {}} />{!Object.keys(analytics?.by_code ?? {}).length ? <p className="rpg-generation-no-error">No blocking validation issues recorded.</p> : null}</section>
          <section className="rpg-generation-token-card" aria-label="World generation token usage"><header><h3>Token usage</h3><span>{tokenUsage?.topic_count ?? 0} generated</span></header><div className="rpg-generation-token-total"><strong>{tokenLabel(tokenUsage?.total_tokens ?? 0)}</strong><span>tokens accounted</span></div><div className="rpg-generation-token-breakdown"><span><small>Usage source</small><b>{tokenUsage?.provider_reported_topics ?? 0} reported · {tokenUsage?.estimated_topics ?? 0} estimated</b></span>{tokenUsage?.timed_topics ? <span><small>Provider time</small><b>{durationLabel(tokenUsage.generation_duration_ms ?? 0)}</b></span> : null}</div>{tokenUsage?.in_flight_topics ? <p>Live batch usage included.</p> : null}</section>
          <section className="rpg-generation-image-card"><header><h3>Image Generation</h3></header><div><article><small>Targets</small><strong>{imageSections.length}</strong></article><article><small>Ready</small><strong>{imageReady}</strong></article></div></section>
        </aside>
      </div>

      {inspectedResult ? (
        <section className="rpg-generation-review-inspector" aria-label="Generation candidate review">
          <header><div><p className="eyebrow">Generation result</p><h3>{label(inspectedResult.topic_id)}</h3><span className={`is-${resultStatus(inspectedResult)}`}>{label(resultStatus(inspectedResult) ?? inspectedResult.status)}</span></div><button type="button" onClick={() => setInspectedTopicId('')}>Close</button></header>
          <div className="rpg-generation-review-inspector-grid"><article><h4>Validation issues</h4>{inspectedResult.validation.issues.length ? inspectedResult.validation.issues.map((issue, index) => <div className="rpg-generation-review-issue" key={`${issue.code}-${index}`}><strong>{label(issue.code)}</strong><span>{[issue.entity_id, issue.field_id].filter(Boolean).join(' · ') || inspectedResult.topic_id}</span><p>{issue.message || inspectedResult.validation.summary}</p></div>) : <p>No blocking issues.</p>}</article></div>
          {retryable.has(inspectedResult.topic_id) ? <div className="rpg-generation-review-retry-controls"><label>Retry scope<select value={retryScope} onChange={(event) => setRetryScope(event.currentTarget.value as RetryScope)}><option value="topic">Whole topic</option><option value="entities">Selected entities</option><option value="entity_fields">Selected fields</option></select></label>{retryScope !== 'topic' ? <label>Entity IDs<textarea value={retryEntityIds} onChange={(event) => setRetryEntityIds(event.currentTarget.value)} /></label> : null}{retryScope === 'entity_fields' ? <label>Fields<textarea value={retryFields} onChange={(event) => setRetryFields(event.currentTarget.value)} /></label> : null}<label>Instructions<textarea value={retryInstructions} onChange={(event) => setRetryInstructions(event.currentTarget.value)} /></label><button type="button" onClick={retryInspectedTopic}>Retry this scope</button></div> : null}
        </section>
      ) : null}

      <details className="rpg-generation-dashboard-controls" id="generation-controls" open={!run || controlsOpen} onToggle={(event) => setControlsOpen(event.currentTarget.open)}><summary>Generation controls and advanced settings</summary><RpgWorldGenerationPanel ref={panelRef} generation={generation} onOpenImages={onOpenImages} profileApproved={profileApproved} sections={sections} worldId={worldId} /></details>
    </div>
  );
}
