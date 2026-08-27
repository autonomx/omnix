import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OmnixRunCard } from './OmnixRunCard';

function renderCard(metadata: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OmnixRunCard metadata={metadata} /></QueryClientProvider>);
}

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
});
