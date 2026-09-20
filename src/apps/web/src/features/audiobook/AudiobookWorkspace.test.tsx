import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { AudiobookWorkspace } from './AudiobookWorkspace';

const project = {
  id: 'book-one', title: 'The Book', author: 'The Author', language: 'en',
  state: 'review_needed', current_source_revision_id: 'source-one',
};

function renderWorkspace() {
  const module = omnixModules.find((entry) => entry.id === 'audiobook');
  if (!module) throw new Error('audiobook module missing');
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AudiobookWorkspace module={module} /></QueryClientProvider>);
}

describe('AudiobookWorkspace', () => {
  afterEach(() => vi.unstubAllGlobals());

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
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/audiobook/projects/book-one', expect.anything()));
    firstVisit.unmount();
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect(await screen.findByLabelText('Canonical chapter text')).toHaveTextContent('The exact book text.');
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
    expect(screen.getByText(/1 generated · 2 cache hits/)).toBeInTheDocument();
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

  it('exposes the updated project tabs with working controls', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project, state: 'ready_to_export', cover_asset_id: 'cover-one',
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
    fireEvent.click(await screen.findByRole('button', { name: 'Books' }));
    expect(await screen.findByRole('heading', { name: 'All ebooks' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Search ebooks' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'List view' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Search ebooks' }), { target: { value: 'The Book' } });
    expect(screen.getByRole('button', { name: 'Open ebook' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open ebook' }));
    await screen.findByRole('button', { name: 'Edit project' });
    fireEvent.click(screen.getAllByRole('button', { name: /^Chapters$/ }).at(-1)!);
    expect((await screen.findAllByRole('heading', { name: 'Chapters' })).length).toBeGreaterThan(1);
    expect(screen.getByRole('textbox', { name: 'Search chapters' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Assets$/ }));
    expect(await screen.findByRole('heading', { name: 'Project Assets' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^Documents$/ }));
    expect(await screen.findByRole('heading', { name: 'Project Documents' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /New document/ }));
    expect(screen.getByRole('textbox', { name: 'Document text' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: /^Render & Export$/ }));
    expect(await screen.findByRole('heading', { name: 'Render & Export' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Render book' })).toBeInTheDocument();
  });

});
