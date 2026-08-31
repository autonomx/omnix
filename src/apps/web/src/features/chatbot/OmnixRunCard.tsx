import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { omnixApiClient } from '../../api/client';
import './OmnixRunCard.css';

type Metadata = Record<string, unknown>;

function asRecord(value: unknown): Metadata | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Metadata : null;
}

function runId(value: Metadata | null): string {
  return typeof value?.run_id === 'string' ? value.run_id : '';
}

function stringField(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function resultSummary(value: unknown, depth = 0): string {
  if (depth > 3 || value == null) return '';
  if (typeof value === 'string') return value.replace(/\s+/g, ' ').trim().slice(0, 320);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return value
      .map((item) => resultSummary(item, depth + 1))
      .filter(Boolean)
      .join(' · ')
      .slice(0, 320);
  }
  const row = asRecord(value);
  if (!row) return '';
  const preferredKeys = ['error', 'message', 'stderr', 'stdout', 'output', 'text', 'content', 'details'];
  for (const key of preferredKeys) {
    if (!(key in row)) continue;
    const summary = resultSummary(row[key], depth + 1);
    if (summary) return summary;
  }
  const exitCode = toolExitCode(row);
  return exitCode !== null ? `exit code ${exitCode}` : '';
}

function toolExitCode(value: unknown): number | null {
  const row = asRecord(value);
  if (!row) return null;
  const direct = row.exitCode ?? row.exit_code;
  if (typeof direct === 'number' && Number.isFinite(direct)) return direct;
  if (typeof direct === 'string' && direct.trim() && Number.isFinite(Number(direct))) return Number(direct);
  return row.details ? toolExitCode(row.details) : null;
}

function toolFailed(payload: Metadata): boolean {
  const exitCode = toolExitCode(payload.result);
  return payload.is_error === true || (exitCode !== null && exitCode !== 0);
}

function eventLabel(event: { event_type: string; payload: Metadata }): string | null {
  const tool = stringField(event.payload.tool) || 'tool';
  if (event.event_type === 'run.started') return '● Agent started';
  if (event.event_type === 'steering.received') return '● Steering received';
  if (event.event_type === 'tool.started') {
    const args = asRecord(event.payload.args);
    const command = stringField(args?.command);
    return command ? `● Running ${command.slice(0, 120)}` : `● Running ${tool}`;
  }
  if (event.event_type === 'tool.completed') {
    if (!toolFailed(event.payload)) return `✓ ${tool} completed`;
    const detail = resultSummary(event.payload.result);
    return `✕ ${tool} failed${detail ? ` · ${detail}` : ''}`;
  }
  if (event.event_type === 'model.message') {
    const text = stringField(event.payload.text).trim();
    return text ? `↳ ${text.slice(0, 500)}` : null;
  }
  if (event.event_type === 'acceptance.started') return '● Verifying acceptance';
  if (event.event_type === 'acceptance.completed') {
    if (event.payload.passed !== false) return '✓ Acceptance passed';
    const failures = Array.isArray(event.payload.failures)
      ? event.payload.failures.map(String).filter(Boolean).join(', ')
      : '';
    if (event.payload.retrying === true) {
      return `● Acceptance needs another pass; retrying${failures ? ` · ${failures}` : ''}`;
    }
    return `✕ Acceptance failed${failures ? ` · ${failures}` : ''}`;
  }
  if (event.event_type === 'acceptance.retry_requested') {
    const attempt = Number(event.payload.attempt ?? 0);
    return `● Automatic repair attempt ${attempt || '?'} started`;
  }
  if (event.event_type === 'run.failed') return '✕ Agent failed';
  return null;
}

function testEvidence(
  events: Array<{ event_type: string; payload: Metadata }>,
): Array<{ id: string; command: string; status: string; detail: string }> {
  const completed = new Map<string, Metadata>();
  events.forEach((event) => {
    if (event.event_type !== 'tool.completed') return;
    const id = stringField(event.payload.tool_call_id);
    if (id) completed.set(id, event.payload);
  });
  const testPattern = /(?:pytest|vitest|npm\s+(?:run\s+)?test|typecheck|\btsc\b|\bruff\b)/i;
  return events.flatMap((event, index) => {
    if (event.event_type !== 'tool.started') return [];
    const args = asRecord(event.payload.args);
    const command = stringField(args?.command);
    if (!command || !testPattern.test(command)) return [];
    const id = stringField(event.payload.tool_call_id) || `test-${index}`;
    const result = completed.get(id);
    return [{
      id,
      command,
      status: result ? (toolFailed(result) ? 'failed' : 'passed') : 'running',
      detail: result && toolFailed(result) ? resultSummary(result.result) : '',
    }];
  });
}

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export function OmnixRunCard({ metadata }: { metadata?: Metadata }) {
  const agent = asRecord(metadata?.agent_run);
  if (runId(agent)) return <AgentRunCard initial={agent!} routing={metadata} />;
  const workflow = asRecord(metadata?.workflow_run);
  if (runId(workflow)) return <WorkflowRunCard initial={workflow!} />;
  return null;
}

