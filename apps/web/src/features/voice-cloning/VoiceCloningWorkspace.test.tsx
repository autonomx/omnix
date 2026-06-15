import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { VoiceCloningWorkspace } from './VoiceCloningWorkspace';

function renderVoiceCloning() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'voice-cloning');

  if (!module) {
    throw new Error('Voice Cloning module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <VoiceCloningWorkspace module={module} />
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

describe('VoiceCloningWorkspace', () => {
  it('queues voice profile jobs through the shared jobs API', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json({
          providers: [
            {
              id: 'qwen-voice',
              label: 'Qwen Voice',
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
          id: 'job:voice-profile',
          module: 'voice-cloning',
          type: 'voice-cloning.train',
          status: 'queued',
          resource_class: 'gpu:tts',
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
              id: 'asset:sample',
              module: 'voice-cloning',
              type: 'voice_sample',
              mime_type: 'audio/wav',
              storage_path: 'samples/ref.wav',
              created_at: '2026-06-14T00:00:00Z',
            },
            {
              id: 'asset:profile',
              module: 'voice-cloning',
              type: 'voice_profile',
              mime_type: 'application/json',
              storage_path: 'profiles/narrator.json',
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderVoiceCloning();

    expect(await screen.findByRole('heading', { name: 'Voice profile' })).toBeInTheDocument();
    expect(await screen.findByText('Qwen Voice')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'voice_profile / voice-cloning' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'qwen-voice' } });
    fireEvent.change(screen.getByLabelText('Sample asset'), { target: { value: 'asset:sample' } });
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'Narrator' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue voice profile' }));

    expect(await screen.findByText('Voice profile job queued: job:voice-profile')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"voice-cloning"');
      expect(createCall?.[1]?.body).toContain('"type":"voice-cloning.train"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:tts"');
      expect(createCall?.[1]?.body).toContain('"sample_asset_id":"asset:sample"');
    });
  });
});
