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
      else if (url.endsWith('/projects/book-one/exports')) body = { exports: [] };
      else if (url.endsWith('/projects/book-one')) body = {
        ...project,
        chapters: [{ id: 'chapter-one', ordinal: 0, title: 'Opening',
          canonical_text: 'The exact book text.\n\nIt stays here.', spans: [] }],
        review_issues: [{ id: 'issue-one', reason: 'speaker uncertain',
          source_text: '"Hello," she said.', chapter_id: 'chapter-one',
          chapter_title: 'Opening', speaker_id: null }],
        speakers: [], render_jobs: [], export_jobs: [],
        render_progress: { completed: 0, total: 1 },
      };
      else throw new Error(`unexpected API request ${url}`);
      return new Response(JSON.stringify(body), { status: 200,
        headers: { 'content-type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    const firstVisit = renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect(await screen.findByText(/The exact book text/)).toBeInTheDocument();
    expect(screen.getByText('"Hello," she said.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Render book' })).toBeDisabled();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/audiobook/projects/book-one', expect.anything()));
    firstVisit.unmount();
    renderWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: /The Book/i }));
    expect(await screen.findByText(/The exact book text/)).toBeInTheDocument();
  });
});
