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
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown;
      if (url.endsWith('/projects')) body = { projects: [project] };
      else if (url.endsWith('/voices')) body = { voices: [] };
      else if (url.endsWith('/models/current')) body = { provider_id: 'faster-qwen3-tts', model_id: 'Qwen3-TTS', model_revision: 'sha256:test-model' };
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening', character_count: 36 }],
        review_issues: [{ id: 'issue-one', reason: 'speaker uncertain',
          source_text: '"Hello," she said.', chapter_id: 'chapter-one',
          chapter_title: 'Opening', speaker_id: null }],
        speakers: [], render_jobs: [], export_jobs: [],
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
    expect(screen.getByText('"Hello," she said.')).toBeInTheDocument();
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
});
