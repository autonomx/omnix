import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { VoiceWorkspace } from './VoiceWorkspace';

function renderVoice() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'voice');

  if (!module) {
    throw new Error('Voice module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <VoiceWorkspace module={module} />
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

describe('VoiceWorkspace', () => {
  it('queues TTS jobs through the shared jobs API and renders audio assets', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json({
          providers: [
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
          id: 'job:tts',
          module: 'voice',
          type: 'tts.synthesize',
          status: 'queued',
          resource_class: 'gpu:tts',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
          progress: { current: 0, total: 1 },
        });
      }

      if (path === '/api/jobs') {
        return Response.json({
          jobs: [
            {
              id: 'job:existing',
              module: 'voice',
              type: 'tts.synthesize',
              status: 'running',
              resource_class: 'gpu:tts',
              created_at: '2026-06-14T00:00:00Z',
              updated_at: '2026-06-14T00:00:01Z',
              priority: 0,
              progress: { current: 1, total: 2 },
            },
          ],
        });
      }

      if (path === '/api/assets') {
        return Response.json({
          assets: [
            {
              id: 'asset:audio',
              module: 'voice',
              type: 'audio',
              mime_type: 'audio/wav',
              storage_path: 'artifacts/voice.wav',
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderVoice();

    expect(await screen.findByRole('heading', { name: 'Synthesis' })).toBeInTheDocument();
    expect(await screen.findByText('Faster Qwen TTS')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'audio / voice' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'faster-qwen3-tts' } });
    fireEvent.change(screen.getByLabelText('Speaker'), { target: { value: 'Narrator' } });
    fireEvent.change(screen.getByLabelText('Text'), { target: { value: 'A short line for synthesis.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue synthesis' }));

    expect(await screen.findByText('TTS job queued: job:tts')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"voice"');
      expect(createCall?.[1]?.body).toContain('"type":"tts.synthesize"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:tts"');
      expect(createCall?.[1]?.body).toContain('"provider_id":"faster-qwen3-tts"');
    });
  });
});
