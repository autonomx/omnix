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
  it('queues TTS jobs through the shared jobs API and renders wired studio panels', async () => {
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
              capabilities: ['tts', 'voice_cloning'],
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
              id: 'voice-cloning:Dave',
              module: 'voice-cloning',
              type: 'voice_profile',
              mime_type: 'application/octet-stream',
              storage_path: 'resources/voice_clones/Dave.wav',
              created_at: '2026-06-14T00:00:00Z',
            },
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

    expect(await screen.findByRole('heading', { name: 'Clone a Voice' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Voice Library' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Text-to-Speech (Multi-Voice)' })).toBeInTheDocument();
    expect(screen.getByText('Dave')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Script'), { target: { value: 'Narrator: A short line for synthesis.' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate Speech/ }));

    expect(await screen.findByText('TTS job queued: job:tts')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"voice"');
      expect(createCall?.[1]?.body).toContain('"type":"tts.synthesize"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:tts"');
      expect(createCall?.[1]?.body).toContain('"provider_id":"faster-qwen3-tts"');
      expect(createCall?.[1]?.body).toContain('"output_settings"');
      expect(createCall?.[1]?.body).toContain('"character_voice_assignments"');
      expect(createCall?.[1]?.body).toContain('"audio_effects"');
    });
  });
});
