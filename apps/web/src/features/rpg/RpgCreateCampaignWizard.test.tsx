import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgCreateCampaignWizard } from './RpgCreateCampaignWizard';

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string'
    ? new URL(input, 'http://localhost').pathname
    : new URL(input.toString(), 'http://localhost').pathname;
}

function renderWizard() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
        <RpgCreateCampaignWizard />
      </MantineProvider>
    </QueryClientProvider>,
  );
}

const world = {
  id: 'world:aurelia',
  title: 'Aurelia: Echoes Beyond the Gate',
  description: 'A reusable fantasy isekai world.',
  status: 'published',
  source_mode: 'imported',
  genre: 'fantasy_isekai',
  tone: 'heroic wonder',
  seed: 482193,
  draft_revision: 1,
  metadata: {},
  scenario_count: 1,
  generation: null,
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
};

const scenario = {
  id: 'scenario:aurelia:arrival',
  world_id: world.id,
  title: 'Beyond the Broken Gate',
  description: 'Arrive in Starfall Grove.',
  status: 'published',
  metadata: {},
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
};

const scenarioRevision = {
  revision: 1,
  world_id: world.id,
  world_revision: 1,
  document: {
    compatible_release: 1,
    starting_location_id: 'location:aurelia:starfall-grove',
  },
  content_hash: 'sha256:scenario',
  created_at: '2026-07-17T00:00:00Z',
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
  created_at: '2026-07-17T00:00:00Z',
};

function libraryPayload() {
  return {
    ok: true,
    worlds: [world],
    scenarios: [scenario],
    campaigns: [],
    generation_runs: [],
  };
}

function detailPayload() {
  return {
    ok: true,
    world,
    topics: [],
    map_blueprints: [],
    revisions: [],
    releases: [release],
    scenarios: [scenario],
    scenario_revisions: { [scenario.id]: [scenarioRevision] },
    generation_runs: [],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgCreateCampaignWizard', () => {
  it('keeps character setup but requires a reusable world instead of offering World Forge', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (requestPath(input) === '/api/rpg/world-library') {
        return Response.json({
          ok: true,
          worlds: [],
          scenarios: [],
          campaigns: [],
          generation_runs: [],
        });
      }
      return new Response('not found', { status: 404 });
    }));
    renderWizard();

    expect(screen.queryByText('World Forge depth')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Create Campaign' })).toBeInTheDocument();
    expect(screen.getByLabelText('Secondary capabilities')).toHaveTextContent('Combat');
    expect(screen.getByText('Opening story')).toBeInTheDocument();
    expect(screen.getByText('Starter gear')).toBeInTheDocument();
    expect(await screen.findByText(/Create or import a world in Worlds & Campaigns/i)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Existing world' })).toBeDisabled();
  });

  it('launches a published scenario from the selected existing world without creating a world', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/rpg/world-library') {
        return Response.json(libraryPayload());
      }
      if (path === `/api/rpg/worlds/${encodeURIComponent(world.id)}/library`) {
        return Response.json(detailPayload());
      }
      if (
        path === `/api/rpg/scenarios/${encodeURIComponent(scenario.id)}/revisions/1/launch`
        && init?.method === 'POST'
      ) {
        return Response.json({
          ok: true,
          status: 'ready',
          session_id: 'campaign:aurelia:one',
          world_forge_invoked: false,
        });
      }
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWizard();

    expect(screen.queryByText('World Forge depth')).not.toBeInTheDocument();
    const worldSelect = await screen.findByRole('combobox', { name: 'Existing world' });
    await waitFor(() => expect(worldSelect).toHaveValue(world.id));
    const scenarioSelect = screen.getByRole('combobox', { name: 'Published scenario' });
    await waitFor(() => expect(scenarioSelect).toHaveValue(scenario.id));
    expect(screen.getByText(/does not create or regenerate a world/i)).toBeInTheDocument();
    expect(await screen.findByText(`Ready: ${world.title} · ${scenario.title}`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      `/api/rpg/scenarios/${encodeURIComponent(scenario.id)}/revisions/1/launch`,
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === '/api/rpg/new-game')).toBe(false);
    expect(await screen.findByRole('dialog', { name: 'Campaign Ready' })).toBeInTheDocument();
    expect(screen.getByText('Session campaign:aurelia:one')).toBeInTheDocument();
  });
});
