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

  it('renders a workflow approval surface', () => {
    renderCard({ workflow_run: { run_id: 'wf-1', workflow_id: 'morning', workflow_version: 1, status: 'waiting_for_approval', current_step_id: 'confirm', input_payload: {}, revision: 2 } });
    expect(screen.getByText('Workflow · morning')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeTruthy();
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
