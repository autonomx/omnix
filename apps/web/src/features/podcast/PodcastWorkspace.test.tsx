import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { PodcastWorkspace } from './PodcastWorkspace';

const GENERATED_AUDIO_DATA_URL = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=';

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
  it('queues podcast voice generation through the Voice Studio TTS path and exposes playback audio', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/assets') {
        return Response.json({
          assets: [
            {
              id: 'voice-cloning:alex',
              module: 'voice-cloning',
              type: 'voice_profile',
              mime_type: 'audio/wav',
              storage_path: 'resources/voice_clones/alex.wav',
              metadata: { profile_name: 'Alex Voice' },
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body));
        return Response.json({
          id: 'job:podcast',
          module: 'podcast',
          type: body.type,
          status: 'completed',
          resource_class: body.resource_class,
          input_payload: body.input_payload,
          stages: body.stages,
          output_refs: [
            {
              type: 'audio',
              asset_id: 'audio:podcast-job',
              title: 'Generated podcast audio',
              data_url: GENERATED_AUDIO_DATA_URL,
              duration: 2,
              mime_type: 'audio/wav',
            },
          ],
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        });
      }

      if (path === '/api/jobs') {
        return Response.json({ jobs: [] });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPodcast();

    expect(await screen.findByRole('heading', { name: 'Episode request' })).toBeInTheDocument();
    expect((await screen.findAllByText('Alex Voice')).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: '2. Participants and voice casting' })).toBeInTheDocument();
    expect(screen.getByText('Voice')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Topic / Episode title'), { target: { value: 'Signals' } });
    fireEvent.change(screen.getByLabelText(/Episode brief/), { target: { value: 'Discuss local AI workstation design.' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));

    expect((await screen.findAllByText('Podcast audio ready: job:podcast')).length).toBeGreaterThan(0);
    expect(await screen.findByText('Generated podcast audio')).toBeInTheDocument();
    expect(screen.getByLabelText('Podcast audio player').querySelector('audio')?.getAttribute('src')).toBe(GENERATED_AUDIO_DATA_URL);

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"podcast"');
      expect(createCall?.[1]?.body).toContain('"type":"tts.multi_speaker_synthesize"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:tts"');
      expect(createCall?.[1]?.body).toContain('"script_segments"');
      expect(createCall?.[1]?.body).toContain('"character_voice_assignments"');
      expect(createCall?.[1]?.body).toContain('"voice_id":"resources/voice_clones/alex.wav"');
      expect(createCall?.[1]?.body).toContain('"speakerInstructions"');
    });
  });
});
