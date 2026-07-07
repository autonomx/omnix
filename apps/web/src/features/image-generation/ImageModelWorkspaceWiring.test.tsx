import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { ImageGenerationWorkspace } from './ImageGenerationWorkspace';

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

function renderWorkspace() {
  const module = omnixModules.find((entry) => entry.id === 'image-generation');
  if (!module) throw new Error('Image Generation module is missing');
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <ImageGenerationWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('Image Generation model residency wiring', () => {
  it('loads, warms, and unloads FLUX through the gateway while gating generation', async () => {
    let loaded = false;
    let warmedUp = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/providers') {
        return Response.json({
          providers: [{ id: 'image:flux_klein', label: 'FLUX.2 [klein] 4B', family: 'image', source: 'settings', status: 'configured', capabilities: ['image'] }],
          models: [],
        });
      }
      if (path === '/api/settings') return Response.json({ success: true, provider: '', audio_provider_tts: '', audio_provider_stt: '', settings: {} });
      if (path === '/api/workers/health') {
        return Response.json({
          ok: true,
          status: 'ready',
          workers: [{ id: 'image', ok: true, status: 'ready', capabilities: ['image'], mocked: false }],
        });
      }
      if (path === '/api/image-generation/model/status') {
        return Response.json({
          ok: true,
          service: 'image',
          enabled: true,
          provider: 'flux_klein',
          model: 'FLUX.2 [klein] 4B',
          loaded,
          state: loaded ? 'loaded' : 'unloaded',
          warmed_up: warmedUp,
          warmup_state: warmedUp ? 'completed' : 'not_started',
          explicit_load_required: true,
          local_model: { ok: true, exists: true, complete: true, missing: [], local_dir: 'resources/models/image/flux2-klein-4b' },
        });
      }
      if (path === '/api/image-generation/model/load' && init?.method === 'POST') {
        loaded = true;
        warmedUp = true;
        return Response.json({
          ok: true,
          provider: 'flux_klein',
          loaded: true,
          warmup: { ok: true, warmed_up: true, state: 'completed' },
        });
      }
      if (path === '/api/image-generation/model/unload' && init?.method === 'POST') {
        loaded = false;
        warmedUp = false;
        return Response.json({ ok: true, provider: 'flux_klein', loaded: false, unloaded: true });
      }
      if (path === '/api/image-generation/jobs') return Response.json({ jobs: [] });
      if (path === '/api/image-generation/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();

    const loadButton = await screen.findByRole('button', { name: 'Load & Warm Model' });
    await waitFor(() => expect(loadButton).toBeEnabled());
    const generateButton = screen.getByRole('button', { name: 'Generate image' });
    expect(generateButton).toBeDisabled();
    expect(generateButton).toHaveAttribute('title', 'Load and warm FLUX.2 [klein] 4B before generating an image.');

    fireEvent.click(loadButton);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Unload Model' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Generate image' })).not.toBeDisabled();
    expect(screen.getByText(/resident and warmed/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) => requestPath(input as RequestInfo | URL) === '/api/image-generation/model/load' && init?.method === 'POST')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Unload Model' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Load & Warm Model' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Generate image' })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input, init]) => requestPath(input as RequestInfo | URL) === '/api/image-generation/model/unload' && init?.method === 'POST')).toBe(true);
  });
});
