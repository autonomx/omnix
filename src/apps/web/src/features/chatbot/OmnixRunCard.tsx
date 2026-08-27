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
    return event.payload.is_error ? `✕ ${tool} failed` : `✓ ${tool} completed`;
  }
  if (event.event_type === 'acceptance.started') return '● Verifying acceptance';
  if (event.event_type === 'acceptance.completed') {
    return event.payload.passed === false ? '✕ Acceptance failed' : '✓ Acceptance passed';
  }
  if (event.event_type === 'run.failed') return '✕ Agent failed';
  return null;
}

function testEvidence(
  events: Array<{ event_type: string; payload: Metadata }>,
): Array<{ id: string; command: string; status: string }> {
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
      status: result ? (result.is_error ? 'failed' : 'passed') : 'running',
    }];
  });
}

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export function OmnixRunCard({ metadata }: { metadata?: Metadata }) {
  const agent = asRecord(metadata?.agent_run);
  if (runId(agent)) return <AgentRunCard initial={agent!} />;
  const workflow = asRecord(metadata?.workflow_run);
  if (runId(workflow)) return <WorkflowRunCard initial={workflow!} />;
  return null;
}

function AgentRunCard({ initial }: { initial: Metadata }) {
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
    .slice(-8);
  const tests = testEvidence(events.data ?? []);
  const diff = (artifacts.data ?? []).find((artifact) => artifact.kind === 'diff');
  const diffPreview = stringField(diff?.metadata.preview);

  return (
    <section className="assistant-runtime-card" aria-label="Agent run">
      <header>
        <span>Agent · {query.data.spec.profile}</span>
        <strong data-run-status={status}>{status}</strong>
      </header>
      <p>{query.data.spec.task}</p>
      <small>{id}</small>
      {query.data.last_error ? <p className="assistant-runtime-error">{query.data.last_error}</p> : null}

      {progress.length ? (
        <div className="assistant-runtime-progress" aria-label="Agent progress">
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
                    <code>{test.command}</code>
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
          <span>Approval: {approval.capability_id}</span>
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
