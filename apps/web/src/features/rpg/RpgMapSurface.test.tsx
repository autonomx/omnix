import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgMapSurface } from './RpgMapSurface';

const definition = {
  schema_version: 1,
  map_id: 'settlement:frost_haven',
  level: 'settlement',
  definition_revision: 'sha256:abc123',
  seed: 1,
  parent_map_id: 'region:northern_pass',
  bounds: { x: 0, y: 0, width: 1000, height: 600 },
  background: null,
  objects: [
    {
      id: 'building:inn',
      kind: 'building',
      x: 300,
      y: 420,
      anchor: 'bottom_center',
      location_id: 'rusty_flagon_tavern',
      label: 'The Frosted Flagon',
      description: 'A warm inn.',
      tags: ['inn'],
      render_order: { layer: 'structures', sort_y: 420, offset: 0 },
      sprite: { asset_id: 'asset:inn', width: 220, height: 180 },
      footprint: null,
      hitbox: null,
      child_map_id: null,
    },
  ],
  route_geometry: [],
  labels: [],
};

function overlay(availability: 'ready' | 'unavailable' = 'ready') {
  return {
    map_id: 'settlement:frost_haven',
    session_id: 'session:test',
    definition_revision: 'sha256:abc123',
    overlay_revision: 2,
    session_turn_index: 5,
    availability,
    unavailable_reason: availability === 'ready' ? '' : 'current_location_unavailable',
    current_location_id: availability === 'ready' ? 'rusty_flagon_tavern' : null,
    discovered_object_ids: ['building:inn'],
    visible_object_ids: ['building:inn'],
    routes: [],
    markers: availability === 'ready'
      ? [{ id: 'marker:player', kind: 'player', x: 300, y: 420, object_id: 'building:inn', label: 'You' }]
      : [],
    capabilities: [],
    environment: { weather: 'Clear' },
  };
}

function renderMap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RpgMapSurface mapId="settlement:frost_haven" sessionId="session:test" />
    </QueryClientProvider>,
  );
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgMapSurface', () => {
  it('renders definition objects and the authoritative player marker', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/rpg/maps/settlement%3Afrost_haven') {
        return Response.json({ ok: true, map_id: definition.map_id, definition_revision: definition.definition_revision, definition });
      }
      if (path === '/api/rpg/sessions/session%3Atest/maps/settlement%3Afrost_haven/overlay') {
        return Response.json({
          ok: true,
          map_id: definition.map_id,
          definition_revision: definition.definition_revision,
          overlay_revision: 2,
          session_turn_index: 5,
          overlay: overlay(),
        });
      }
      return new Response('not found', { status: 404 });
    }));

    const view = renderMap();

    expect(await screen.findByRole('img', { name: /interactive map/i })).toBeInTheDocument();
    expect(screen.getAllByText('The Frosted Flagon')).toHaveLength(2);
    expect(view.container.querySelector('[data-map-object-id="building:inn"]')).toBeInTheDocument();
    expect(view.container.querySelector('.rpg-map-player-marker')).toBeInTheDocument();
    expect(screen.getByText('Definition abc123')).toBeInTheDocument();
  });

  it('renders a truthful unavailable state without a player marker', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path.includes('/api/rpg/maps/')) {
        return Response.json({ ok: true, map_id: definition.map_id, definition_revision: definition.definition_revision, definition });
      }
      return Response.json({
        ok: true,
        map_id: definition.map_id,
        definition_revision: definition.definition_revision,
        overlay_revision: 2,
        session_turn_index: 5,
        overlay: overlay('unavailable'),
      });
    }));

    const view = renderMap();

    expect(await screen.findByText('Live position unavailable')).toBeInTheDocument();
    expect(screen.getByText('current location unavailable')).toBeInTheDocument();
    await waitFor(() => expect(view.container.querySelector('.rpg-map-player-marker')).not.toBeInTheDocument());
  });
});
