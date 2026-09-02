import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { omnixApiClient } from '../../api/client';
import { OmnixRunCard } from './OmnixRunCard';

function renderCard(metadata: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OmnixRunCard metadata={metadata} /></QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('OmnixRunCard', () => {
  it('renders an agent run from durable chat metadata', () => {
    renderCard({ agent_run: { run_id: 'run-1', status: 'paused', profile: 'coding', task: 'Fix tests', revision: 2 } });
    expect(screen.getByText('Agent · coding')).toBeTruthy();
    expect(screen.getByText('paused')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeTruthy();
  });

  it('shows semantic routing and compiler diagnostics', () => {
    renderCard({
      agent_run: {
        run_id: 'run-routing',
        status: 'paused',
        profile: 'coding',
        task: 'Fix Aurora light mode',
        revision: 2,
      },
      semantic_task: {
        intent: 'repair Aurora appearance',
        reason_code: 'workspace_ui_mutation',
        ambiguity: 'none',
      },
      turn_plan: {
        lane: 'agent',
        profile_id: 'coding',
        disposition: 'revise_objective',
        run_action: 'steer_agent',
        authority_delta: ['workspace_read', 'workspace_mutate', 'workspace_execute'],
      },
      semantic_compilation: {
        lane: 'agent',
        profile_id: 'coding',
        action_intents: ['workspace_read', 'workspace_mutate', 'workspace_execute'],
        anomalies: [],
      },
      routing_decision: {
        production_router: 'semantic_v2',
        production_lane: 'agent',
        parser: { provider: 'chatgpt_codex', model: 'gpt-fast', latency_ms: 143, cache_hit: false },
        semantic_v2: { lane: 'agent', reason: 'semantic_v2:workspace_ui_mutation' },
      },
    });

    expect(screen.getByText('Routing & compiler')).toBeTruthy();
    expect(screen.getByText(/agent · coding · revise_objective · steer_agent/)).toBeTruthy();
    expect(screen.getByText(/authority=workspace_read, workspace_mutate, workspace_execute/)).toBeTruthy();
    expect(screen.getByText(/workspace_ui_mutation · none/)).toBeTruthy();
    expect(screen.getByText(/coding · workspace_read, workspace_mutate, workspace_execute/)).toBeTruthy();
    expect(screen.getByText(/gpt-fast · 143ms/)).toBeTruthy();
    expect(screen.getByText(/semantic_v2 · lane=agent/)).toBeTruthy();
  });

  it('renders and updates a durable task graph result', () => {
    renderCard({
      task_graph_run: {
        run_id: 'graph-1',
        status: 'completed',
        revision: 3,
        result: 'Combined final answer.',
        graph: {
          graph_id: 'graph-def-1',
          revision: 1,
          nodes: [
            { id: 'research-1', kind: 'evidence_read', profile_id: 'research' },
            { id: 'synthesize-results', kind: 'agent', profile_id: 'research' },
          ],
          output_contract: { result_node: 'synthesize-results' },
        },
        node_states: [
          { node_id: 'research-1', status: 'completed' },
          { node_id: 'synthesize-results', status: 'completed' },
        ],
      },
    });
    expect(screen.getByText('Agent · Task graph')).toBeTruthy();
    expect(screen.getByText('completed')).toBeTruthy();
    expect(screen.getByText('Combined final answer.')).toBeTruthy();
    expect(screen.getByText(/2\/2 nodes complete/)).toBeTruthy();
  });

  it('renders a workflow approval surface', () => {
    renderCard({ workflow_run: { run_id: 'wf-1', workflow_id: 'morning', workflow_version: 1, status: 'waiting_for_approval', current_step_id: 'confirm', input_payload: {}, revision: 2 } });
    expect(screen.getByText('Workflow · morning')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeTruthy();
  });

  it('shows safe activity narration, failure output, and automatic repair', async () => {
    vi.spyOn(omnixApiClient, 'getAgentRun').mockResolvedValue({
      run_id: 'run-repair',
      status: 'running',
      desired_state: 'running',
      revision: 3,
      spec: { profile: 'coding', task: 'Fix the issue in code', evidence_policy: { requirements: [] } },
    });
    vi.spyOn(omnixApiClient, 'listAgentRunEvents').mockResolvedValue([
      {
        event_id: 'activity-1',
        run_id: 'run-repair',
        sequence: 1,
        event_type: 'model.message',
        payload: { text: 'I found the validation failure and I am correcting the implementation.' },
        created_at: '2026-08-29T00:00:00Z',
      },
      {
        event_id: 'activity-2',
        run_id: 'run-repair',
        sequence: 2,
        event_type: 'tool.started',
        payload: {
          tool_call_id: 'tool-1',
          tool: 'powershell',
          args: { command: 'python -m pytest src/tests/live_speech -q' },
        },
        created_at: '2026-08-29T00:00:01Z',
      },
      {
        event_id: 'activity-3',
        run_id: 'run-repair',
        sequence: 3,
        event_type: 'tool.completed',
        payload: {
          tool_call_id: 'tool-1',
          tool: 'powershell',
          is_error: false,
          result: { details: { exitCode: 1, stderr: '2 failed, 18 passed' } },
        },
        created_at: '2026-08-29T00:00:02Z',
      },
      {
        event_id: 'activity-4',
        run_id: 'run-repair',
        sequence: 4,
        event_type: 'acceptance.completed',
        payload: {
          passed: false,
          retrying: true,
          failures: ['successful_test_command'],
        },
        created_at: '2026-08-29T00:00:03Z',
      },
      {
        event_id: 'activity-5',
        run_id: 'run-repair',
        sequence: 5,
        event_type: 'acceptance.retry_requested',
        payload: { attempt: 1, failures: ['successful_test_command'] },
        created_at: '2026-08-29T00:00:04Z',
      },
    ]);
    vi.spyOn(omnixApiClient, 'listAgentTaskRevisions').mockResolvedValue([]);
    vi.spyOn(omnixApiClient, 'getAgentEvidenceSet').mockResolvedValue({
      run_id: 'run-repair',
      evaluated_at: '2026-08-29T00:00:04Z',
      requirements: [],
      missing_requirements: [],
      stale_receipts: [],
      wrong_subject_receipts: [],
      insufficient_trust_receipts: [],
      source_manifest_ids: [],
      attribution_refs: [],
      passed: true,
    });
    vi.spyOn(omnixApiClient, 'listAgentEvidenceReceipts').mockResolvedValue([]);
    vi.spyOn(omnixApiClient, 'listAgentArtifacts').mockResolvedValue([]);

    renderCard({
      agent_run: {
        run_id: 'run-repair',
        status: 'running',
        profile: 'coding',
        task: 'Fix the issue in code',
        revision: 3,
      },
    });

    expect(await screen.findByText('Live activity')).toBeTruthy();
    expect(screen.getByText(/I found the validation failure/)).toBeTruthy();
    expect(screen.getByText(/powershell failed · 2 failed, 18 passed/)).toBeTruthy();
    expect(screen.getByText(/Acceptance needs another pass; retrying/)).toBeTruthy();
    expect(screen.getByText('● Automatic repair attempt 1 started')).toBeTruthy();
    expect(screen.getByText('2 failed, 18 passed')).toBeTruthy();
  });

  it('shows durable progress, tests, and diff evidence', async () => {
    vi.spyOn(omnixApiClient, 'getAgentRun').mockResolvedValue({
      run_id: 'run-evidence',
      status: 'completed',
      desired_state: 'running',
      revision: 5,
      spec: { profile: 'coding', task: 'Fix tests', request_mode: { mode: 'agent', source: 'classifier' }, evidence_policy: { requirements: [] } },
    });
    vi.spyOn(omnixApiClient, 'listAgentRunEvents').mockResolvedValue([
      {
        event_id: 'event-1',
        run_id: 'run-evidence',
        sequence: 1,
        event_type: 'tool.started',
        payload: {
          tool_call_id: 'tool-1',
          tool: 'bash',
          args: { command: 'python -m pytest src/tests/agent_runtime -q' },
        },
        created_at: '2026-08-27T00:00:00Z',
      },
      {
        event_id: 'event-2',
        run_id: 'run-evidence',
        sequence: 2,
        event_type: 'tool.completed',
        payload: { tool_call_id: 'tool-1', tool: 'bash', is_error: false },
        created_at: '2026-08-27T00:00:01Z',
      },
      {
        event_id: 'event-3',
        run_id: 'run-evidence',
        sequence: 3,
        event_type: 'acceptance.completed',
        payload: { passed: true },
        created_at: '2026-08-27T00:00:02Z',
      },
    ]);
    vi.spyOn(omnixApiClient, 'listAgentTaskRevisions').mockResolvedValue([{
      revision_id: 'revision-1',
      run_id: 'run-evidence',
      sequence: 1,
      user_instruction: 'Fix tests',
      effective_objective: 'Fix tests',
      evidence_decision: { confidence: 0.98, reason: 'required:repo_ci_state', classifier: 'deterministic', policy: {} },
      required_local_capabilities: [],
      required_external_capabilities: [],
      expected_artifacts: ['diff'],
      acceptance_checks: ['successful_test_command'],
      created_at: '2026-08-27T00:00:00Z',
    }]);
    vi.spyOn(omnixApiClient, 'getAgentEvidenceSet').mockResolvedValue({
      run_id: 'run-evidence',
      evaluated_at: '2026-08-27T00:00:02Z',
      requirements: [],
      missing_requirements: [],
      stale_receipts: [],
      wrong_subject_receipts: [],
      insufficient_trust_receipts: [],
      source_manifest_ids: [],
      attribution_refs: ['manifest:run-evidence'],
      passed: true,
    });
    vi.spyOn(omnixApiClient, 'listAgentEvidenceReceipts').mockResolvedValue([]);
    vi.spyOn(omnixApiClient, 'listAgentArtifacts').mockResolvedValue([
      {
        artifact_id: 'artifact-1',
        run_id: 'run-evidence',
        kind: 'diff',
        name: 'workspace.diff',
        storage_ref: 'agent/runs/workspace/run/workspace.diff',
        checksum: 'abc',
        metadata: { preview: 'diff --git a/a.ts b/a.ts\n+fixed' },
        created_at: '2026-08-27T00:00:02Z',
      },
    ]);

    renderCard({
      agent_run: {
        run_id: 'run-evidence',
        status: 'completed',
        profile: 'coding',
        task: 'Fix tests',
        revision: 5,
      },
    });

    expect(await screen.findByText('✓ bash completed')).toBeTruthy();
    expect(screen.getByText('✓ Acceptance passed')).toBeTruthy();
    expect(screen.getByText('View tests')).toBeTruthy();
    expect(screen.getByText('View diff')).toBeTruthy();
    expect(screen.getByText('Authority & evidence')).toBeTruthy();
    expect(await screen.findByText('manifest:run-evidence')).toBeTruthy();
  });
});
