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

const invalidBlueprint = {
  world_id: world.id,
  map_id: 'map:harbor',
  blueprint_revision: 1,
  document: {
    schema_version: 'rpg_map_blueprint_v1',
    map_id: 'map:harbor',
    location_id: 'location:harbor',
    level: 'settlement',
    navigation_kind: 'square_grid',
    required_portal_ids: [],
    required_route_ids: [],
    required_spawn_point_ids: [],
    required_zone_ids: [],
    required_object_ids: [],
    required_hazard_ids: [],
    size_profile: 'medium',
    directives: {},
    metadata: {},
  },
  content_hash: 'sha256:blueprint-one',
  semantic_interface_hash: 'sha256:semantic-one',
  status: 'invalid',
  findings: [{
    code: 'scenario_spawn_missing',
    scenario_id: scenario.id,
    scenario_revision: 1,
    operation_id: 'init:captain',
    target_id: 'spawn:office',
  }],
  created_at: '2026-07-16T00:00:00Z',
};

function libraryPayload() {
  return {
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
  };
}

function detailPayload() {
  return {
    ok: true,
    world,
    topics: [
      {
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
      },
      {
        topic_id: 'locations',
        draft_revision: 1,
        source: 'ai',
        status: 'ready',
        content: {
          entities: [{ location_id: 'loc:glitch_bar', name: 'The Glitch Bar' }],
        },
        directives: {},
        dependency_hashes: {},
        input_hash: 'sha256:locations-input',
        content_hash: 'sha256:locations-topic',
        provenance: {},
        updated_at: '2026-07-16T00:00:00Z',
      },
    ],
    map_blueprints: [invalidBlueprint],
    revisions: [{
      revision: 1,
      document: {
        topology: {
          locations: ['location:harbor', 'location:citadel'],
        },
        canon: {
          entities: {
            'location:harbor': { kind: 'location', name: 'Storm Harbor' },
            'location:citadel': { kind: 'location', name: 'High Citadel' },
          },
        },
        blueprint_requirements: [{
          map_id: 'map:harbor',
          location_id: 'location:harbor',
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
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgWorldsCampaignsLibrary', () => {
  it('surfaces reusable-world authoring, blueprint reconciliation, lifecycle, and launch views', async () => {
    let scenarioPublishAttempts = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/rpg/world-library') {
        return Response.json(libraryPayload());
      }
      if (path === `/api/rpg/worlds/${encodeURIComponent(world.id)}/library`) {
        return Response.json(detailPayload());
      }
      if (
        path === `/api/rpg/worlds/${encodeURIComponent(world.id)}/map-blueprints/${encodeURIComponent('map:harbor')}`
        && init?.method === 'POST'
      ) {
        return Response.json({
          ok: true,
          map_blueprint: {
            ...invalidBlueprint,
            blueprint_revision: 2,
            status: 'ready',
            findings: [],
            content_hash: 'sha256:blueprint-two',
            semantic_interface_hash: 'sha256:semantic-two',
          },
        });
      }
      if (
        path === `/api/rpg/worlds/${encodeURIComponent(world.id)}/archive`
        && init?.method === 'POST'
      ) {
        return Response.json({ ok: true, world: { ...world, status: 'archived' }, idempotent: false });
      }
      if (
        path === `/api/rpg/scenarios/${encodeURIComponent(scenario.id)}/archive`
        && init?.method === 'POST'
      ) {
        return Response.json({ ok: true, scenario: { ...scenario, status: 'archived' }, idempotent: false });
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
      if (
        path === `/api/rpg/scenarios/${encodeURIComponent(scenario.id)}/revisions`
        && init?.method === 'POST'
      ) {
        scenarioPublishAttempts += 1;
        if (scenarioPublishAttempts === 1) {
          return Response.json(
            { detail: { ok: false, error: 'scenario_starting_map_missing:location:harbor' } },
            { status: 409 },
          );
        }
        return Response.json({
          ok: true,
          scenario_revision: { ...scenarioRevision, revision: 2, world_revision: 2 },
        });
      }
      if (
        path === `/api/rpg/worlds/${encodeURIComponent(world.id)}/starter-bubble/promote`
        && init?.method === 'POST'
      ) {
        return Response.json({
          ok: true,
          status: 'ready',
          reused: false,
          promotion: {
            world_revision: 2,
            world_revision_hash: 'sha256:promoted-revision',
            world_release: 1,
          },
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
    expect(screen.getByRole('heading', { name: 'Blueprint revisions' })).toBeInTheDocument();
    expect(screen.getByText(/scenario_spawn_missing/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Published releases' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Campaign openings' })).toBeInTheDocument();
    const openingLocation = screen.getByRole('combobox', { name: 'Starting location' });
    expect(openingLocation).toHaveValue('location:harbor');
    expect(screen.getByRole('option', { name: 'Storm Harbor (location:harbor)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'High Citadel (location:citadel)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'The Glitch Bar (loc:glitch_bar)' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Use existing scenario' }));
    expect(await screen.findByText(/Using existing published scenario: Opening Scenario/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input) === '/api/rpg/scenarios')).toBe(false);

    expect(screen.getByRole('button', { name: 'Scenario already published' })).toBeDisabled();
    fireEvent.change(openingLocation, { target: { value: 'location:citadel' } });
    fireEvent.click(screen.getByRole('button', { name: 'Publish new scenario revision' }));
    expect(await screen.findByText(/Scenario revision published: 2 after preparing starter maps in world revision 2/)).toBeInTheDocument();
    expect(scenarioPublishAttempts).toBe(2);
    expect(fetchMock.mock.calls.some(([input]) => (
      requestPath(input) === `/api/rpg/worlds/${encodeURIComponent(world.id)}/starter-bubble/promote`
    ))).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Edit next revision' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save blueprint revision' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      `/api/rpg/worlds/${encodeURIComponent(world.id)}/map-blueprints/${encodeURIComponent('map:harbor')}`,
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByText(/Blueprint map:harbor r2 is ready/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Archive world' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      `/api/rpg/worlds/${encodeURIComponent(world.id)}/archive`,
      expect.objectContaining({ method: 'POST' }),
    ));

    fireEvent.click(screen.getByRole('button', { name: 'Archive scenario' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      `/api/rpg/scenarios/${encodeURIComponent(scenario.id)}/archive`,
      expect.objectContaining({ method: 'POST' }),
    ));

    fireEvent.click(screen.getByRole('button', { name: 'Launch campaign' }));
    await waitFor(() => expect(onSessionLaunched).toHaveBeenCalledWith('campaign:launched'));

    fireEvent.click(screen.getByRole('button', { name: 'Campaigns' }));
    expect(screen.getByRole('heading', { name: 'Campaign One' })).toBeInTheDocument();
  });
});
