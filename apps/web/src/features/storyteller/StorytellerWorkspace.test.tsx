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
      ...(typeof overrides.input_payload === 'object' && overrides.input_payload
        ? (overrides.input_payload as Record<string, unknown>)
        : {}),
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

function assetPayload(extraAssets: unknown[] = []) {
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
      ...extraAssets,
    ],
  };
}

function savedAssetResponse() {
  const asset = {
    id: 'story:saved-orchard:abc123',
    module: 'storyteller',
    type: 'story',
    mime_type: 'text/markdown',
    storage_path: 'resources/data/assets/stories/saved-orchard.md',
    created_at: '2026-06-14T00:00:03Z',
  };
  return { asset, content: 'Saved roots remembered every footstep.' };
}

function assetContentPayload() {
  return {
    asset: assetPayload().assets[0],
    content: '# The Glass Orchard\n\nAsset branches chimed softly when Mira opened the gate.',
    encoding: 'utf-8',
    size_bytes: 68,
    truncated: false,
  };
}

function stubStoryApi(jobs: unknown[] = [storyJob()]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }
      if (path === '/api/jobs') {
        return Response.json({ jobs });
      }
      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }
      if (path === '/api/assets/asset%3Astory/content') {
        return Response.json(assetContentPayload());
      }
      return new Response('not found', { status: 404 });
    }),
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('StorytellerWorkspace', () => {
  it('renders completed story output as the main manuscript workspace', async () => {
    stubStoryApi([storyJob()]);

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
    stubStoryApi([]);

    renderStoryteller();

    expect(await screen.findByText('Start with a premise, choose a tone, then generate the first scene. Completed output will appear here as a manuscript instead of a job-card preview.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save story' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export Markdown' })).toBeDisabled();
  });

  it('generates stories through the shared jobs API from the redesigned controls', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/providers') return Response.json(providerPayload());
      if (path === '/api/jobs' && init?.method === 'POST') return Response.json(storyJob());
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json(assetPayload());
      if (path === '/api/assets/asset%3Astory/content') return Response.json(assetContentPayload());
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
      const body = JSON.parse(String(createCall?.[1]?.body ?? '{}')) as {
        input_payload?: Record<string, unknown>;
        module?: string;
        type?: string;
        resource_class?: string;
      };
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
    stubStoryApi([newer, older]);

    renderStoryteller();

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('Newer branches glittered over the city.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Older Orchard 5 words/ }));
    expect(await within(manuscript).findByText('Older roots remembered every footstep.')).toBeInTheDocument();
  });

  it('loads a saved local draft from the Story library', async () => {
    window.localStorage.setItem(
      'omnix:storyteller:last-draft',
      JSON.stringify({
        title: 'Local Draft Orchard',
        premise: 'A local draft waits in storage.',
        sourceJobId: 'job:draft-source',
        content: 'Local draft roots hummed beneath the glass soil.',
      }),
    );
    stubStoryApi([storyJob()]);

    renderStoryteller();

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Local Draft Orchard/ }));
    expect(await within(manuscript).findByText('Local draft roots hummed beneath the glass soil.')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { name: 'Local Draft Orchard' }).length).toBeGreaterThan(0);
  });

  it('loads readable story asset content from the Story library', async () => {
    stubStoryApi([]);

    renderStoryteller();

    const library = await screen.findByRole('complementary', { name: 'Story library' });
    const assetButton = await within(library).findByRole('button', { name: /the glass orchard/ });
    fireEvent.click(assetButton);

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('Asset branches chimed softly when Mira opened the gate.')).toBeInTheDocument();
    expect((await screen.findAllByRole('heading', { name: /the glass orchard/i })).length).toBeGreaterThan(0);
  });

  it('saves the selected story version as a shared asset', async () => {
    const selected = storyJob({
      id: 'job:selected',
      input_payload: { title: 'Saved Orchard', action: 'rewrite' },
      output_refs: [{ kind: 'text', content: 'Saved roots remembered every footstep.' }],
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/providers') return Response.json(providerPayload());
      if (path === '/api/jobs') return Response.json({ jobs: [selected] });
      if (path === '/api/assets' && init?.method !== 'POST') return Response.json(assetPayload());
      if (path === '/api/assets/story' && init?.method === 'POST') return Response.json(savedAssetResponse());
      if (path === '/api/assets/asset%3Astory/content') return Response.json(assetContentPayload());
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderStoryteller();

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('Saved roots remembered every footstep.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save story' }));

    expect(await screen.findByText('Saved “Saved Orchard” as a shared story asset.')).toBeInTheDocument();
    const saveCall = fetchMock.mock.calls.find(
      ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/assets/story' && init?.method === 'POST',
    );
    const body = JSON.parse(String(saveCall?.[1]?.body ?? '{}')) as Record<string, unknown>;
    expect(body.title).toBe('Saved Orchard');
    expect(body.content).toBe('Saved roots remembered every footstep.');
    expect(body.source_job_id).toBe('job:selected');
    const saved = JSON.parse(window.localStorage.getItem('omnix:storyteller:last-draft') ?? '{}') as Record<string, unknown>;
    expect(saved.title).toBe('Saved Orchard');
  });

  it('falls back to local browser storage when backend save fails', async () => {
    const selected = storyJob({
      id: 'job:selected',
      input_payload: { title: 'Saved Orchard', action: 'rewrite' },
      output_refs: [{ kind: 'text', content: 'Saved roots remembered every footstep.' }],
    });
    stubStoryApi([selected]);

    renderStoryteller();

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('Saved roots remembered every footstep.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save story' }));

    expect(await screen.findByText('Saved “Saved Orchard” locally.')).toBeInTheDocument();
    const saved = JSON.parse(window.localStorage.getItem('omnix:storyteller:last-draft') ?? '{}') as Record<string, unknown>;
    expect(saved.title).toBe('Saved Orchard');
    expect(saved.sourceJobId).toBe('job:selected');
    expect(saved.content).toBe('Saved roots remembered every footstep.');
  });

  it('exports the selected story version as Markdown', async () => {
    const createObjectUrl = vi.fn(() => 'blob:story-export');
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const selected = storyJob({
      id: 'job:exported',
      input_payload: { title: 'Exported Orchard', action: 'expand' },
      output_refs: [{ kind: 'text', content: 'Exported branches glittered over the city.' }],
    });
    stubStoryApi([selected]);

    renderStoryteller();

    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('Exported branches glittered over the city.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Export Markdown' }));

    expect(await screen.findByText('Exported exported-orchard.md.')).toBeInTheDocument();
    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:story-export');
  });

  it('derives outline entries from generated chapter and scene headings', async () => {
    const chapteredStory = [
      'Chapter 1: The Glass Orchard',
      'Scene 1: The Crystal Row',
      'The orchard rang like crystal at sunset.',
      'Chapter 2: The Memory Market',
      'Scene 1: The Name Seller',
      'Mira traded a silver thread for a forgotten lullaby.',
    ].join('\n\n');
    stubStoryApi([storyJob({ output_refs: [{ kind: 'text', content: chapteredStory }] })]);

    renderStoryteller();

    const outline = await screen.findByRole('complementary', { name: 'Story outline' });
    expect(await within(outline).findByRole('button', { name: /Chapter 1 The Glass Orchard/ })).toBeInTheDocument();
    expect(within(outline).getByRole('button', { name: /Scene 1 The Crystal Row/ })).toBeInTheDocument();
    const chapterTwoButton = await within(outline).findByRole('button', { name: /Chapter 2 The Memory Market/ });
    expect(chapterTwoButton).toBeInTheDocument();

    fireEvent.click(chapterTwoButton);

    const manuscript = screen.getByRole('region', { name: 'Story manuscript' });
    expect((await within(manuscript).findAllByRole('heading', { name: 'The Memory Market' })).length).toBeGreaterThan(0);
  });

  it('submits quick actions with active manuscript context', async () => {
    const baseText = 'The orchard rang like crystal at sunset.\n\nEach branch remembered a name.';
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/providers') return Response.json(providerPayload());
      if (path === '/api/jobs' && init?.method === 'POST') {
        return Response.json(storyJob({
          id: 'job:continue',
          input_payload: { title: 'The Glass Orchard', action: 'continue' },
          output_refs: [{ kind: 'text', content: 'The path continued beneath the glass leaves.' }],
        }));
      }
      if (path === '/api/jobs') {
        return Response.json({ jobs: [storyJob({ id: 'job:base', output_refs: [{ kind: 'text', content: baseText }] })] });
      }
      if (path === '/api/assets') return Response.json(assetPayload());
      if (path === '/api/assets/asset%3Astory/content') return Response.json(assetContentPayload());
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
