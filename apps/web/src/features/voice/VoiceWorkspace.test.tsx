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
  it('loads central defaults, resets local edits, and queues TTS through the shared jobs API', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/settings') {
        return Response.json({
          success: true,
          provider: 'lmstudio',
          audio_provider_tts: 'faster-qwen3-tts',
          audio_provider_stt: 'parakeet',
          settings: {
            settings_control_center: {
              revision: 'voice-studio-r1',
              global: { providers: { tts: 'faster-qwen3-tts', voiceCloning: 'qwen-voice' } },
              voice: {
                language: 'English',
                stability: 0.61,
                similarity: 0.72,
                style: 0.22,
                speed: 1.25,
                pitch: 1,
                volume: -2,
                effects: ['Compression'],
                cloningLanguage: 'French',
                cloningQuality: 'Standard',
              },
            },
          },
        });
      }

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
            {
              id: 'qwen-voice',
              label: 'Qwen Voice',
              family: 'tts',
              source: 'settings',
              status: 'configured',
              capabilities: ['voice_cloning'],
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
    expect(screen.getAllByText('Dave').length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(screen.getByLabelText('Output speed')).toHaveValue('1.25');
      expect(screen.getByLabelText('Language / Accent')).toHaveValue('French');
      expect(screen.getByLabelText('Quality')).toHaveValue('Standard');
      expect(screen.getByRole('button', { name: 'Compression' })).toHaveClass('active');
      expect(screen.getByRole('button', { name: 'Equalizer' })).not.toHaveClass('active');
    });

    fireEvent.change(screen.getByLabelText('Output speed'), { target: { value: '1.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reset tuning' }));
    expect(screen.getByLabelText('Output speed')).toHaveValue('1.25');

    fireEvent.click(screen.getByRole('button', { name: 'Equalizer' }));
    expect(screen.getByRole('button', { name: 'Equalizer' })).toHaveClass('active');
    fireEvent.click(screen.getByRole('button', { name: 'Reset effects' }));
    expect(screen.getByRole('button', { name: 'Compression' })).toHaveClass('active');
    expect(screen.getByRole('button', { name: 'Equalizer' })).not.toHaveClass('active');

    fireEvent.change(screen.getByLabelText('Language / Accent'), { target: { value: 'Spanish' } });
    fireEvent.change(screen.getByLabelText('Quality'), { target: { value: 'Draft' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reset defaults' }));
    expect(screen.getByLabelText('Language / Accent')).toHaveValue('French');
    expect(screen.getByLabelText('Quality')).toHaveValue('Standard');

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
      expect(createCall?.[1]?.body).toContain('"language":"English"');
      expect(createCall?.[1]?.body).toContain('"speed":1.25');
      expect(createCall?.[1]?.body).toContain('"audio_effects":["Compression"]');
      expect(createCall?.[1]?.body).toContain('"character_voice_assignments"');
    });
  });
});
