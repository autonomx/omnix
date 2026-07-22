import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RpgAuthoringSection } from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import { RpgWorldGenerationDashboard } from './RpgWorldGenerationDashboard';

const section: RpgAuthoringSection = {
  id: 'regions',
  label: 'Regions',
  group: 'world',
  page_kind: 'collection',
  topic_ids: ['regions'],
  entity_kind: 'region',
  dependencies: [],
  required_before_launch: true,
  supports_generation: true,
  supports_images: true,
  supports_entity_editing: true,
  operational_status: 'complete',
  editorial_status: 'unreviewed',
  entity_count: 4,
};

const previousRun: RpgWorldGenerationRun = {
  run_id: 'run:previous',
  world_id: 'world:aurelia',
  draft_revision: 2,
  status: 'review',
  graph: {},
  context: {},
  settings: { provider_route: 'lmstudio', model: 'qwen-world' },
  plan: {},
  progress: { percent: 100, active_topic_ids: [], failed_topic_ids: [] },
  error: {},
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
};

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RpgWorldGenerationDashboard
        generation={previousRun}
        sections={[section]}
        worldId="world:aurelia"
      />
    </QueryClientProvider>,
  );
}

describe('RpgWorldGenerationDashboard', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('starts generation from the prominent Generate World action even when controls are collapsed', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return new Response(JSON.stringify({
        ok: true,
        worker_started: true,
        run: {
          ...previousRun,
          run_id: 'run:new',
          status: 'running',
          progress: { percent: 0, active_topic_ids: ['regions'], failed_topic_ids: [] },
          settings: { provider_route: 'lmstudio', model: 'qwen-world' },
        },
        execution_summary: {
          queued_count: 1,
          reused_count: 0,
          protected_count: 0,
        },
        resolved_route: {
          provider: 'lmstudio',
          model: 'qwen-world',
          source: 'settings_control_center',
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));

    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: '✦ Generate World' }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].url).toContain('/api/rpg/worlds/world%3Aaurelia/generation');
    expect(JSON.parse(String(requests[0].init?.body))).toMatchObject({
      scope: { mode: 'full' },
      provider_route: 'configured',
      model: 'configured',
    });
    expect(await screen.findByText(/1 provider topic job queued/)).toBeInTheDocument();
  });
});
