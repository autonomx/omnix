import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { RpgMapSurface } from './RpgMapSurface';

const definition = {
  schema_version: 1,
  map_id: 'region:generated:northern_pass',
  level: 'region',
  definition_revision: 'sha256:generated-world-map',
  seed: 1,
  parent_map_id: null,
  bounds: { x: 0, y: 0, width: 1200, height: 800 },
  background: {
    asset_id: 'asset:rpg-map:northern-pass-base',
    destination_bounds: { x: 0, y: 0, width: 1200, height: 800 },
    source_crop: null,
  },
  route_geometry: [],
  labels: [],
  objects: [],
};

const overlay = {
  map_id: definition.map_id,
  session_id: 'session:test',
  definition_revision: definition.definition_revision,
  overlay_revision: 0,
  session_turn_index: 0,
  availability: 'ready',
  unavailable_reason: '',
  current_location_id: 'tidebreak_docks',
  discovered_object_ids: [],
  visible_object_ids: [],
  object_states: [],
  fog_polygons: [],
  routes: [],
  markers: [],
  capabilities: [],
  environment: {},
};

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

afterEach(() => vi.unstubAllGlobals());

it('replaces fixture map art with the generated map from the session world', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = requestPath(input);
    if (path.includes('/image-targets')) {
      return Response.json({
        ok: true,
        world: { id: 'world:test' },
        targets: [{
          world_id: 'world:test',
          target_id: 'world:map',
          target_type: 'world',
          entity_id: 'world:test',
          role: 'map',
          source_content_hash: 'hash',
          status: 'completed',
          review_state: 'approved',
          suggested_prompt: 'map',
          active_asset_id: 'asset:generated-tidebreak-atlas',
          latest_job_id: null,
          metadata: {},
          attempts: [],
          created_at: '2026-07-31T00:00:00Z',
          updated_at: '2026-07-31T00:00:00Z',
        }],
      });
    }
    if (path.includes('/overlay')) {
      return Response.json({
        ok: true,
        map_id: definition.map_id,
        definition_revision: definition.definition_revision,
        overlay_revision: 0,
        session_turn_index: 0,
        overlay,
      });
    }
    if (path.includes('/api/rpg/maps/')) {
      return Response.json({
        ok: true,
        map_id: definition.map_id,
        definition_revision: definition.definition_revision,
        definition,
      });
    }
    if (path.includes('/api/rpg/sessions/')) {
      return Response.json({
        ok: true,
        session_id: 'session:test',
        session: {
          manifest: { world_id: 'world:test' },
          state: { map_state: { current_location_id: 'tidebreak_docks' } },
        },
      });
    }
    return new Response('not found', { status: 404 });
  }));

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <RpgMapSurface mapId={definition.map_id} sessionId="session:test" />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('img', { name: /interactive map/i })).toBeInTheDocument();
  await waitFor(() => {
    const background = view.container.querySelector('[data-map-asset-id="asset:generated-tidebreak-atlas"]');
    expect(background).toHaveAttribute('href', '/api/assets/asset%3Agenerated-tidebreak-atlas/file');
  });
  expect(view.container.querySelector('[data-map-asset-id="asset:rpg-map:northern-pass-base"]')).not.toBeInTheDocument();
});
