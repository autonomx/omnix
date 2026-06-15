import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { PodcastWorkspace } from './PodcastWorkspace';

function renderPodcast() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'podcast');

  if (!module) {
    throw new Error('Podcast module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <PodcastWorkspace module={module} />
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

describe('PodcastWorkspace', () => {
  it('queues multi-stage podcast jobs through the shared jobs API', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json({
          providers: [
            {
              id: 'lmstudio',
              label: 'LM Studio',
              family: 'llm',
              source: 'settings',
              status: 'configured',
              capabilities: ['chat'],
            },
            {
              id: 'faster-qwen3-tts',
              label: 'Faster Qwen TTS',
              family: 'tts',
              source: 'settings',
              status: 'configured',
              capabilities: ['tts'],
            },
          ],
          models: [],
        });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json({
          id: 'job:podcast',
          module: 'podcast',
          type: 'podcast.generate',
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
              id: 'asset:script',
              module: 'podcast',
              type: 'podcast_script',
              mime_type: 'text/markdown',
              storage_path: 'artifacts/podcast.md',
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPodcast();

    expect(await screen.findByRole('heading', { name: 'Episode request' })).toBeInTheDocument();
    expect(await screen.findByText('Faster Qwen TTS')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'podcast_script / podcast' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('LLM provider'), { target: { value: 'lmstudio' } });
    fireEvent.change(screen.getByLabelText('TTS provider'), { target: { value: 'faster-qwen3-tts' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Signals' } });
    fireEvent.change(screen.getByLabelText('Brief'), { target: { value: 'Discuss local AI workstation design.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue episode' }));

    expect(await screen.findByText('Podcast job queued: job:podcast')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"podcast"');
      expect(createCall?.[1]?.body).toContain('"type":"podcast.generate"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:llm"');
      expect(createCall?.[1]?.body).toContain('"id":"voices"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:tts"');
    });
  });
});
