import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { RpgWorkspace } from './RpgWorkspace';

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RpgWorkspace campaign handoff', () => {
  it('surfaces a created campaign and queues the first turn for it', async () => {
    let inventoryReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        inventoryReads += 1;
        return Response.json({
          sessions:
            inventoryReads > 1
              ? [
                  {
                    session_id: 'rpg-created-1',
                    title: 'Created Campaign',
                    location: 'Rusty Flagon Tavern',
                    summary: 'A new campaign is ready at the tavern.',
                    turn_count: 0,
                    updated_at: '2026-06-20T00:00:00Z',
                  },
                ]
              : [],
          diagnostics: [],
        });
      }

      if (path === '/api/rpg/new-game' && init?.method === 'POST') {
        return Response.json({ ok: true, session_id: 'rpg-created-1', status: 'ready' });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json({
          id: 'job:rpg-created-turn',
          module: 'rpg',
          type: 'rpg.turn',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-20T00:00:01Z',
          updated_at: '2026-06-20T00:00:01Z',
          priority: 0,
        });
      }

      if (path === '/api/jobs') {
        return Response.json({ jobs: [] });
      }

      if (path === '/api/assets') {
        return Response.json({ assets: [] });
      }

      if (path === '/api/reports') {
        return Response.json({ reports: [] });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderRpg();

    expect(await screen.findByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Create Campaign' }));

    expect(await screen.findByRole('dialog', { name: 'Campaign Ready' })).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Created Campaign — rpg-created-1' })).toBeInTheDocument();
    expect(await screen.findByText('Created Campaign')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Enter World' }));

    await waitFor(() => {
      const commandInput = screen.getByLabelText('Command') as HTMLTextAreaElement;
      expect(commandInput.value).toContain('Session rpg-created-1 is ready');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Queue RPG turn' }));

    await waitFor(() => {
      const turnCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          requestPath(input as RequestInfo | URL) === '/api/jobs' &&
          init?.method === 'POST' &&
          String(init.body).includes('"type":"rpg.turn"'),
      );
      expect(String(turnCall?.[1]?.body)).toContain('"session_id":"rpg-created-1"');
    });
  });
});
