import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { RpgWorkspace } from './RpgWorkspace';

function renderRpg() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'rpg');

  if (!module) {
    throw new Error('RPG module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <RpgWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgWorkspace', () => {
  it('uses replay inventory and queues RPG turns through shared jobs', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        return Response.json({
          sessions: [{ session_id: 'rpg-session-1', updated_at: '2026-06-14T00:00:00Z' }],
          diagnostics: [],
        });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json({
          id: 'job:rpg',
          module: 'rpg',
          type: 'rpg.turn',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        });
      }

      if (path === '/api/jobs') {
        return Response.json({ jobs: [] });
      }

      if (path === '/api/assets') {
        return Response.json({
          assets: [
            {
              id: 'asset:checkpoint',
              module: 'rpg',
              type: 'rpg_checkpoint',
              mime_type: 'application/json',
              storage_path: 'checkpoints/session.json',
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      if (path === '/api/reports') {
        return Response.json({
          reports: [{ id: 'rpg/autoplay.json', kind: 'rpg_autoplay', path: 'reports/rpg/autoplay.json', size_bytes: 32 }],
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderRpg();

    expect(await screen.findByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'rpg-session-1' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'rpg_checkpoint / rpg' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Session'), { target: { value: 'rpg-session-1' } });
    fireEvent.change(screen.getByLabelText('Command'), { target: { value: 'Look around the tavern.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue RPG turn' }));

    expect(await screen.findByText('RPG turn job queued: job:rpg')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"rpg"');
      expect(createCall?.[1]?.body).toContain('"type":"rpg.turn"');
      expect(createCall?.[1]?.body).toContain('"determinism_policy":"replay_preserving"');
      expect(createCall?.[1]?.body).toContain('"session_id":"rpg-session-1"');
    });
  });
});
