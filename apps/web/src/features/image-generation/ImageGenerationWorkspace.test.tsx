import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { JobListResponse } from '../../api/client';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { hasActiveImageJobs, ImageGenerationWorkspace, isImageJobEventPayload } from './ImageGenerationWorkspace';

function renderImageGeneration() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'image-generation');

  if (!module) {
    throw new Error('Image Generation module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <ImageGenerationWorkspace module={module} />
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

describe('ImageGenerationWorkspace', () => {
  it('queues image jobs and reads bounded workspace projections', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json({
          providers: [
            {
              id: 'image:flux',
              label: 'Flux local',
              family: 'image',
              source: 'settings',
              status: 'configured',
              capabilities: ['image'],
            },
            {
              id: 'rpg_visual:flux',
              label: 'RPG visual provider',
              family: 'rpg_visual',
              source: 'settings',
              status: 'configured',
              capabilities: ['image'],
            },
          ],
          models: [],
        });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json({
          id: 'job:image',
          module: 'image-generation',
          type: 'image.generate',
          status: 'queued',
          resource_class: 'gpu:image',
          created_at: '2026-06-14T00:00:01Z',
          updated_at: '2026-06-14T00:00:01Z',
          priority: 0,
        });
      }

      if (path === '/api/image-generation/jobs') {
        return Response.json({ jobs: [] });
      }

      if (path === '/api/image-generation/assets') {
        return Response.json({
          assets: [
            {
              id: 'asset:image',
              module: 'image-generation',
              type: 'image',
              mime_type: 'image/png',
              storage_path: 'artifacts/image.png',
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderImageGeneration();

    expect(await screen.findByRole('heading', { name: 'Image request' })).toBeInTheDocument();
    expect(await screen.findByText('Flux local')).toBeInTheDocument();
    expect(screen.queryByText('RPG visual provider')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Select Generated image' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'image:flux' } });
    fireEvent.change(screen.getByLabelText('Prompt'), { target: { value: 'A bright workstation render.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue image' }));

    expect(await screen.findByText('Image job queued: job:image')).toBeInTheDocument();

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => requestPath(input as RequestInfo | URL));
      expect(paths).toContain('/api/image-generation/jobs');
      expect(paths).toContain('/api/image-generation/assets');
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"image-generation"');
      expect(createCall?.[1]?.body).toContain('"type":"image.generate"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:image"');
      expect(createCall?.[1]?.body).toContain('"provider_id":"image:flux"');
    });
  });
});

describe('image job synchronization helpers', () => {
  it('recognizes image events and rejects unrelated events', () => {
    expect(isImageJobEventPayload({ payload: { type: 'image.generate', module: 'image-generation' } })).toBe(true);
    expect(isImageJobEventPayload({ payload: { type: 'tts.synthesize', module: 'voice' } })).toBe(false);
    expect(isImageJobEventPayload({ payload: null })).toBe(false);
  });

  it('polls only while an image job is active', () => {
    const active = { jobs: [{ status: 'running' }] } as JobListResponse;
    const completed = { jobs: [{ status: 'completed' }] } as JobListResponse;

    expect(hasActiveImageJobs(active)).toBe(true);
    expect(hasActiveImageJobs(completed)).toBe(false);
    expect(hasActiveImageJobs(undefined)).toBe(false);
  });
});
