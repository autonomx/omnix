import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { AudiobookWorkspace } from './AudiobookWorkspace';

const project = {
  id: 'book-one', title: 'The Book', author: 'The Author', language: 'en',
  state: 'review_required', current_source_revision_id: 'source-one',
};

function renderWorkspace() {
  const module = omnixModules.find((entry) => entry.id === 'audiobook');
  if (!module) throw new Error('audiobook module missing');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AudiobookWorkspace module={module} /></QueryClientProvider>);
}

describe('AudiobookWorkspace', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('loads projects beyond the first library page', async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => ({
      ...project, id: `book-${index + 1}`, title: `Project ${index + 1}`,
    }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: firstPage };
      else if (url.endsWith('/projects?offset=100')) body = { projects: [{ ...project, id: 'book-101', title: 'Project 101' }] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();

    expect(await screen.findByRole('button', { name: /Project 101/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/audiobook/projects?offset=100', expect.anything());
  });

  it('opens the new-project form from the library rail', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, chapters: [], review_issues: [], speakers: [], render_jobs: [],
        preview_jobs: [], export_jobs: [], render_progress: { completed: 0, total: 0 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Start new project' }));
    expect(await screen.findByRole('heading', { name: 'Create a New Audiobook Project' })).toBeInTheDocument();
    expect(screen.getByLabelText('Project title *')).toBeInTheDocument();
  });

  it('shows canonical chapter text and review state from the backend', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/projects/book-one/source/library') && init?.method === 'POST') {
        return new Response(JSON.stringify({ project_id: 'book-one', source_asset_id: 'asset-one', job_id: 'job-one' }),
          { status: 202, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS', model_revision: 'sha256:test-model' };
      else if (url.endsWith('/source-library')) body = { directory: 'resources\\data\\audiobooks', files: [{ name: 'joy.pdf', source_format: 'pdf', size_bytes: 123 }] };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 36 }],
        review_issues: [{ id: 'issue-one', reason: 'speaker uncertain',
          source_text: '"Hello," she said.', chapter_id: 'chapter-one',
          chapter_title: 'Opening', speaker_id: null }],
        speakers: [], render_jobs: [], export_jobs: [],
        pipeline_jobs: [
          { id: 'ingest-new', type: 'audiobook.ingest', status: 'completed', progress: {}, error: null, attempts: 1, max_attempts: 3, can_retry: false },
          { id: 'ingest-old', type: 'audiobook.ingest', status: 'failed', progress: {}, error: { code: 'ingest_failed', message: 'old failure', retryable: true }, attempts: 3, max_attempts: 3, can_retry: true },
        ],
        render_progress: { completed: 0, total: 1 },
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-one')) body = {
        id: 'chapter-one', ordinal: 0, title: 'Opening',
        canonical_text: 'The exact book text.\n\nIt stays here.',
        spans: [{ id: 'span-one', source_text: 'The exact book text.\n\nIt stays here.', structural_kind: 'narration',
          annotation: null, speech_plan: { tts_input_text: 'The exact book text.\n\nIt stays here.', hash: 'plan', transformations: [] } }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    const firstVisit = renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect(await screen.findByLabelText('Canonical chapter text')).toHaveTextContent('The exact book text.');
    expect(screen.queryByText(/ingest failed/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit project' }));
    expect(screen.getByLabelText('Upload from computer')).toHaveAttribute(
      'accept', '.pdf,.epub,.docx,.html,.htm,.txt,.text,.md,.markdown',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Upload source' }));
    fireEvent.change(await screen.findByLabelText('Local audiobook source'), { target: { value: 'joy.pdf' } });
    fireEvent.change(screen.getByLabelText('Exclude PDF pages'), { target: { value: '1-3, 42-45' } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload selected source' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/source/library?filename=joy.pdf&exclude_pages=1-3%2C%2042-45',
      { method: 'POST' },
    ));
    expect(screen.getByText('"Hello," she said.')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Books/ }).at(-1)!);
    expect(screen.getByRole('heading', { name: 'Books & chapters' })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Characters/ }).at(-1)!);
    expect(screen.getByRole('heading', { name: 'Character-to-voice mapping' })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /Pronunciations/ }).at(-1)!);
    expect(screen.getAllByRole('heading', { name: 'Pronunciations' }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: /Chapters/ }).at(-1)!);
    fireEvent.click(screen.getByRole('button', { name: 'Outline and cast' }));
    expect(screen.getByRole('button', { name: 'Outline and cast' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('Chapter and cast inspector')).toHaveClass('mobile-open');
    fireEvent.click(screen.getByRole('button', { name: 'Close outline' }));
    expect(screen.getByRole('button', { name: 'Outline and cast' })).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(screen.getByRole('button', { name: /Production Render/ }));
    expect(screen.getByRole('button', { name: 'Render book' })).toBeDisabled();
    expect(screen.getAllByText('Not started').length).toBeGreaterThan(0);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/audiobook/projects/book-one', expect.anything()));
    firstVisit.unmount();
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect(await screen.findByLabelText('Canonical chapter text')).toHaveTextContent('The exact book text.');
  });


  it('changes reading mode and can override a skipped structural block', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/reading-policy') && init?.method === 'PATCH') {
        return new Response(JSON.stringify({ project_id: 'book-one', audiobook_mode: 'story_only' }),
          { status: 200, headers: { 'content-type': 'application/json' } });
      }
      if (url.endsWith('/projects/book-one/document-overrides') && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 'override-one', scope: 'BLOCK', scope_key: 'block-page', action: 'READ' }),
          { status: 200, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, audiobook_mode: 'standard',
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 24 }],
        review_issues: [], speakers: [], render_jobs: [], preview_jobs: [], export_jobs: [],
        render_progress: { completed: 0, total: 1 },
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-one')) body = {
        id: 'chapter-one', ordinal: 0, title: 'Opening', canonical_text: 'Page 1 of 3\nStory.',
        spans: [{ id: 'span-one', source_text: 'Page 1 of 3\nStory.', structural_kind: 'narration',
          annotation: null, speech_plan: { tts_input_text: 'Story.', hash: 'plan', transformations: [] } }],
        document_blocks: [{
          id: 'block-page', original_text: 'Page 1 of 3', effective_role: 'page_number',
          confidence: 0.995, render_action: 'SKIP', speaker_analysis_visibility: 'EXCLUDE',
          provenance: [{ source: 'pattern', signal: 'page_number', value: 'Page 1 of 3' }],
        }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Edit project' }));
    const mode = await screen.findByLabelText('Audiobook reading mode');
    expect(mode).toHaveValue('standard');
    fireEvent.change(mode, { target: { value: 'story_only' } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/reading-policy',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ mode: 'story_only' }) }),
    ));

    fireEvent.click(screen.getAllByRole('button', { name: /Chapters/ }).at(-1)!);
    expect(await screen.findByLabelText('Skipped audiobook content')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Read skipped block Page 1 of 3' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/document-overrides',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          scope: 'BLOCK', scope_key: 'block-page', action: 'READ', role_override: null,
        }),
      }),
    ));
  });

  it('shows detected speaker candidates and lets the operator confirm one', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/speakers') && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 'candidate-one', canonical_name: 'Time Traveller', status: 'active', promoted: true }),
          { status: 200, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, chapters: [],
        review_issues: [{ id: 'issue-one', reason: 'UNSUPPORTED_SPEAKER', source_text: '"Hello."',
          chapter_id: 'chapter-one', chapter_title: 'Opening', speaker_id: 'narrator',
          speaker_candidate: 'Time Traveller', structural_kind: 'dialogue', evidence: {} }],
        speakers: [
          { id: 'narrator', canonical_name: 'Narrator', kind: 'narrator', status: 'active', casting: null, aliases: [] },
          { id: 'candidate-one', canonical_name: 'Time Traveller', kind: 'character', status: 'proposed', occurrence_count: 3, casting: null, aliases: [] },
        ], render_jobs: [], preview_jobs: [], export_jobs: [], render_progress: { completed: 0, total: 0 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /Characters/ }).at(-1)!);
    expect(await screen.findByRole('heading', { name: 'Character-to-voice mapping' })).toBeInTheDocument();
    const confirmCandidate = await screen.findByRole('button', { name: /Confirm Time Traveller/ });
    expect(confirmCandidate).toBeInTheDocument();
    fireEvent.click(confirmCandidate);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/speakers',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ canonical_name: 'Time Traveller' }) }),
    ));
    expect(screen.getByText(/Human review required/)).toBeInTheDocument();
  });


  it('lets assigning a voice confirm a detected speaker directly', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/speakers/candidate-one/casting') && init?.method === 'POST') {
        return new Response(JSON.stringify({
          speaker_id: 'candidate-one', voice_profile_id: 'voice-one', revision: 1,
        }), { status: 200, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [{ id: 'voice-one', name: 'Voice One', language: 'en' }] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, chapters: [], review_issues: [],
        speakers: [
          { id: 'narrator', canonical_name: 'Narrator', kind: 'narrator', status: 'active', casting: null, aliases: [] },
          { id: 'candidate-one', canonical_name: 'Time Traveller', kind: 'character', status: 'proposed', occurrence_count: 3, casting: null, aliases: [] },
        ], render_jobs: [], preview_jobs: [], export_jobs: [], render_progress: { completed: 0, total: 0 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /Characters/ }).at(-1)!);

    const voiceSelect = await screen.findByLabelText('Main voice for Time Traveller');
    expect(voiceSelect).toBeEnabled();
    fireEvent.change(voiceSelect, { target: { value: 'voice-one' } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/speakers/candidate-one/casting',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ voice_profile_id: 'voice-one' }) }),
    ));
  });

  it('skips policy-muted front matter when choosing a sample preview', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/preview') && init?.method === 'POST') {
        return new Response(JSON.stringify({ job_id: 'preview-story', span_id: 'story-span' }),
          { status: 202, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = {
        provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS',
        model_revision: 'sha256:test-model',
      };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        state: 'ready_to_render',
        audiobook_mode: 'story_only',
        chapters: [
          { id: 'chapter-front', ordinal: 0, title: 'Contents', character_count: 10 },
          { id: 'chapter-story', ordinal: 1, title: 'Chapter One', character_count: 24 },
        ],
        review_issues: [], speakers: [], render_jobs: [], pipeline_jobs: [],
        preview_jobs: [], export_jobs: [], render_progress: { completed: 0, total: 0 },
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-front')) body = {
        id: 'chapter-front', ordinal: 0, title: 'Contents', canonical_text: '# Contents',
        spans: [{
          id: 'front-span', source_text: '# Contents', structural_kind: 'narration',
          annotation: null,
          speech_plan: { tts_input_text: '', hash: 'front-plan', transformations: [] },
        }],
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-story')) body = {
        id: 'chapter-story', ordinal: 1, title: 'Chapter One',
        canonical_text: 'Daniel opened the gate.',
        spans: [{
          id: 'story-span', source_text: 'Daniel opened the gate.', structural_kind: 'narration',
          annotation: null,
          speech_plan: {
            tts_input_text: 'Daniel opened the gate.', hash: 'story-plan', transformations: [],
          },
        }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect((await screen.findAllByText('# Contents')).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Preview' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Play sample' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/preview',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"span_id":"story-span"'),
      }),
    ));
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/preview',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"span_id":"front-span"'),
      }),
    );
  });

  it('queues a span preview and restores its audio from durable job state', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/preview') && init?.method === 'POST') {
        return new Response(JSON.stringify({ job_id: 'preview-one', span_id: 'span-one' }),
          { status: 202, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS', model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 7 }],
        review_issues: [], speakers: [], render_jobs: [], export_jobs: [],
        preview_jobs: [{ id: 'preview-one', span_id: 'span-one', status: 'completed' }],
        render_progress: { completed: 0, total: 1 },
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-one')) body = {
        id: 'chapter-one', ordinal: 0, title: 'Opening', canonical_text: 'A line.',
        spans: [{ id: 'span-one', source_text: 'A line.', structural_kind: 'narration',
          annotation: null, speech_plan: { tts_input_text: 'A line.', hash: 'plan', transformations: [] } }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    const preview = await screen.findByRole('button', { name: 'Preview' });
    await waitFor(() => expect(preview).toBeEnabled());
    expect(screen.getByLabelText('Preview A line.')).toHaveAttribute('src',
      '/api/audiobook/projects/book-one/previews/preview-one/audio');
    fireEvent.click(preview);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/preview',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"span_id":"span-one"') }),
    ));
  });

  it('renders fractional progress reported by an active chapter job', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        state: 'rendering',
        chapters: [
          { id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 7 },
          { id: 'chapter-two', ordinal: 1, title: 'Middle', character_count: 7 },
        ],
        review_issues: [], speakers: [], export_jobs: [], preview_jobs: [],
        render_jobs: [
          { id: 'render-one', chapter_id: 'chapter-one', status: 'completed', progress: { current: 1, total: 1 } },
          { id: 'render-two', chapter_id: 'chapter-two', status: 'running', progress: { current: 0.37, total: 1, unit_current: 760, unit_total: 2048 } },
        ],
        render_progress: { completed: 1, total: 2 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Production Render/ }));

    expect(await screen.findByText('37%')).toBeInTheDocument();
  });

  it('excludes policy-skipped source chapters from render progress', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        state: 'rendering',
        chapters: [
          { id: 'chapter-front-matter', ordinal: 0, title: 'Contents', character_count: 12 },
          { id: 'chapter-one', ordinal: 1, title: 'Chapter One', character_count: 20 },
        ],
        review_issues: [], speakers: [], export_jobs: [], preview_jobs: [], pipeline_jobs: [],
        render_jobs: [
          { id: 'render-one', chapter_id: 'chapter-one', status: 'running',
            progress: { current: 0.5, total: 1 } },
        ],
        render_progress: { completed: 0, total: 2 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Production Render/ }));

    expect((await screen.findAllByText('50%')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/0 \/ 1 audiobook chapters/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/1 skipped by policy/).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/Skipped/).some((node) =>
        node.textContent?.includes('by reading policy'),
      ),
    ).toBe(true);
    expect(screen.getAllByText('Skipped by policy').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Not applicable').length).toBeGreaterThan(0);
  });

  it('keeps pause and stop controls in the render queue', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS', model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one/render/pause') && init?.method === 'POST') body = { project_id: 'book-one', paused: 2 };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, state: 'rendering',
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 7 },
          { id: 'chapter-two', ordinal: 1, title: 'Middle', character_count: 7 }],
        review_issues: [], speakers: [], export_jobs: [], preview_jobs: [],
        render_jobs: [
          { id: 'render-one', chapter_id: 'chapter-one', status: 'running', progress: { current: 0, total: 1 } },
          { id: 'render-two', chapter_id: 'chapter-two', status: 'paused', progress: { current: 0, total: 1 } },
        ],
        render_progress: { completed: 0, total: 2 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Production Render/ }));

    expect(await screen.findByRole('button', { name: 'Pause all chapters' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Resume all chapters' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Stop all chapters' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Pause chapter' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Resume chapter' })).toBeEnabled();
    expect(screen.getAllByRole('button', { name: 'Stop chapter' })).toHaveLength(2);
    expect(document.querySelector('.audiobook-render-controls')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Pause all chapters' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/render/pause', expect.objectContaining({ method: 'POST' }),
    ));
  });

  it('saves a selected span interpretation without changing the displayed source', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/spans/span-one/annotation') && init?.method === 'POST') {
        return new Response(JSON.stringify({ span_id: 'span-one', revision: 2, changed: true }),
          { status: 200, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS', model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 7 }],
        review_issues: [], speakers: [{ id: 'speaker-one', canonical_name: 'Narrator', kind: 'narrator', casting: null, aliases: [] }],
        render_jobs: [], preview_jobs: [], export_jobs: [], render_progress: { completed: 0, total: 1 },
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-one')) body = {
        id: 'chapter-one', ordinal: 0, title: 'Opening', canonical_text: 'A line.',
        spans: [{ id: 'span-one', source_text: 'A line.', structural_kind: 'narration',
          annotation: { id: 'annotation-one', role: 'narration', speaker_id: 'speaker-one',
            speaker_candidate: null, delivery: '', review_status: 'accepted', evidence: {} },
          speech_plan: { tts_input_text: 'A line.', hash: 'plan', transformations: [] } }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect(await screen.findByLabelText('Canonical chapter text')).toHaveTextContent('A line.');
    fireEvent.change(screen.getByLabelText('Selected span delivery'), { target: { value: 'softly' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save interpretation' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/spans/span-one/annotation',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"delivery":"softly"') }),
    ));
    expect(screen.getByLabelText('Canonical chapter text')).toHaveTextContent('A line.');
  });

  it('offers a retry from persisted failed render state', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/render') && init?.method === 'POST') {
        return new Response(JSON.stringify({ render_run_id: 'second-run' }),
          { status: 202, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS', model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, state: 'rendering', chapters: [], review_issues: [], speakers: [],
        render_jobs: [{ id: 'failed-job', status: 'failed', progress: { generated: 1, cache_hits: 2 }, error: { message: 'GPU unavailable' } }],
        preview_jobs: [], export_jobs: [], render_progress: { completed: 3, total: 4 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: /Production Render/ }));
    const retry = await screen.findByRole('button', { name: 'Retry render' });
    await waitFor(() => expect(retry).toBeEnabled());
    expect(screen.getByText('Cache Hits').closest('article')).toHaveTextContent('2');
    fireEvent.click(retry);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/render',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('sha256:test-model') }),
    ));
  });

  it('locates a cast speaker in another chapter before auditioning', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/preview') && init?.method === 'POST') {
        return new Response(JSON.stringify({ job_id: 'preview-two' }), { status: 202,
          headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, chapters: [{ id: 'chapter-one', ordinal: 0, title: 'First' },
          { id: 'chapter-two', ordinal: 1, title: 'Second' }], review_issues: [],
        speakers: [{ id: 'speaker-two', canonical_name: 'Ada', kind: 'character', casting: null, aliases: [] }],
        render_jobs: [], preview_jobs: [], export_jobs: [], render_progress: { completed: 0, total: 2 },
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-one')) body = {
        id: 'chapter-one', ordinal: 0, title: 'First', canonical_text: 'Narration.',
        spans: [{ id: 'span-one', source_text: 'Narration.', structural_kind: 'narration', annotation: null,
          speech_plan: { tts_input_text: 'Narration.', hash: 'one', transformations: [] } }],
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-two')) body = {
        id: 'chapter-two', ordinal: 1, title: 'Second', canonical_text: 'Hello.',
        spans: [{ id: 'span-two', source_text: 'Hello.', structural_kind: 'dialogue',
          annotation: { id: 'annotation-two', role: 'dialogue', speaker_id: 'speaker-two',
            speaker_candidate: null, delivery: '', review_status: 'accepted', evidence: {} },
          speech_plan: { tts_input_text: 'Hello.', hash: 'two', transformations: [] } }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    const find = await screen.findByRole('button', { name: 'Find span for Ada' });
    fireEvent.click(find);
    expect(await screen.findByLabelText('Canonical chapter text')).toHaveTextContent('Hello.');
    const audition = screen.getByRole('button', { name: 'Audition voice for Ada' });
    await waitFor(() => expect(audition).toBeEnabled());
    fireEvent.click(audition);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/preview',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"span_id":"span-two"') }),
    ));
  });

  it('saves project metadata and retries an actionable failed pipeline stage', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one') && init?.method === 'PATCH') {
        return new Response(JSON.stringify({ ...project, title: 'Renamed Book' }), {
          status: 200, headers: { 'content-type': 'application/json' },
        });
      }
      if (url.endsWith('/projects/book-one/jobs/failed-analysis/retry') && init?.method === 'POST') {
        return new Response(JSON.stringify({
          job_id: 'retry-analysis', retry_of: 'failed-analysis', type: 'audiobook.analyze',
        }), { status: 202, headers: { 'content-type': 'application/json' } });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = {
        provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS',
        model_revision: 'sha256:test-model',
      };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, state: 'analyzing', chapters: [], review_issues: [], speakers: [],
        render_jobs: [], preview_jobs: [], export_jobs: [], pronunciations: [],
        pipeline_jobs: [{
          id: 'failed-analysis', type: 'audiobook.analyze', status: 'failed',
          attempts: 3, max_attempts: 3, can_retry: true,
          error: { code: 'analysis_failed', message: 'classifier unavailable', retryable: false },
          progress: {},
        }],
        render_progress: { completed: 0, total: 0 },
        word_count: 1200, estimated_runtime_seconds: 480, actual_runtime_seconds: 0,
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));

    expect(await screen.findByText(/1,200 words/)).toBeInTheDocument();
    expect(screen.getByText(/analysis failed/)).toBeInTheDocument();
    expect(screen.getByText(/attempt 3\/3/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Edit project' }));
    const title = screen.getByLabelText('Title');
    fireEvent.change(title, { target: { value: 'Renamed Book' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one',
      expect.objectContaining({
        method: 'PATCH',
        body: expect.stringContaining('Renamed Book'),
      }),
    ));

    fireEvent.click(screen.getByRole('button', { name: 'Retry stage' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/jobs/failed-analysis/retry',
      expect.objectContaining({ method: 'POST' }),
    ));
  });

  it('queues reclassification for the current manuscript before voice assignment', async () => {
    let reclassifyQueued = false;
    let reclassificationStatus = 'running';
    let cancelRequests = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/reclassify') && init?.method === 'POST') {
        reclassifyQueued = true;
        return new Response(JSON.stringify({ job_id: 'reclassify-one', source_revision_id: 'source-one' }), {
          status: 202, headers: { 'content-type': 'application/json' },
        });
      }
      if (url.endsWith('/jobs/reclassify-one/pause') && init?.method === 'POST') {
        reclassificationStatus = 'paused';
        return new Response(JSON.stringify({ job_id: 'reclassify-one', status: 'paused', paused: true }), { status: 200 });
      }
      if (url.endsWith('/jobs/reclassify-one/resume') && init?.method === 'POST') {
        reclassificationStatus = 'running';
        return new Response(JSON.stringify({ job_id: 'reclassify-one', status: 'running', resumed: true }), { status: 200 });
      }
      if (url.endsWith('/jobs/reclassify-one/cancel') && init?.method === 'POST') {
        cancelRequests += 1;
        reclassificationStatus = cancelRequests > 1 ? 'canceled' : 'cancel_requested';
        return new Response(JSON.stringify({ job_id: 'reclassify-one', cancellation_requested: true }), { status: 200 });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, chapters: [], review_issues: [], speakers: [], render_jobs: [],
        preview_jobs: [], export_jobs: [], pronunciations: [],
        render_progress: { completed: 0, total: 0 },
        pipeline_jobs: reclassifyQueued ? [{
          id: 'reclassify-one', type: 'audiobook.analyze', status: reclassificationStatus,
          progress: { current: 3, total: 17, message: 'analyzing chapters' },
          error: null, attempts: 1, max_attempts: 3, can_retry: false,
        }] : [],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Edit project' }));
    expect(screen.getByRole('button', { name: 'Reclassify text' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Reclassify text' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/reclassify', expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByLabelText('Text reclassification progress')).toHaveValue(18);
    expect(screen.getByText('3 / 17 spans · analyzing chapters')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reclassifying…' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/jobs/reclassify-one/pause', expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByRole('button', { name: 'Resume' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/jobs/reclassify-one/resume', expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByRole('button', { name: 'Pause' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/jobs/reclassify-one/cancel', expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByRole('button', { name: 'Cancel now' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel now' }));
    await waitFor(() => expect(cancelRequests).toBe(2));
  });

  it('treats stale-span regeneration as an active reclassification phase', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        state: 'ingesting',
        chapters: [],
        review_issues: [],
        speakers: [],
        render_jobs: [],
        preview_jobs: [],
        export_jobs: [],
        pronunciations: [],
        render_progress: { completed: 0, total: 0 },
        pipeline_jobs: [{
          id: 'reextract-one',
          type: 'audiobook.ingest',
          reason: 'user_requested_reclassification',
          status: 'running',
          progress: {},
          error: null,
          attempts: 1,
          max_attempts: 3,
          can_retry: false,
        }],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Edit project' }));

    expect(await screen.findByText('Refreshing source spans')).toBeInTheDocument();
    expect(screen.getByText('Regenerating canonical dialogue spans before AI analysis')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reclassifying…' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  });

  it('exposes the updated project tabs with working controls', async () => {
    let deleted = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one') && init?.method === 'DELETE') {
        deleted = true;
        return new Response(null, { status: 204 });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: deleted ? [] : [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, state: 'ready_to_export', cover_asset_id: 'cover-one', source_format: 'pdf', source_filename: 'the-book.pdf',
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 240 }],
        review_issues: [], speakers: [], render_jobs: [{ id: 'render-one', chapter_id: 'chapter-one', status: 'completed', progress: {} }],
        preview_jobs: [], export_jobs: [], pronunciations: [], render_progress: { completed: 1, total: 1 },
        word_count: 48, estimated_runtime_seconds: 30,
      };
      else if (url.endsWith('/projects/book-one/chapters/chapter-one')) body = {
        id: 'chapter-one', ordinal: 0, title: 'Opening', canonical_text: 'A short opening.', spans: [],
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: 'Library' }));
    expect(await screen.findByRole('heading', { name: 'Audiobook Library' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Search audiobooks' })).toBeInTheDocument();
    expect(await screen.findByText('the-book.pdf')).toBeInTheDocument();
    expect(screen.queryByText('Fiction')).not.toBeInTheDocument();
    expect(screen.getByText('Source Storage')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter by format' }), { target: { value: 'epub' } });
    expect(screen.queryByRole('button', { name: 'Open' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter by format' }), { target: { value: 'pdf' } });
    fireEvent.click(screen.getByRole('button', { name: 'List view' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Search audiobooks' }), { target: { value: 'The Book' } });
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument();
    const pdfDownload = await screen.findByRole('link', { name: 'Download The Book source' });
    expect(pdfDownload).toHaveAttribute('href', '/api/audiobook/projects/book-one/source/download');
    expect(pdfDownload).toHaveTextContent('Download PDF');
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    await screen.findByRole('button', { name: 'Edit project' });
    fireEvent.click(screen.getAllByRole('button', { name: /^Chapters$/ }).at(-1)!);
    expect((await screen.findAllByRole('heading', { name: 'Chapters' })).length).toBeGreaterThan(1);
    expect(screen.getByRole('textbox', { name: 'Search chapters' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Assets$/ }));
    expect(await screen.findByRole('heading', { name: 'Project Assets' })).toBeInTheDocument();
    expect(screen.getAllByText('Project cover').length).toBeGreaterThan(0);
    expect(screen.queryByText('chapter_01.jpg')).not.toBeInTheDocument();
    expect(screen.queryByText('Opening-narration.wav')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Documents$/ }));
    expect(await screen.findByRole('heading', { name: 'Project Documents' })).toBeInTheDocument();
    expect(screen.queryByText('Chapter outline (generated)')).not.toBeInTheDocument();
    expect(screen.getAllByText('the-book.pdf').length).toBeGreaterThan(0);
    expect(screen.getByText('Replace manuscript')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /New document/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Render & Export$/ }));
    expect(await screen.findByRole('heading', { name: 'Render & Export' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Render book' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Edit project' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete audiobook' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Delete “The Book”?');
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete audiobook' }).at(-1)!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one', expect.objectContaining({ method: 'DELETE' }),
    ));
    expect(await screen.findByRole('heading', { name: 'Audiobook Library' })).toBeInTheDocument();
  });

  it('deletes a generated asset from the asset inspector after confirmation', async () => {
    let deleted = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/projects/book-one/assets/asset-export') && init?.method === 'DELETE') {
        deleted = true;
        return new Response(JSON.stringify({ asset_id: 'asset-export', deleted: true, file_deleted: true }), {
          status: 200, headers: { 'content-type': 'application/json' },
        });
      }
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = deleted ? { exports: [] } : {
        exports: [{ id: 'export-one', format: 'mp3', manifest_hash: 'hash', asset_id: 'asset-export', created_at: '2026-09-21T00:00:00Z', byte_size: 3 }],
      };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, state: 'exported', cover_asset_id: 'cover-one', source_format: 'pdf', source_filename: 'the-book.pdf',
        chapters: [], review_issues: [], speakers: [], render_jobs: [], preview_jobs: [], export_jobs: [],
        pronunciations: [], render_progress: { completed: 0, total: 0 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^Assets$/ }));
    expect(await screen.findByText('audiobook.mp3')).toBeInTheDocument();
    fireEvent.click(screen.getByText('audiobook.mp3'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Delete “audiobook.mp3”?');
    fireEvent.click(screen.getByRole('button', { name: 'Delete asset' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/audiobook/projects/book-one/assets/asset-export', expect.objectContaining({ method: 'DELETE' }),
    ));
    await waitFor(() => expect(screen.queryByText('audiobook.mp3')).not.toBeInTheDocument());
  });

});