function AgentRunCard({ initial, routing }: { initial: Metadata; routing?: Metadata }) {
  const id = runId(initial);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['agent-run', id],
    queryFn: () => omnixApiClient.getAgentRun(id),
    initialData: {
      run_id: id,
      status: String(initial.status ?? 'starting'),
      desired_state: 'running',
      revision: Number(initial.revision ?? 1),
      last_error: typeof initial.last_error === 'string' ? initial.last_error : null,
      spec: {
        profile: String(initial.profile ?? 'agent'),
        task: String(initial.task ?? 'Agent task'),
      },
    },
    refetchInterval: (state) => TERMINAL.has(String(state.state.data?.status ?? '')) ? false : 1500,
  });
  const status = query.data.status;
  const live = !TERMINAL.has(status);
  const events = useQuery({
    queryKey: ['agent-run', id, 'events'],
    queryFn: () => omnixApiClient.listAgentRunEvents(id),
    refetchInterval: live ? 1500 : false,
  });
  const artifacts = useQuery({
    queryKey: ['agent-run', id, 'artifacts'],
    queryFn: () => omnixApiClient.listAgentArtifacts(id),
    refetchInterval: live ? 2000 : false,
  });
  const revisions = useQuery({
    queryKey: ['agent-run', id, 'task-revisions'],
    queryFn: () => omnixApiClient.listAgentTaskRevisions(id),
    refetchInterval: live ? 2000 : false,
  });
  const evidence = useQuery({
    queryKey: ['agent-run', id, 'evidence'],
    queryFn: () => omnixApiClient.getAgentEvidenceSet(id),
    refetchInterval: live ? 2000 : false,
  });
  const receipts = useQuery({
    queryKey: ['agent-run', id, 'evidence', 'receipts'],
    queryFn: () => omnixApiClient.listAgentEvidenceReceipts(id),
    refetchInterval: live ? 2000 : false,
  });
  const approvals = useQuery({
    queryKey: ['agent-run', id, 'approvals'],
    queryFn: () => omnixApiClient.listAgentApprovals(id, 'pending'),
    enabled: status === 'waiting_for_approval',
    refetchInterval: status === 'waiting_for_approval' ? 1500 : false,
  });
  const command = useMutation({
    mutationFn: (input: { type: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject'; payload?: Record<string, unknown> }) =>
      omnixApiClient.commandAgentRun(id, input.type, input.payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['agent-run', id] });
      void queryClient.invalidateQueries({ queryKey: ['agent-run', id, 'approvals'] });
      void queryClient.invalidateQueries({ queryKey: ['agent-run', id, 'events'] });
    },
  });
  const progress = (events.data ?? [])
    .map((event) => ({ event, label: eventLabel(event) }))
    .filter((row): row is { event: typeof row.event; label: string } => Boolean(row.label))
    .slice(-14);
  const tests = testEvidence(events.data ?? []);
  const diff = (artifacts.data ?? []).find((artifact) => artifact.kind === 'diff');
  const diffPreview = stringField(diff?.metadata.preview);
  const latestRevision = (revisions.data ?? []).at(-1);
  const requestMode = asRecord(query.data.spec.request_mode);
  const evidencePolicy = asRecord(query.data.spec.evidence_policy);
  const evidenceRequirements = Array.isArray(evidencePolicy?.requirements)
    ? evidencePolicy.requirements.map(asRecord).filter((value): value is Metadata => Boolean(value))
    : [];
  const attributionRefs = evidence.data?.attribution_refs ?? [];
  const semanticTask = asRecord(routing?.semantic_task);
  const semanticCompilation = asRecord(routing?.semantic_compilation);
  const routingDecision = asRecord(routing?.routing_decision) ?? asRecord(routing?.routing_shadow);
  const authorityCompilation = asRecord(routing?.authority_compilation);
  const legacyRoute = asRecord(routingDecision?.legacy);
  const semanticV2Route = asRecord(routingDecision?.semantic_v2);
  const parserDiagnostics = asRecord(routingDecision?.parser);
  const semanticActions = Array.isArray(semanticCompilation?.action_intents)
    ? semanticCompilation.action_intents.map(String)
    : [];
  const semanticAnomalies = Array.isArray(semanticCompilation?.anomalies)
    ? semanticCompilation.anomalies.map(asRecord).filter((value): value is Metadata => Boolean(value))
    : [];
  const issuedLocal = Array.isArray(authorityCompilation?.issued_local)
    ? authorityCompilation.issued_local.map(String)
    : [];
  const issuedExternal = Array.isArray(authorityCompilation?.issued_external)
    ? authorityCompilation.issued_external.map(String)
    : [];
  const deniedActions = Array.isArray(authorityCompilation?.denied_actions)
    ? authorityCompilation.denied_actions.map(String)
    : [];
  const productionRouter = stringField(routingDecision?.production_router)
    || stringField(routingDecision?.production)
    || 'semantic_v2';
  const productionLane = stringField(routingDecision?.production_lane)
    || (productionRouter === 'semantic_v2' ? stringField(semanticV2Route?.lane) : stringField(legacyRoute?.lane))
    || stringField(asRecord(routing?.omnix_route)?.lane);
  const showRouting = Boolean(semanticTask || semanticCompilation || routingDecision || authorityCompilation);

  return (
    <section className="assistant-runtime-card" aria-label="Agent run">
      <header>
        <span>Agent · {query.data.spec.profile}</span>
        <strong data-run-status={status}>{status}</strong>
      </header>
      <p>{query.data.spec.task}</p>
      <small>{id}</small>
      {query.data.last_error ? <p className="assistant-runtime-error">{query.data.last_error}</p> : null}
      {(requestMode || latestRevision || evidenceRequirements.length || evidence.data) ? (
        <details className="assistant-runtime-policy">
          <summary>Authority & evidence</summary>
          <div className="assistant-runtime-policy-grid">
            {requestMode ? <div><strong>Mode</strong><span>{stringField(requestMode.mode)} · {stringField(requestMode.source)}</span></div> : null}
            {latestRevision ? <div><strong>Task revision</strong><span>#{latestRevision.sequence} · {latestRevision.evidence_decision.reason}</span></div> : null}
            <div><strong>Evidence</strong><span>{evidence.data?.passed ? 'satisfied' : evidenceRequirements.length ? 'required' : 'not required'}</span></div>
            {evidenceRequirements.map((requirement, index) => {
              const subject = asRecord(requirement.subject);
              const evaluation = evidence.data?.requirements.find((row) => row.requirement_id === stringField(requirement.id));
              return (
                <div key={stringField(requirement.id) || `requirement-${index}`}>
                  <strong>{stringField(requirement.source_class) || 'evidence'}</strong>
                  <span>
                    {evaluation?.status ?? 'pending'}
                    {subject ? ` · ${stringField(subject.display_name) || stringField(subject.canonical_id)}` : ''}
                    {requirement.freshness ? ` · ${String(requirement.freshness)}` : ''}
                  </span>
                </div>
              );
            })}
            {(receipts.data ?? []).slice(-5).map((receipt) => (
              <div key={receipt.receipt_id}>
                <strong>Receipt · {receipt.source_class}</strong>
                <span>{receipt.provider ?? receipt.origin ?? receipt.capability_id} · {receipt.trust_level}</span>
              </div>
            ))}
            {attributionRefs.slice(-5).map((reference) => (
              <div key={`attribution-${reference}`}>
                <strong>Source reference</strong>
                <span>{reference}</span>
              </div>
            ))}
            {query.data.superseded_by_run_id ? <div><strong>Superseded by</strong><span>{query.data.superseded_by_run_id}</span></div> : null}
            {query.data.spec.supersedes_run_id ? <div><strong>Supersedes</strong><span>{query.data.spec.supersedes_run_id}</span></div> : null}
          </div>
        </details>
      ) : null}

      {showRouting ? (
        <details className="assistant-runtime-policy">
          <summary>Routing & compiler</summary>
          <div className="assistant-runtime-policy-grid">
            {semanticTask ? (
              <div>
                <strong>Semantic task</strong>
                <span>
                  {stringField(semanticTask.reason_code) || stringField(semanticTask.intent) || 'parsed'}
                  {semanticTask.ambiguity ? ` · ${String(semanticTask.ambiguity)}` : ''}
                </span>
              </div>
            ) : null}
            {semanticCompilation ? (
              <div>
                <strong>Compiled domain</strong>
                <span>
                  {stringField(semanticCompilation.profile_id) || stringField(semanticCompilation.lane) || 'chat'}
                  {semanticActions.length ? ` · ${semanticActions.join(', ')}` : ''}
                </span>
              </div>
            ) : null}
            {parserDiagnostics ? (
              <div>
                <strong>Semantic parser</strong>
                <span>
                  {stringField(parserDiagnostics.model) || stringField(parserDiagnostics.provider) || 'configured model'}
                  {parserDiagnostics.latency_ms != null ? ` · ${String(parserDiagnostics.latency_ms)}ms` : ''}
                  {parserDiagnostics.cache_hit === true ? ' · cache hit' : ''}
                </span>
              </div>
            ) : null}
            {authorityCompilation ? (
              <div>
                <strong>Issued authority</strong>
                <span>
                  {issuedLocal.length ? `local=${issuedLocal.join(', ')}` : 'local=none'}
                  {issuedExternal.length ? ` · external=${issuedExternal.join(', ')}` : ' · external=none'}
                  {deniedActions.length ? ` · denied=${deniedActions.join(', ')}` : ''}
                </span>
              </div>
            ) : null}
            {routingDecision ? (
              <div>
                <strong>Production route</strong>
                <span>
                  {productionRouter}
                  {productionLane ? ` · lane=${productionLane}` : ''}
                </span>
              </div>
            ) : null}
            {semanticAnomalies.map((anomaly, index) => (
              <div key={`semantic-anomaly-${index}`}>
                <strong>Semantic anomaly</strong>
                <span>{stringField(anomaly.code)}{anomaly.detail ? ` · ${String(anomaly.detail)}` : ''}</span>
              </div>
            ))}
          </div>
        </details>
      ) : null}

      {progress.length ? (
        <div className="assistant-runtime-progress" aria-label="Agent activity">
          <strong className="assistant-runtime-progress-heading">Live activity</strong>
          {progress.map(({ event, label }, index) => (
            <div key={event.event_id || `${event.event_type}-${index}`}>{label}</div>
          ))}
        </div>
      ) : null}

      {(diffPreview || tests.length) ? (
        <div className="assistant-runtime-evidence">
          {diffPreview ? (
            <details>
              <summary>View diff</summary>
              <pre>{diffPreview}</pre>
            </details>
          ) : null}
          {tests.length ? (
            <details>
              <summary>View tests</summary>
              <div className="assistant-runtime-test-list">
                {tests.map((test) => (
                  <div key={test.id}>
                    <strong>{test.status}</strong>
                    <div>
                      <code>{test.command}</code>
                      {test.detail ? <pre className="assistant-runtime-test-output">{test.detail}</pre> : null}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      ) : null}

      <div className="assistant-runtime-actions">
        {status === 'paused'
          ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'resume' })}>Resume</button>
          : !TERMINAL.has(status) && status !== 'waiting_for_approval'
            ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'pause' })}>Pause</button>
            : null}
        {!TERMINAL.has(status) ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'cancel' })}>Cancel</button> : null}
      </div>
      {approvals.data?.map((approval) => (
        <div className="assistant-runtime-approval" key={approval.approval_id}>
          <div>
            <span>Permission: {approval.capability_id}</span>
            {typeof approval.request_payload.command === 'string'
              ? <code className="assistant-runtime-approval-command">{approval.request_payload.command}</code>
              : typeof approval.request_payload.path === 'string'
                ? <code className="assistant-runtime-approval-command">{approval.request_payload.path}</code>
              : null}
          </div>
          <div>
            <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'approve', payload: { approval_id: approval.approval_id } })}>Approve</button>
            <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'reject', payload: { approval_id: approval.approval_id } })}>Reject</button>
          </div>
        </div>
      ))}
    </section>
  );
}

