import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules, type OmnixModuleId } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { PlatformModuleWorkspace } from './PlatformModuleWorkspace';

class MockEventSource {
  readonly url: string;

  constructor(url: string | URL) {
    this.url = String(url);
  }

  addEventListener() {}

  removeEventListener() {}

  close() {}
}

function renderPlatform(moduleId: OmnixModuleId) {
  vi.stubGlobal('EventSource', MockEventSource);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === moduleId);

  if (!module) {
    throw new Error(`Unknown module ${moduleId}`);
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <PlatformModuleWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function mockGateway(payloads: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
    const payload = payloads[path];

    if (payload === undefined) {
      return new Response('not found', { status: 404 });
    }

    return Response.json(payload);
  });

  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('PlatformModuleWorkspace', () => {
  it('renders provider and model registry data from the generated API surface', async () => {
    mockGateway({
      '/api/providers': {
        providers: [
          {
            id: 'openai',
            label: 'OpenAI compatible',
            family: 'llm',
            source: 'settings',
            status: 'configured',
            capabilities: ['chat', 'model_discovery'],
            metadata: { latency_ms: 42 },
          },
        ],
        models: [],
      },
      '/api/models': {
        providers: [],
        models: [
          {
            id: 'local-mistral',
            label: 'Local Mistral',
            provider_id: 'local',
            location: 'local',
            capabilities: ['chat'],
            vram_hint_mb: 8192,
            metadata: { default_for: 'chat' },
          },
        ],
      },
    });

    renderPlatform('providers');
    expect(await screen.findByRole('heading', { name: 'OpenAI compatible' })).toBeInTheDocument();
    expect(screen.getByText('configured')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();

    renderPlatform('models');
    expect(await screen.findByRole('heading', { name: 'Local Mistral' })).toBeInTheDocument();
    expect(screen.getByText('8192 MB')).toBeInTheDocument();
  });

  it('renders jobs with progress and cancellation through the shared queue API', async () => {
    const fetchMock = mockGateway({
      '/api/jobs': {
        jobs: [
          {
            id: 'job-1',
            type: 'tts.generate',
            module: 'voice',
            status: 'running',
            resource_class: 'gpu:tts',
            created_at: '2026-06-14T00:00:00Z',
            updated_at: '2026-06-14T00:00:01Z',
            priority: 0,
            progress: { current: 1, total: 4, message: 'Synthesizing' },
            stages: [{ id: 's1', label: 'Synthesis', status: 'running', resource_class: 'gpu:tts' }],
            logs: [{ level: 'info', message: 'started' }],
          },
        ],
      },
      '/api/jobs/job-1/cancel': {
        id: 'job-1',
        type: 'tts.generate',
        module: 'voice',
        status: 'cancel_requested',
        resource_class: 'gpu:tts',
        created_at: '2026-06-14T00:00:00Z',
        updated_at: '2026-06-14T00:00:02Z',
        priority: 0,
      },
    });

    renderPlatform('jobs');

    expect(await screen.findByRole('heading', { name: 'tts.generate' })).toBeInTheDocument();
    expect(screen.getByText('Synthesizing')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/jobs/job-1/cancel', expect.objectContaining({ method: 'POST' }));
    });
  });

  it('renders assets, reports, settings, and diagnostics data', async () => {
    mockGateway({
      '/api/assets': {
        assets: [
          {
            id: 'asset-1',
            module: 'image-generation',
            type: 'image',
            mime_type: 'image/png',
            storage_path: 'artifacts/image.png',
            created_at: '2026-06-14T00:00:00Z',
            source_job_id: 'job-1',
          },
        ],
      },
      '/api/reports': {
        reports: [{ id: 'autoplay-report', kind: 'rpg_autoplay', path: 'reports/run.json', size_bytes: 512 }],
      },
      '/api/settings': {
        provider: 'openai',
        audio_provider_tts: 'piper',
        audio_provider_stt: 'whisper',
        image_enabled: true,
        rpg_visual_enabled: false,
        worker_urls: { llm: 'http://127.0.0.1:9001' },
      },
      '/api/diagnostics': {
        ok: true,
        status: 'ready',
        event_stream: { status: 'ready' },
        workers: {
          contract_version: 'omnix_worker_health_contract_v1',
          format_version: 'omnix_gateway_foundation_v1',
          ok: true,
          status: 'ready',
          workers: [{ id: 'llm', ok: true, mocked: true, source_env: 'OMNIX_LLM_WORKER_URL', status: 'mocked', url: '' }],
        },
        logs: [{ level: 'info', message: 'ready' }],
      },
    });

    renderPlatform('assets');
    expect(await screen.findByRole('heading', { name: 'image / image-generation' })).toBeInTheDocument();

    renderPlatform('reports');
    expect(await screen.findByRole('heading', { name: 'autoplay-report' })).toBeInTheDocument();

    renderPlatform('settings');
    expect(await screen.findByText('openai')).toBeInTheDocument();
    expect(screen.getByLabelText('Image generation')).toBeChecked();

    renderPlatform('diagnostics');
    expect(await screen.findByRole('heading', { name: 'Gateway status' })).toBeInTheDocument();
    expect(screen.getByText('mocked')).toBeInTheDocument();
  });

  it('renders core empty states when platform APIs return empty collections', async () => {
    mockGateway({
      '/api/providers': { providers: [], models: [] },
    });

    renderPlatform('providers');

    expect(await screen.findByText('No providers returned by gateway.')).toBeInTheDocument();
  });
});
