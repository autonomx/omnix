import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { createTestQueryClient } from '../../test/renderWithProviders';
import { DubbingWorkspace } from './DubbingWorkspace';

function renderDubbing() {
  const module = omnixModules.find((entry) => entry.id === 'dubbing');
  if (!module) throw new Error('Dubbing module is missing');
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark" env="test">
      <QueryClientProvider client={createTestQueryClient()}>
        <DubbingWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function url(input: RequestInfo | URL): URL {
  return new URL(input instanceof Request ? input.url : input.toString(), 'http://localhost');
}

const line = (overrides: Record<string, unknown> = {}) => ({
  id: 'line:1', position: 0, speaker: 'Speaker 1', start_seconds: 0, end_seconds: 3, budget_seconds: 3,
  source_text: 'Good morning.', translation: 'Buenos días.', translation_revision: 1, translation_origin: 'llm',
  voice_override: '', take_asset_id: 'take:1', take_revision: 1, take_seconds: 2.9, fit_status: 'fits', fit_ratio: 0.97,
  shortenings: 0, take_current: true, approved: false, ...overrides,
});

const project = (segments: Array<Record<string, unknown>>, overrides: Record<string, unknown> = {}) => ({
  id: 'dub:1', title: 'Planning call', source_asset_id: 'dubbing-source:1', source_language: 'en', target_language: 'es',
  translator: '', engine: '', speakers: 0, duration_seconds: 6, created_at: '', updated_at: '',
  steps: { synthesize: { status: 'done' } }, assets: { background: 'a:bg' }, casting: { 'Speaker 1': 'voice-cloning:1' },
  line_count: segments.length, approved_count: segments.filter((segment) => segment.approved).length, segments, ...overrides,
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DubbingWorkspace', () => {
  it('uploads a video, starts the pipeline, and warns before a cloud translator', async () => {
    let upload: { query: URLSearchParams; body: unknown } | undefined;
    const jobs: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const target = url(input);
      if (target.pathname === '/api/dubbing/projects' && init?.method === 'POST') {
        upload = { query: target.searchParams, body: init.body };
        return Response.json(project([]), { status: 201 });
      }
      if (target.pathname === '/api/dubbing/projects') return Response.json({ projects: [] });
      if (target.pathname === '/api/jobs' && init?.method === 'POST') {
        jobs.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ id: 'job:1', module: 'dubbing', type: 'dub.ingest', status: 'queued', resource_class: 'cpu', priority: 0, created_at: '', updated_at: '' });
      }
      if (target.pathname === '/api/dubbing/projects/dub%3A1') return Response.json(project([]));
      if (target.pathname === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderDubbing();
    const file = new File(['video'], 'call.mp4', { type: 'video/mp4' });
    fireEvent.change(screen.getByLabelText('Video'), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText('Target language'), { target: { value: 'de' } });
    fireEvent.change(screen.getByLabelText('Translator'), { target: { value: 'openrouter' } });
    expect(screen.getByRole('note')).toHaveTextContent('The transcript leaves this machine');
    fireEvent.click(screen.getByRole('button', { name: 'Upload and start' }));
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(upload?.query.get('filename')).toBe('call.mp4');
    expect(upload?.query.get('target_language')).toBe('de');
    expect(upload?.query.get('translator')).toBe('openrouter');
    expect(upload?.body).toBe(file);
    expect(jobs[0]).toMatchObject({ module: 'dubbing', type: 'dub.ingest', input_payload: { project_id: 'dub:1', chain: true } });
  });

  it('reviews lines: edits, regenerates, approves, and exports only when every line is approved', async () => {
    let current = project([line(), line({ id: 'line:2', position: 1, speaker: 'Speaker 2', start_seconds: 3.5, end_seconds: 6, source_text: 'Thanks.', translation: 'Gracias.', fit_status: 'over' })]);
    const jobs: Array<Record<string, unknown>> = [];
    let edited: Record<string, unknown> | undefined;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const target = url(input);
      if (target.pathname === '/api/dubbing/projects' && (!init?.method || init.method === 'GET')) return Response.json({ projects: [current] });
      if (target.pathname === '/api/dubbing/projects/dub%3A1') return Response.json(current);
      if (target.pathname.endsWith('/lines/line%3A1') && init?.method === 'PUT') {
        edited = JSON.parse(String(init.body)) as Record<string, unknown>;
        current = { ...current, segments: [line({ translation: 'Muy buenos días.', translation_revision: 2, take_current: false, translation_origin: 'person' }), current.segments[1]] };
        return Response.json(current);
      }
      if (target.pathname.endsWith('/approval') && init?.method === 'POST') {
        const ids = (JSON.parse(String(init.body)) as { line_ids: string[] }).line_ids;
        const segments = current.segments.map((segment) => (ids.includes(String(segment.id)) ? { ...segment, approved: true } : segment));
        current = project(segments);
        return Response.json(current);
      }
      if (target.pathname === '/api/jobs' && init?.method === 'POST') {
        jobs.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ id: `job:${jobs.length}`, module: 'dubbing', type: 'dub.synthesize', status: 'queued', resource_class: 'gpu:tts', priority: 0, created_at: '', updated_at: '' });
      }
      if (target.pathname === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderDubbing();
    fireEvent.click(await screen.findByRole('button', { name: /Planning call/ }));
    expect(await screen.findByText('Too long')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mix and export' })).toBeDisabled();
    expect(screen.getByRole('group', { name: 'Take lane' })).toBeInTheDocument();

    const speakAgain = within(screen.getByText('Thanks.').closest('li') as HTMLElement).getByRole('button', { name: 'Speak again' });
    fireEvent.click(speakAgain);
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(jobs[0]).toMatchObject({ type: 'dub.synthesize', input_payload: { project_id: 'dub:1', line_ids: ['line:2'], chain: false } });

    fireEvent.click(screen.getByRole('button', { name: 'Approve 2 ready lines' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Mix and export' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Mix and export' }));
    await waitFor(() => expect(jobs).toHaveLength(2));
    expect(jobs[1]).toMatchObject({ type: 'dub.mux', resource_class: 'cpu' });

    const translation = screen.getByLabelText('Line 1 translation');
    fireEvent.change(translation, { target: { value: 'Muy buenos días.' } });
    fireEvent.blur(translation);
    await waitFor(() => expect(edited).toEqual({ translation: 'Muy buenos días.' }));
    expect(await screen.findByText('Take is out of date')).toBeInTheDocument();
    expect(screen.getByLabelText('Approve line 1')).toBeDisabled();
  });
});
