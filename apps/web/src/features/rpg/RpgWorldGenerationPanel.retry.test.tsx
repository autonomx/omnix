import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import { RpgWorldGenerationPanel } from './RpgWorldGenerationPanel';

function run(status: string, failedTopicIds: string[] = []): RpgWorldGenerationRun {
  return {
    run_id: `run:${status}`,
    world_id: 'world:aurelia',
    draft_revision: 2,
    status,
    graph: {},
    context: {},
    settings: {},
    plan: {},
    progress: {
      percent: status === 'running' ? 27 : 40,
      failed_topic_ids: failedTopicIds,
    },
    error: {},
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
  };
}

function renderPanel(generation: RpgWorldGenerationRun) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RpgWorldGenerationPanel
        generation={generation}
        sections={[]}
        worldId="world:aurelia"
      />
    </QueryClientProvider>,
  );
}

describe('RpgWorldGenerationPanel failed-topic retry guards', () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];

  beforeEach(() => {
    requests.length = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return new Response(JSON.stringify({
        ok: true,
        worker_started: true,
        run: run('running'),
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it('blocks duplicate generation scopes while the current run is active', () => {
    renderPanel(run('running'));

    expect(screen.getByRole('button', { name: 'Generate World' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Regenerate Stale' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Retry Failed' })).toBeDisabled();
    expect(screen.getByText(/Failed-topic retry becomes available/)).toBeInTheDocument();
  });

  it('enables retry only for terminally failed topics and sends failed scope', async () => {
    renderPanel(run('failed', ['points_of_interest']));

    const retry = screen.getByRole('button', { name: 'Retry Failed (1)' });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(JSON.parse(String(requests[0].init?.body))).toMatchObject({
      scope: { mode: 'failed' },
    });
  });
});
