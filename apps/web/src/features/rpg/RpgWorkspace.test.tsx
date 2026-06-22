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

const emptyWorkspaceResponses = {
  inventory: {
    sessions: [{ session_id: 'rpg-session-1', updated_at: '2026-06-14T00:00:00Z' }],
    diagnostics: [],
  },
  jobs: { jobs: [] },
  assets: {
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
  },
  reports: {
    reports: [{ id: 'rpg/autoplay.json', kind: 'rpg_autoplay', path: 'reports/rpg/autoplay.json', size_bytes: 32 }],
  },
};

function stubEmptyWorkspaceFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input);

    if (path === '/api/replay/persistence/inventory') {
      return Response.json(emptyWorkspaceResponses.inventory);
    }

    if (path === '/api/jobs') {
      return Response.json(emptyWorkspaceResponses.jobs);
    }

    if (path === '/api/assets') {
      return Response.json(emptyWorkspaceResponses.assets);
    }

    if (path === '/api/reports') {
      return Response.json(emptyWorkspaceResponses.reports);
    }

    return new Response(init?.method ?? 'not found', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.documentElement.classList.remove('rpg-play-focus-mode');
});

describe('RpgWorkspace', () => {
  it('uses replay inventory and queues RPG turns through shared jobs', async () => {
    let turnQueued = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        return Response.json(emptyWorkspaceResponses.inventory);
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        turnQueued = true;
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
        if (turnQueued) {
          return new Promise<Response>(() => undefined);
        }
        return Response.json(emptyWorkspaceResponses.jobs);
      }

      if (path === '/api/assets') {
        return Response.json(emptyWorkspaceResponses.assets);
      }

      if (path === '/api/reports') {
        return Response.json(emptyWorkspaceResponses.reports);
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderRpg();

    expect(await screen.findByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'rpg-session-1' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'rpg_checkpoint / rpg' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Session')).toHaveValue('rpg-session-1'));

    fireEvent.change(screen.getByLabelText('Command'), { target: { value: 'Look around the tavern.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue RPG turn' }));

    expect(await screen.findByText('RPG turn job queued: job:rpg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Queue RPG turn' })).toBeEnabled();

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

  it('surfaces a timeout when the RPG turn queue request is not acknowledged', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        return Promise.resolve(Response.json(emptyWorkspaceResponses.inventory));
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
        });
      }

      if (path === '/api/jobs') {
        return Promise.resolve(Response.json(emptyWorkspaceResponses.jobs));
      }

      if (path === '/api/assets') {
        return Promise.resolve(Response.json(emptyWorkspaceResponses.assets));
      }

      if (path === '/api/reports') {
        return Promise.resolve(Response.json(emptyWorkspaceResponses.reports));
      }

      return Promise.resolve(new Response('not found', { status: 404 }));
    });
    vi.stubGlobal('fetch', fetchMock);

    renderRpg();

    expect(await screen.findByRole('heading', { name: 'Turn request' })).toBeInTheDocument();

    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText('Command'), { target: { value: 'Look around the tavern.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue RPG turn' }));

    await vi.waitFor(() => {
      expect(screen.getByText('Queueing RPG turn job…')).toBeInTheDocument();
    });

    await vi.advanceTimersByTimeAsync(10_000);

    await vi.waitFor(() => {
      expect(screen.getByText(/Gateway did not acknowledge the RPG turn queue request within 10s/)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Queue RPG turn' })).toBeEnabled();
  });

  it('wires checkpoint and autoplay controls through replay-safe APIs', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        return Response.json({
          sessions: [
            {
              session_id: 'rpg-session-2',
              title: 'North Road Campaign',
              location: 'North Road',
              summary: 'The party waits near the northern milestone.',
              turn_count: 8,
              checkpoint_id: 'checkpoint:last',
              updated_at: '2026-06-14T00:05:00Z',
            },
          ],
          diagnostics: [],
        });
      }

      if (path === '/api/replay/checkpoints' && init?.method === 'POST') {
        return Response.json({ checkpoint_id: 'checkpoint:manual', metadata: {}, payload: {} });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json({
          id: 'job:autoplay',
          module: 'rpg',
          type: 'rpg.autoplay',
          status: 'queued',
          resource_class: 'gpu:llm',
          created_at: '2026-06-14T00:05:01Z',
          updated_at: '2026-06-14T00:05:01Z',
          priority: 0,
        });
      }

      if (path === '/api/jobs') {
        return Response.json(emptyWorkspaceResponses.jobs);
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

    expect(await screen.findByText('North Road')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Create checkpoint' }));
    expect(await screen.findByText('Checkpoint created: checkpoint:manual')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Start autoplay' }));

    await waitFor(() => {
      const checkpointCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/replay/checkpoints' && init?.method === 'POST',
      );
      const autoplayCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );

      expect(String(checkpointCall?.[1]?.body)).toContain('"source":"rpg-workspace"');
      expect(String(checkpointCall?.[1]?.body)).toContain('"session_id":"rpg-session-2"');
      expect(String(autoplayCall?.[1]?.body)).toContain('"type":"rpg.autoplay"');
      expect(String(autoplayCall?.[1]?.body)).toContain('"determinism_policy":"replay_preserving"');
      expect(String(autoplayCall?.[1]?.body)).toContain('"session_id":"rpg-session-2"');
    });
  });

  it('preserves accessible controls when the player and world rails are collapsed', async () => {
    stubEmptyWorkspaceFetch();

    renderRpg();

    expect(screen.getByRole('button', { name: 'Show RPG headers' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide player rail' })).toBeInTheDocument();
    expect(await screen.findByRole('complementary', { name: 'Player, party, and quests' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'World, jobs, and reports' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Contain player rail' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Contain world rail' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('complementary', { name: 'Player, party, and quests' })).toHaveClass('rpg-rail-full-size');
    expect(screen.getByRole('complementary', { name: 'World, jobs, and reports' })).toHaveClass('rpg-rail-full-size');

    fireEvent.click(screen.getByRole('button', { name: 'Hide player rail' }));
    fireEvent.click(screen.getByRole('button', { name: 'Hide world rail' }));

    expect(screen.queryByRole('complementary', { name: 'Player, party, and quests' })).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: 'World, jobs, and reports' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show player rail' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Show world rail' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: 'Turn request' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show player rail' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show world rail' }));

    expect(screen.getByRole('complementary', { name: 'Player, party, and quests' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'World, jobs, and reports' })).toBeInTheDocument();
  });

  it('starts in RPG play focus chrome mode and can show or hide the header', async () => {
    stubEmptyWorkspaceFetch();

    renderRpg();

    expect(await screen.findByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    await waitFor(() => {
      expect(document.documentElement).toHaveClass('rpg-play-focus-mode');
    });
    expect(screen.queryByRole('button', { name: 'New Campaign' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Campaign Menu' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide player rail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show RPG headers' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Expand header' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show RPG headers' }));

    await waitFor(() => {
      expect(document.documentElement).not.toHaveClass('rpg-play-focus-mode');
    });
    expect(screen.getByRole('button', { name: 'Expand header' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Hide header' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Hide header' }));

    await waitFor(() => {
      expect(document.documentElement).toHaveClass('rpg-play-focus-mode');
    });
    expect(screen.getByRole('button', { name: 'Show RPG headers' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
  });

  it('surfaces live data empty and error states while keeping preview fallback usable', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);

      if (path === '/api/replay/persistence/inventory') {
        return Response.json({ sessions: [], diagnostics: [] });
      }

      if (path === '/api/jobs') {
        return new Response('job queue unavailable', { status: 500 });
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

    expect(await screen.findByRole('region', { name: 'RPG live data status' })).toBeInTheDocument();
    expect(await screen.findByText('1 source need attention')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Expand live data' }));

    expect(await screen.findByText('Omnix API request failed with status 500')).toBeInTheDocument();
    expect(screen.getByLabelText('Sessions status')).toHaveTextContent('Empty');
    expect(screen.getByLabelText('Jobs status')).toHaveTextContent('Error');
    expect(screen.getByLabelText('Checkpoints status')).toHaveTextContent('Empty');
    expect(screen.getByLabelText('Reports status')).toHaveTextContent('Empty');
    expect(screen.getByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
  });
});
