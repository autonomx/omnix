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
      action: 'draft',
      ...(typeof overrides.input_payload === 'object' && overrides.input_payload ? (overrides.input_payload as Record<string, unknown>) : {}),
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
    expect((await screen.findAllByText('The orchard rang like crystal at sunset.')).length).toBeGreaterThan(0);

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      const body = JSON.parse(String(createCall?.[1]?.body ?? '{}')) as { input_payload?: Record<string, unknown>; module?: string; type?: string; resource_class?: string };
      expect(body.module).toBe('storyteller');
      expect(body.type).toBe('story.generate');
      expect(body.resource_class).toBe('gpu:llm');
      expect(body.input_payload?.prompt_template_id).toBe('storyteller.draft.v1');
      expect(body.input_payload?.action).toBe('draft');
      expect(body.input_payload?.source_text).toBeNull();
      expect(body.input_payload?.source_job_id).toBeNull();
      expect(body.input_payload?.tone).toBe('Cozy');
      expect(body.input_payload?.writing_style).toBe('Lyrical & Descriptive');
    });

    expect(screen.getAllByText('story.generate').length).toBeGreaterThan(0);
  });

  it('selects prior story versions into the manuscript', async () => {
    const newer = storyJob({
      id: 'job:newer',
      input_payload: { title: 'Newer Orchard', action: 'expand' },
      output_refs: [{ kind: 'text', content: 'Newer branches glittered over the city.' }],
    });
    const older = storyJob({
      id: 'job:older',
      input_payload: { title: 'Older Orchard', action: 'rewrite' },
      output_refs: [{ kind: 'text', content: 'Older roots remembered every footstep.' }],
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = requestPath(input);

        if (path === '/api/providers') {
          return Response.json(providerPayload());
        }

        if (path === '/api/jobs') {
          return Response.json({ jobs: [newer, older] });
        }

        if (path === '/api/assets') {
          return Response.json(assetPayload());
        }

        return new Response('not found', { status: 404 });
      }),
    );

    renderStoryteller();

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(within(manuscript).getByText('Newer branches glittered over the city.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Select v1: Rewrite paragraph • Older Orchard/ }));

    expect(within(manuscript).getByText('Older roots remembered every footstep.')).toBeInTheDocument();
  });

  it('submits quick actions with active manuscript context', async () => {
    const baseText = 'The orchard rang like crystal at sunset.\n\nEach branch remembered a name.';
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json(
          storyJob({
            id: 'job:continue',
            input_payload: { title: 'The Glass Orchard', action: 'continue' },
            output_refs: [{ kind: 'text', content: 'The path continued beneath the glass leaves.' }],
          }),
        );
      }

      if (path === '/api/jobs') {
        return Response.json({
          jobs: [
            storyJob({
              id: 'job:base',
              output_refs: [{ kind: 'text', content: baseText }],
            }),
          ],
        });
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderStoryteller();

    expect(await screen.findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Premise/), { target: { value: 'A city grows fruit made of memory.' } });
    fireEvent.click(screen.getByRole('button', { name: /Continue Story/ }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/jobs' && init?.method === 'POST',
      );
      const body = JSON.parse(String(createCall?.[1]?.body ?? '{}')) as { input_payload?: Record<string, unknown> };
      expect(body.input_payload?.action).toBe('continue');
      expect(body.input_payload?.prompt_template_id).toBe('storyteller.continue.v1');
      expect(body.input_payload?.source_text).toBe(baseText);
      expect(body.input_payload?.source_job_id).toBe('job:base');
    });
  });
});
