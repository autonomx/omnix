import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

function providerPayload() {
  return {
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
  };
}

function storyJob(overrides: Record<string, unknown> = {}) {
  return {
    id: 'job:story',
    module: 'storyteller',
    type: 'story.generate',
    status: 'completed',
    resource_class: 'gpu:llm',
    created_at: '2026-06-14T00:00:01Z',
    updated_at: '2026-06-14T00:00:02Z',
    priority: 0,
    progress: { current: 3, total: 3 },
    input_payload: {
      title: 'The Glass Orchard',
      premise: 'A city grows fruit made of memory.',
      provider_id: 'lmstudio',
    },
    output_refs: [
      {
        kind: 'text',
        content:
          'The orchard rang like crystal at sunset.\n\nEach branch held a memory bright enough to bruise the dark, and Mira knew the city would wake hungry for forgotten names.',
      },
    ],
    ...overrides,
  };
}

function assetPayload() {
  return {
    assets: [
      {
        id: 'asset:story',
        module: 'storyteller',
        type: 'story',
        mime_type: 'text/markdown',
        storage_path: 'artifacts/the-glass-orchard.md',
        created_at: '2026-06-14T00:00:00Z',
      },
    ],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('StorytellerWorkspace', () => {
  it('renders completed story output as the main manuscript workspace', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = requestPath(input);

        if (path === '/api/providers') {
          return Response.json(providerPayload());
        }

        if (path === '/api/jobs') {
          return Response.json({ jobs: [storyJob()] });
        }

        if (path === '/api/assets') {
          return Response.json(assetPayload());
        }

        return new Response('not found', { status: 404 });
      }),
    );

    renderStoryteller();

    expect(await screen.findByRole('complementary', { name: 'Story library' })).toBeInTheDocument();
    const manuscript = screen.getByRole('region', { name: 'Story manuscript' });
    expect(manuscript).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Story controls' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Story outline' })).toBeInTheDocument();
    expect((await screen.findAllByRole('heading', { name: 'The Glass Orchard' })).length).toBeGreaterThan(0);
    expect(within(manuscript).getByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    expect(within(manuscript).getByText(/Each branch held a memory/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Continue Story/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Rewrite Paragraph/ })).toBeInTheDocument();
  });

  it('shows an empty manuscript state before the first story is generated', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = requestPath(input);

        if (path === '/api/providers') {
          return Response.json(providerPayload());
        }

        if (path === '/api/jobs') {
          return Response.json({ jobs: [] });
        }

        if (path === '/api/assets') {
          return Response.json({ assets: [] });
        }

        return new Response('not found', { status: 404 });
      }),
    );

    renderStoryteller();

    expect(await screen.findByText('Start with a premise, choose a tone, then generate the first scene. Completed output will appear here as a manuscript instead of a job-card preview.')).toBeInTheDocument();
  });

  it('generates stories through the shared jobs API from the redesigned controls', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json(storyJob());
      }

      if (path === '/api/jobs') {
        return Response.json({ jobs: [] });
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderStoryteller();

    expect(await screen.findByText('LM Studio')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'lmstudio' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'The Glass Orchard' } });
    fireEvent.change(screen.getByLabelText(/Premise/), { target: { value: 'A city grows fruit made of memory.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Generate story' }));

    expect(await screen.findByText('Story generated: job:story')).toBeInTheDocument();
    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      const body = String(createCall?.[1]?.body ?? '');
      expect(body).toContain('"module":"storyteller"');
      expect(body).toContain('"type":"story.generate"');
      expect(body).toContain('"resource_class":"gpu:llm"');
      expect(body).toContain('"prompt_template_id":"storyteller.draft.v1"');
      expect(body).toContain('"tone":"Cozy"');
      expect(body).toContain('"writing_style":"Lyrical & Descriptive"');
    });

    expect(screen.getAllByText('story.generate').length).toBeGreaterThan(0);
  });
});
