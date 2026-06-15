import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { StorytellerWorkspace } from './StorytellerWorkspace';

function renderStoryteller() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'storyteller');

  if (!module) {
    throw new Error('Storyteller module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <StorytellerWorkspace module={module} />
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

describe('StorytellerWorkspace', () => {
  it('queues story jobs through the shared jobs API', async () => {
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
              capabilities: ['chat', 'completion'],
            },
          ],
          models: [],
        });
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json({
          id: 'job:story',
          module: 'storyteller',
          type: 'story.generate',
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
              id: 'asset:story',
              module: 'storyteller',
              type: 'story',
              mime_type: 'text/markdown',
              storage_path: 'artifacts/story.md',
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderStoryteller();

    expect(await screen.findByRole('heading', { name: 'Story request' })).toBeInTheDocument();
    expect(await screen.findByText('LM Studio')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'story / storyteller' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'lmstudio' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'The Glass Orchard' } });
    fireEvent.change(screen.getByLabelText('Premise'), { target: { value: 'A city grows fruit made of memory.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue story' }));

    expect(await screen.findByText('Story job queued: job:story')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      expect(createCall?.[1]?.body).toContain('"module":"storyteller"');
      expect(createCall?.[1]?.body).toContain('"type":"story.generate"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:llm"');
      expect(createCall?.[1]?.body).toContain('"prompt_template_id":"storyteller.draft.v1"');
    });
  });
});
