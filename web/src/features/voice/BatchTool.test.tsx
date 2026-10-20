import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AssetListResponse } from '../../api/client';
import { omnixTheme } from '../../design/theme';
import { createTestQueryClient } from '../../test/renderWithProviders';
import { BatchTool, chainProblem } from './BatchTool';
import { PushToTalkButton } from './PushToTalkButton';

type Asset = AssetListResponse['assets'][number];

function path(input: RequestInfo | URL): string {
  const value = input instanceof Request ? input.url : String(input);
  return new URL(value, 'http://localhost').pathname;
}

const recording = { id: 'audio:talk', type: 'audio', mime_type: 'audio/wav', file_name: 'talk.wav', metadata: { title: 'Talk' } } as unknown as Asset;
const recipe = { id: 'vrecipe:1', name: 'Clean', version: 2, steps: [{ tool: 'isolate', settings: {} }, { tool: 'transcribe', settings: {} }], created_at: '', updated_at: '' };
const run = {
  id: 'vbatch:1', recipe_id: 'vrecipe:1', recipe_version: 2, title: 'Clean', watch_folder: '', status: 'running', created_at: '2026-10-19T10:00:00Z', updated_at: '',
  steps: recipe.steps, counts: { done: 1, running: 1 },
  items: [
    { id: 'vbitem:1', position: 0, source_asset_id: 'audio:talk', current_asset_id: 'audio:talk', step_index: 2, status: 'done', job_id: '', attempts: 0, outputs: [{ tool: 'isolate', title: 'Talk vocals' }], error: '', output_name: '' },
    { id: 'vbitem:2', position: 1, source_asset_id: 'audio:b', current_asset_id: 'audio:b', step_index: 0, status: 'running', job_id: 'job:1', attempts: 1, outputs: [], error: 'engine crashed', output_name: '' },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderTool() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MantineProvider theme={omnixTheme}><BatchTool assets={[recording]} /></MantineProvider>
    </QueryClientProvider>,
  );
}

describe('BatchTool', () => {
  it('explains a chain of steps that cannot run', () => {
    expect(chainProblem([{ tool: 'isolate', settings: {} }, { tool: 'transcribe', settings: {} }, { tool: 'subtitles', settings: {} }])).toBe('');
    expect(chainProblem([{ tool: 'subtitles', settings: {} }])).toMatch(/needs transcript/);
    expect(chainProblem([{ tool: 'transcribe', settings: {} }, { tool: 'isolate', settings: {} }])).toMatch(/needs audio, but the step before it makes a transcript/);
    expect(chainProblem([{ tool: 'export', settings: {} }, { tool: 'enhance', settings: {} }])).toMatch(/nothing to work on/);
  });

  it('starts a batch over chosen recordings and shows its progress', async () => {
    let started: Record<string, unknown> | undefined;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const route = path(input);
      const method = input instanceof Request ? input.method : init?.method ?? 'GET';
      if (route === '/api/voice/recipes') return Response.json({ recipes: [recipe], tools: ['isolate', 'transcribe'] });
      if (route === '/api/voice/batches' && method === 'POST') {
        started = (input instanceof Request ? await input.json() : JSON.parse(String(init?.body))) as Record<string, unknown>;
        return Response.json(run, { status: 201 });
      }
      if (route === '/api/voice/batches') return Response.json({ runs: [run] });
      if (route === '/api/voice/batches/vbatch%3A1' || route === '/api/voice/batches/vbatch:1') return Response.json(run);
      if (route === '/api/voice/clients') return Response.json({ detail: 'workspace_admin_required' }, { status: 403 });
      return new Response('not found', { status: 404 });
    }));
    renderTool();
    expect(await screen.findByText('Isolate vocals → Transcribe · v2')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Batch recipe'), { target: { value: 'vrecipe:1' } });
    fireEvent.click(screen.getByLabelText('Talk'));
    fireEvent.click(screen.getByRole('button', { name: 'Start batch' }));
    await waitFor(() => expect(started).toEqual({ recipe_id: 'vrecipe:1', asset_ids: ['audio:talk'], title: '' }));
    expect(await screen.findByText('1 of 2 finished · running')).toBeInTheDocument();
    expect(screen.getByText('Talk vocals')).toBeInTheDocument();
    expect(screen.getByText(/engine crashed/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeInTheDocument();
  });

  it('refuses to save a recipe whose steps do not chain', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const route = path(input);
      if (route === '/api/voice/recipes') return Response.json({ recipes: [], tools: [] });
      if (route === '/api/voice/batches') return Response.json({ runs: [] });
      return Response.json({ clients: [], capabilities: [] });
    }));
    renderTool();
    fireEvent.click(await screen.findByRole('button', { name: 'New recipe' }));
    fireEvent.change(screen.getByLabelText('Recipe name'), { target: { value: 'Broken' } });
    fireEvent.change(screen.getByLabelText('Step 1 tool'), { target: { value: 'subtitles' } });
    expect(screen.getByRole('alert')).toHaveTextContent('needs transcript');
    expect(screen.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
  });
});

describe('PushToTalkButton', () => {
  it('stays hidden where the browser cannot record', () => {
    const { container } = render(<PushToTalkButton onText={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('never records when the button was released before the microphone was granted', async () => {
    let grant: (stream: MediaStream) => void = () => undefined;
    const stopTrack = vi.fn();
    const recorders: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ ready: true, detail: '' })));
    vi.stubGlobal('MediaRecorder', class {
      static isTypeSupported() { return true; }
      constructor() { recorders.push(this); }
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: () => new Promise<MediaStream>((resolve) => { grant = resolve; }) },
    });
    try {
      render(<PushToTalkButton onText={() => undefined} />);
      const button = screen.getByRole('button', { name: 'Hold to dictate' });
      fireEvent.pointerDown(button);
      fireEvent.pointerUp(button);   // released while the permission prompt is open
      grant({ getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream);
      expect(await screen.findByText('Microphone ready: hold the button while you speak.')).toBeInTheDocument();
      expect(stopTrack).toHaveBeenCalled();
      expect(recorders).toEqual([]);
    } finally {
      Reflect.deleteProperty(navigator, 'mediaDevices');
    }
  });
});
