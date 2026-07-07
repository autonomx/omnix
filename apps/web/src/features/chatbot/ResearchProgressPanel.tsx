import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef } from 'react';
import { omnixApiClient, type ChatSession, type JobRecord } from '../../api/client';

type ChatMessage = NonNullable<ChatSession['messages']>[number];

type ResearchProgressPanelProps = {
  session?: ChatSession;
  queuedJob?: JobRecord;
};

const ACTIVE_JOB_STATUSES = new Set(['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested']);
const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'canceled', 'stale']);
const RESEARCH_JOB_TYPE = 'assistant.deep_research';

export function ResearchProgressPanel({ session, queuedJob }: ResearchProgressPanelProps) {
  const queryClient = useQueryClient();
  const jobId = latestResearchJobId(session?.messages ?? [], queuedJob);
  const settledJobRef = useRef<string | null>(null);
  const jobQuery = useQuery({
    queryKey: ['platform', 'jobs', 'research', jobId],
    queryFn: () => omnixApiClient.getJob(jobId ?? ''),
    enabled: Boolean(jobId),
    initialData: queuedJob?.id === jobId ? queuedJob : undefined,
    refetchInterval: (query) => isActiveResearchJob(query.state.data as JobRecord | undefined) ? 1_500 : false,
  });
  const cancelMutation = useMutation({
    mutationFn: (id: string) => omnixApiClient.cancelJob(id, 'Canceled by the user from the research progress panel.'),
    onSuccess: async (job) => {
      queryClient.setQueryData(['platform', 'jobs', 'research', job.id], job);
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });
  const job = jobQuery.data;
  const details = useMemo(() => researchJobDetails(job), [job]);

  useEffect(() => {
    if (!job || !TERMINAL_JOB_STATUSES.has(String(job.status)) || settledJobRef.current === job.id) return;
    settledJobRef.current = job.id;
    void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot'] });
    void queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
  }, [job?.id, job?.status, queryClient]);

  if (!jobId) return null;
  if (jobQuery.isError && !job) {
    return <section className="assistant-research-progress error" role="status">Research progress could not be restored.</section>;
  }
  if (!job) {
    return <section className="assistant-research-progress" role="status">Restoring research progress…</section>;
  }

  const active = isActiveResearchJob(job);
  const announcement = researchStageAnnouncement(job);
  return (
    <section className={`assistant-research-progress status-${String(job.status)}`} aria-labelledby={`research-progress-${job.id}`}>
      <header>
        <div>
          <p className="eyebrow">Deep research</p>
          <h3 id={`research-progress-${job.id}`}>{researchStageLabel(job)}</h3>
        </div>
        <span className="assistant-research-status">{formatResearchJobStatus(job.status)}</span>
      </header>
      <div className="assistant-research-progress-track" aria-hidden="true">
        <span style={{ width: `${researchProgressPercent(job)}%` }} />
      </div>
      <p className="assistant-research-announcement" aria-live="polite" aria-atomic="true">{announcement}</p>
      <div className="assistant-research-progress-actions">
        {active ? (
          <button
            type="button"
            disabled={cancelMutation.isPending || String(job.status) === 'cancel_requested'}
            onClick={() => cancelMutation.mutate(job.id)}
          >
            {String(job.status) === 'cancel_requested' ? 'Cancellation requested' : cancelMutation.isPending ? 'Canceling…' : 'Cancel research'}
          </button>
        ) : null}
        <small>{completedStageCount(job)} of {job.stages?.length ?? 0} stages complete</small>
      </div>
      {cancelMutation.isError ? <p role="alert">Research cancellation failed.</p> : null}
      {details ? <ResearchJobDetailsView details={details} /> : null}
    </section>
  );
}

export function ResearchMessageDetails({ message }: { message: ChatMessage }) {
  const metadata = asRecord(message.metadata);
  const mode = stringValue(metadata.research_mode);
  if (message.role !== 'assistant' || (mode !== 'quick' && mode !== 'deep')) return null;
  const status = stringValue(metadata.research_status) || 'completed';
  const warnings = stringList(metadata.research_warnings);
  const citationValidation = asRecord(metadata.citation_validation ?? metadata.synthesis_validation);
  return (
    <details className="assistant-research-message-details">
      <summary>{mode === 'quick' ? 'Quick search details' : 'Research details'} · {status}</summary>
      <dl>
        <div><dt>Mode</dt><dd>{mode === 'quick' ? 'Quick search' : 'Deep research'}</dd></div>
        {stringValue(metadata.source_manifest_id) ? <div><dt>Sources</dt><dd>Manifest saved</dd></div> : null}
        {stringValue(metadata.planner_backend) ? <div><dt>Planner</dt><dd>{stringValue(metadata.planner_backend)}</dd></div> : null}
        {stringValue(metadata.synthesis_backend) ? <div><dt>Synthesis</dt><dd>{stringValue(metadata.synthesis_backend)}</dd></div> : null}
        {numberValue(metadata.logical_queries) !== null ? <div><dt>Queries</dt><dd>{numberValue(metadata.logical_queries)}</dd></div> : null}
        {numberValue(metadata.extracted_pages) !== null ? <div><dt>Pages reviewed</dt><dd>{numberValue(metadata.extracted_pages)}</dd></div> : null}
        {numberValue(metadata.conflict_count) !== null ? <div><dt>Conflicts</dt><dd>{numberValue(metadata.conflict_count)}</dd></div> : null}
        {typeof citationValidation.valid === 'boolean' ? <div><dt>Citations</dt><dd>{citationValidation.valid ? 'Validated' : 'Validation warning'}</dd></div> : null}
      </dl>
      {warnings.length ? <ul>{warnings.map((warning) => <li key={warning}>{humanizeCode(warning)}</li>)}</ul> : null}
    </details>
  );
}

export function latestResearchJobId(messages: ChatMessage[], queuedJob?: JobRecord): string | null {
  if (queuedJob?.type === RESEARCH_JOB_TYPE) return queuedJob.id;
  for (const message of [...messages].reverse()) {
    const metadata = asRecord(message.metadata);
    const jobId = stringValue(metadata.research_job_id);
    if (jobId) return jobId;
  }
  return null;
}

export function isActiveResearchJob(job?: JobRecord): boolean {
  return Boolean(job?.type === RESEARCH_JOB_TYPE && ACTIVE_JOB_STATUSES.has(String(job.status)));
}

export function researchStageLabel(job: JobRecord): string {
  const stage = activeResearchStage(job);
  return stage?.label || (String(job.status) === 'completed' ? 'Research complete' : 'Research job');
}

export function researchStageAnnouncement(job: JobRecord): string {
  const status = String(job.status);
  if (status === 'completed') return 'Research complete. The answer and source details are available in the conversation.';
  if (status === 'failed') return 'Research failed. Review the job error or retry the request.';
  if (status === 'canceled') return 'Research canceled.';
  if (status === 'cancel_requested') return 'Cancellation requested. The current operation will stop at the next safe boundary.';
  const stage = activeResearchStage(job);
  return stringValue(stage?.progress?.message) || stage?.label || 'Research is queued.';
}

export function researchProgressPercent(job: JobRecord): number {
  const total = Math.max(1, job.stages?.length ?? 1);
  const completed = completedStageCount(job);
  if (String(job.status) === 'completed') return 100;
  return Math.max(0, Math.min(99, Math.round((completed / total) * 100)));
}

function activeResearchStage(job: JobRecord) {
  const stages = job.stages ?? [];
  return stages.find((stage) => ['running', 'leased', 'cancel_requested'].includes(String(stage.status)))
    ?? stages.find((stage) => !['completed', 'failed', 'canceled', 'stale'].includes(String(stage.status)))
    ?? stages.at(-1);
}

function completedStageCount(job: JobRecord): number {
  return (job.stages ?? []).filter((stage) => String(stage.status) === 'completed').length;
}

function formatResearchJobStatus(value: unknown): string {
  return humanizeCode(String(value || 'queued'));
}

type ResearchJobDetails = {
  sources: Array<{ id: string; title: string; url?: string; citation?: string; extractionStatus?: string }>;
  conflicts: Array<{ id: string; summary: string }>;
  warnings: string[];
  plannerBackend?: string;
  synthesisBackend?: string;
  stopReason?: string;
  logicalQueries?: number;
  extractedPages?: number;
};

function researchJobDetails(job?: JobRecord): ResearchJobDetails | null {
  const output = asRecord(job?.output_refs?.[0]);
  if (!Object.keys(output).length) return null;
  const snapshots = arrayRecords(output.snapshots);
  const snapshotBySource = new Map(snapshots.map((snapshot) => [stringValue(snapshot.source_record_id), snapshot]));
  const sources = arrayRecords(output.sources).map((source, index) => {
    const id = stringValue(source.source_record_id) || `source-${index + 1}`;
    const snapshot = snapshotBySource.get(id);
    return {
      id,
      title: stringValue(source.title) || `Source ${index + 1}`,
      url: stringValue(source.canonical_url ?? source.original_url) || undefined,
      citation: stringValue(snapshot?.citation_label) || undefined,
      extractionStatus: stringValue(snapshot?.extraction_status) || undefined,
    };
  });
  const conflicts = arrayRecords(output.conflicts).map((conflict, index) => ({
    id: stringValue(conflict.conflict_id) || `conflict-${index + 1}`,
    summary: stringValue(conflict.summary) || 'Unresolved source conflict.',
  }));
  return {
    sources,
    conflicts,
    warnings: stringList(output.warnings),
    plannerBackend: stringValue(output.planner_backend) || undefined,
    synthesisBackend: stringValue(output.synthesis_backend) || undefined,
    stopReason: stringValue(output.stop_reason) || undefined,
    logicalQueries: numberValue(output.logical_queries) ?? undefined,
    extractedPages: numberValue(output.extracted_pages) ?? undefined,
  };
}

function ResearchJobDetailsView({ details }: { details: ResearchJobDetails }) {
  return (
    <details className="assistant-research-job-details">
      <summary>Research details</summary>
      <dl>
        {details.plannerBackend ? <div><dt>Planner</dt><dd>{details.plannerBackend}</dd></div> : null}
        {details.synthesisBackend ? <div><dt>Synthesis</dt><dd>{details.synthesisBackend}</dd></div> : null}
        {details.logicalQueries !== undefined ? <div><dt>Queries</dt><dd>{details.logicalQueries}</dd></div> : null}
        {details.extractedPages !== undefined ? <div><dt>Pages reviewed</dt><dd>{details.extractedPages}</dd></div> : null}
        {details.stopReason ? <div><dt>Stop reason</dt><dd>{humanizeCode(details.stopReason)}</dd></div> : null}
      </dl>
      {details.sources.length ? (
        <section aria-labelledby="research-sources-heading">
          <h4 id="research-sources-heading">Sources</h4>
          <ol className="assistant-research-source-list">
            {details.sources.map((source) => (
              <li key={source.id}>
                <span>{source.citation ? `[${source.citation}] ` : ''}{source.title}</span>
                {source.url ? <a href={source.url} target="_blank" rel="noreferrer">Open source</a> : null}
                {source.extractionStatus ? <small>{humanizeCode(source.extractionStatus)}</small> : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      {details.conflicts.length ? (
        <section aria-labelledby="research-conflicts-heading">
          <h4 id="research-conflicts-heading">Unresolved conflicts</h4>
          <ul>{details.conflicts.map((conflict) => <li key={conflict.id}>{conflict.summary}</li>)}</ul>
        </section>
      ) : null}
      {details.warnings.length ? (
        <section aria-labelledby="research-warnings-heading">
          <h4 id="research-warnings-heading">Warnings</h4>
          <ul>{details.warnings.map((warning) => <li key={warning}>{humanizeCode(warning)}</li>)}</ul>
        </section>
      ) : null}
    </details>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(stringValue).filter(Boolean) : [];
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function humanizeCode(value: string): string {
  const text = value.replace(/[_-]+/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Unknown';
}