function WorkflowRunCard({ initial }: { initial: Metadata }) {
  const id = runId(initial);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['workflow-run', id],
    queryFn: () => omnixApiClient.getWorkflowRun(id),
    initialData: {
      run_id: id,
      workflow_id: String(initial.workflow_id ?? 'workflow'),
      workflow_version: Number(initial.workflow_version ?? 1),
      status: String(initial.status ?? 'running'),
      current_step_id: typeof initial.current_step_id === 'string' ? initial.current_step_id : null,
      input_payload: asRecord(initial.input_payload) ?? {},
      revision: Number(initial.revision ?? 1),
    },
    refetchInterval: (state) => TERMINAL.has(String(state.state.data?.status ?? '')) ? false : 1500,
  });
  const command = useMutation({
    mutationFn: (input: { type: 'pause' | 'resume' | 'cancel' | 'approve' | 'reject'; stepId?: string }) =>
      omnixApiClient.commandWorkflowRun(id, input.type, input.stepId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['workflow-run', id] }),
  });
  const status = query.data.status;
  const stepId = query.data.current_step_id ?? undefined;
  return (
    <section className="assistant-runtime-card" aria-label="Workflow run">
      <header>
        <span>Workflow · {query.data.workflow_id}</span>
        <strong data-run-status={status}>{status}</strong>
      </header>
      <small>{stepId ? `Current step: ${stepId}` : id}</small>
      <div className="assistant-runtime-actions">
        {status === 'waiting_for_approval' && stepId ? <>
          <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'approve', stepId })}>Approve</button>
          <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'reject', stepId })}>Reject</button>
        </> : null}
        {status === 'paused'
          ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'resume' })}>Resume</button>
          : !TERMINAL.has(status) && status !== 'waiting_for_approval'
            ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'pause' })}>Pause</button>
            : null}
        {!TERMINAL.has(status) ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ type: 'cancel' })}>Cancel</button> : null}
      </div>
    </section>
  );
}
