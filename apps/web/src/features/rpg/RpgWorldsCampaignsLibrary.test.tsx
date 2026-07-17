import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgWorldsCampaignsLibrary } from './RpgWorldsCampaignsLibrary';

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string'
    ? new URL(input, 'http://localhost').pathname
    : new URL(input.toString(), 'http://localhost').pathname;
}

function renderLibrary(onSessionLaunched = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return {
    onSessionLaunched,
    ...render(
      <QueryClientProvider client={client}>
        <RpgWorldsCampaignsLibrary onBack={vi.fn()} onSessionLaunched={onSessionLaunched} />
      </QueryClientProvider>,
    ),
  };
}

const world = {
  id: 'world:published',
  title: 'Publication World',
  description: 'A reusable world with immutable releases.',
  status: 'published',
  source_mode: 'hybrid',
  genre: 'classic_fantasy',
  tone: 'mythic',
  seed: 23,
  draft_revision: 2,
  metadata: {},
  scenario_count: 1,
  generation: null,
  created_at: '2026-07-16T00:00:00Z',
  updated_at: '2026-07-16T00:00:00Z',
};

const release = {
  world_revision: 1,
  release: 1,
  document: {
    certification: {
      launch_ready: true,
      missing_requirements: [],
    },
  },
  release_hash: 'sha256:release',
  created_at: '2026-07-16T00:00:00Z',
};

const scenario = {
  id: 'scenario:opening',
  world_id: world.id,
  title: 'Opening Scenario',
  description: 'Start in the harbor.',
  status: 'published',
  metadata: {},
  created_at: '2026-07-16T00:00:00Z',
  updated_at: '2026-07-16T00:00:00Z',
};

const scenarioRevision = {
  revision: 1,
  world_id: world.id,
  world_revision: 1,
  document: { compatible_release: 1, starting_location_id: 'location:harbor' },
  content_hash: 'sha256:scenario',
  created_at: '2026-07-16T00:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgWorldsCampaignsLibrary', () => {
  it('surfaces reusable-world authoring, validation, release, and scenario launch views', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/rpg/world-library') {
        return Response.json({
          ok: true,
          worlds: [world],
          scenarios: [scenario],
          campaigns: [{
            campaign_id: 'campaign:one',
            title: 'Campaign One',
            status: 'active',
            revision: 0,
            updated_at: '2026-07-16T00:00:00Z',
            world_id: world.id,
            world_revision: 1,
            world_release: 1,
            scenario_id: scenario.id,
            scenario_revision: 1,
            binding: {},
          }],
          generation_runs: [],
        });
      }
      if (path === `/api/rpg/worlds/${encodeURIComponent(world.id)}/library`) {
        return Response.json({
          ok: true,
          world,
          topics: [{
            topic_id: 'realm',
            draft_revision: 1,
            source: 'ai',
            status: 'ready',
            content: {},
            directives: {},
            dependency_hashes: {},
            input_hash: 'sha256:input',
            content_hash: 'sha256:topic',
            provenance: {},
            updated_at: '2026-07-16T00:00:00Z',
          }],
          revisions: [{
            revision: 1,
            document: {
              blueprint_requirements: [{
                map_id: 'map:harbor',
                simulation_readiness: 'semantic',
                presentation_readiness: 'placeholder',
              }],
            },
            content_hash: 'sha256:revision',
            created_at: '2026-07-16T00:00:00Z',
          }],
          releases: [release],
          scenarios: [scenario],
          scenario_revisions: { [scenario.id]: [scenarioRevision] },
          generation_runs: [],
        });
      }
      if (
        path === `/api/rpg/scenarios/${encodeURIComponent(scenario.id)}/revisions/1/launch`
        && init?.method === 'POST'
      ) {
        return Response.json({
          ok: true,
          status: 'ready',
          session_id: 'campaign:launched',
          world_forge_invoked: false,
        });
      }
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const onSessionLaunched = vi.fn();
    renderLibrary(onSessionLaunched);

    expect(await screen.findByRole('heading', { name: 'Publication World' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'World generation' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Launch ready' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Map-blueprint requirements' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Published releases' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Campaign openings' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Launch campaign' }));
    await waitFor(() => expect(onSessionLaunched).toHaveBeenCalledWith('campaign:launched'));

    fireEvent.click(screen.getByRole('button', { name: 'Campaigns' }));
    expect(screen.getByRole('heading', { name: 'Campaign One' })).toBeInTheDocument();
  });
});
