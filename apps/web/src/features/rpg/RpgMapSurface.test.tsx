import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgMapSurface } from './RpgMapSurface';

const polygon = { kind: 'polygon' as const, points: [[-110, -90], [110, -90], [110, 20], [-110, 20]] as [number, number][] };
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
      anchor: 'bottom_center' as const,
      location_id: 'rusty_flagon_tavern',
      label: 'The Frosted Flagon',
      description: 'A warm inn.',
      tags: ['inn'],
      render_order: { layer: 'structures' as const, sort_y: 420, offset: 0 },
      sprite: { asset_id: 'asset:inn', width: 220, height: 180 },
      footprint: polygon,
      hitbox: polygon,
      child_map_id: null,
    },
  ],
  route_geometry: [{
    route_id: 'route:frost_haven:inn_market',
    points: [[300, 420], [500, 360], [760, 330]] as [number, number][],
    style: 'street',
  }],
  labels: [{ id: 'label:frost_haven', text: 'FROST HAVEN', x: 500, y: 120, priority: 100 }],
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
    routes: [{ route_id: 'route:frost_haven:inn_market', status: 'open', known: true, safe: true, reason: '' }],
    markers: availability === 'ready'
      ? [
          { id: 'marker:player', kind: 'player', x: 300, y: 420, object_id: 'building:inn', label: 'You' },
          { id: 'marker:quest:shipment', kind: 'quest', x: 760, y: 330, object_id: null, label: 'Missing shipment' },
        ]
      : [],
    capabilities: [{
      type: 'inspect',
      enabled: true,
      target_object_id: 'building:inn',
      target_location_id: 'rusty_flagon_tavern',
      route_id: null,
      disabled_reason: '',
    }],
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

function installFetch(availability: 'ready' | 'unavailable' = 'ready') {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = requestPath(input);
    if (path.includes('/api/rpg/maps/')) {
      return Response.json({ ok: true, map_id: definition.map_id, definition_revision: definition.definition_revision, definition });
    }
    if (path.includes('/overlay')) {
      return Response.json({
        ok: true,
        map_id: definition.map_id,
        definition_revision: definition.definition_revision,
        overlay_revision: 2,
        session_turn_index: 5,
        overlay: overlay(availability),
      });
    }
    return new Response('not found', { status: 404 });
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgMapSurface', () => {
  it('renders objects, route geometry, labels, and authoritative markers', async () => {
    installFetch();
    const view = renderMap();

    expect(await screen.findByRole('img', { name: /interactive map/i })).toBeInTheDocument();
    expect(screen.getAllByText('The Frosted Flagon')).toHaveLength(2);
    expect(view.container.querySelector('[data-map-object-id="building:inn"]')).toBeInTheDocument();
    expect(view.container.querySelector('[data-map-hitbox="building:inn"]')).toHaveAttribute('points', '-110,-90 110,-90 110,20 -110,20');
    expect(view.container.querySelector('[data-map-route-id="route:frost_haven:inn_market"]')).toHaveAttribute('points', '300,420 500,360 760,330');
    expect(view.container.querySelector('[data-map-label-id="label:frost_haven"]')).toHaveTextContent('FROST HAVEN');
    expect(view.container.querySelector('[data-map-marker-kind="player"]')).toBeInTheDocument();
    expect(view.container.querySelector('[data-map-marker-kind="quest"]')).toHaveTextContent('Missing shipment');
    expect(screen.getByText('Definition abc123')).toBeInTheDocument();
  });

  it('toggles presentation layers without mutating map data', async () => {
    installFetch();
    const view = renderMap();
    await screen.findByRole('img', { name: /interactive map/i });

    fireEvent.click(screen.getByRole('checkbox', { name: 'routes' }));
    expect(view.container.querySelector('[data-map-layer="routes"]')).not.toBeInTheDocument();
    expect(view.container.querySelector('[data-map-object-id="building:inn"]')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: 'markers' }));
    expect(view.container.querySelector('[data-map-layer="markers"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: 'labels' }));
    expect(view.container.querySelector('[data-map-layer="labels"]')).not.toBeInTheDocument();
  });

  it('shows the same details for pointer hover and keyboard focus', async () => {
    installFetch();
    renderMap();
    const object = await screen.findByRole('button', { name: 'The Frosted Flagon map object' });

    fireEvent.mouseEnter(object);
    expect(screen.getByRole('tooltip')).toHaveTextContent('A warm inn.');
    fireEvent.mouseLeave(object);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    fireEvent.focus(object);
    expect(screen.getByRole('tooltip')).toHaveTextContent('The Frosted Flagon');
    fireEvent.blur(object);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('selects from the visual object and accessible list without changing location', async () => {
    installFetch();
    const view = renderMap();
    const object = await screen.findByRole('button', { name: 'The Frosted Flagon map object' });

    fireEvent.click(object);
    expect(screen.getByRole('region', { name: 'Selected map object' })).toHaveTextContent('A warm inn.');
    expect(screen.getByText('inspect')).toBeInTheDocument();
    expect(object).toHaveAttribute('aria-pressed', 'true');
    expect(view.container.querySelector('.rpg-map-object-selected')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Close selection' }));
    expect(screen.queryByRole('region', { name: 'Selected map object' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'The Frosted Flagon' })).toBeInTheDocument();
  });

  it('renders a truthful unavailable state without a player marker', async () => {
    installFetch('unavailable');
    const view = renderMap();

    expect(await screen.findByText('Live position unavailable')).toBeInTheDocument();
    expect(screen.getByText('current location unavailable')).toBeInTheDocument();
    await waitFor(() => expect(view.container.querySelector('[data-map-marker-kind="player"]')).not.toBeInTheDocument());
  });
});
