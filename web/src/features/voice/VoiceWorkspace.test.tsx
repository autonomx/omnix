import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { VoiceWorkspace } from './VoiceWorkspace';
import { createTestQueryClient } from '../../test/renderWithProviders';

// CodeMirror needs a real layout engine; jsdom gets a plain textarea with the same contract.
vi.mock('./VoiceScriptEditor', () => ({
  VoiceScriptEditor: ({ value, onChange, onGenerate, label = 'Script' }: { value: string; onChange: (value: string) => void; onGenerate: () => void; label?: string }) => (
    <textarea
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.currentTarget.value)}
      onKeyDown={(event) => { if (event.key === 'Enter' && event.ctrlKey) onGenerate(); }}
    />
  ),
}));

function renderVoice() {
  const queryClient = createTestQueryClient();
  const module = omnixModules.find((entry) => entry.id === 'voice');
  if (!module) throw new Error('Voice module is missing');
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark" env="test">
      <QueryClientProvider client={queryClient}>
        <VoiceWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

const fishEngines = (delivery = true) => ({
  selected: 'fish-s2-pro',
  engines: [{
    id: 'fish-s2-pro', label: 'Fish Audio S2 Pro', description: '', selected: true, installed: true,
    unavailable_reason: '', needs_transcripts: true, delivery_instruction: delivery,
    voice_controls: ['stability', 'style', 'speed', 'pitch', 'volume'],
  }],
  switch: { provider: null, phase: 'idle', error: null, voices: { prepared: [], failed: [], already_ready: 0 } },
});

const libraryAssets = [
  { id: 'voice-cloning:Dave', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'Dave.wav', created_at: '2026-06-14T00:00:00Z' },
  { id: 'voice-cloning:jinx2', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'jinx2.wav', metadata: { profile_name: 'jinx2', voice_id: 'jinx2', language: 'English' }, created_at: '2026-06-14T00:00:01Z' },
];

const queuedJob = {
  id: 'job:new', module: 'voice', type: 'tts.synthesize', status: 'queued',
  resource_class: 'gpu:tts', created_at: '2026-06-14T00:00:01Z',
  updated_at: '2026-06-14T00:00:01Z', priority: 0, progress: { current: 0, total: 1 },
};

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// Mantine transitions schedule state updates on timers. Let the last ones
// run while jsdom still exists; otherwise they can fire after teardown.
afterAll(async () => {
  await new Promise((resolve) => setTimeout(resolve, 400));
});

describe('VoiceWorkspace', () => {
  it('shows only shipped tools in the rail and keeps the chosen tool', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/tts/engines') {
        return Response.json({ selected: '', engines: [], switch: { provider: null, phase: 'idle', error: null, voices: { prepared: [], failed: [], already_ready: 0 } } });
      }
      if (path === '/api/dubbing/projects') return Response.json({ projects: [] });
      return Response.json({ jobs: [], assets: [], providers: [], models: [] });
    }));
    renderVoice();
    const rail = screen.getByRole('navigation', { name: 'Voice Studio tools' });
    expect(within(rail).getAllByRole('button').map((button) => button.textContent)).toEqual(['Speak', 'Voices', 'Design', 'Transcribe', 'Dub', 'Audio Tools', 'Batch', 'Models']);
    // Dubbing opens in the studio's canvas, so the rail stays beside it.
    fireEvent.click(within(rail).getByRole('button', { name: 'Dub' }));
    expect(await screen.findByRole('region', { name: 'Dub' })).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'New dub' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Voice Studio tools' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Dub' })).toBeNull();
    fireEvent.click(within(rail).getByRole('button', { name: 'Voices' }));
    expect(await screen.findByRole('region', { name: 'Clone a Voice' })).toBeInTheDocument();
    expect(window.localStorage.getItem('omnix.voice.studio.tool')).toBe('voices');
  });

  it('plays the completed speech when the job list still has a queued summary', async () => {
    let detailRequests = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/settings/profile') return Response.json({ success: true, settings: {} });
      if (path === '/api/assets') return Response.json({ assets: [] });
      if (path === '/api/jobs' && init?.method === 'POST') return Response.json(queuedJob);
      if (path === '/api/jobs/voice-summaries') {
        return Response.json({ jobs: [
          queuedJob,
          { ...queuedJob, id: 'job:old', status: 'completed', output_refs: [{ title: 'Old speech', data_url: 'data:audio/wav;base64,b2xk' }] },
        ] });
      }
      if (path === '/api/jobs/job%3Anew') {
        detailRequests += 1;
        return Response.json(detailRequests === 1 ? queuedJob : {
          ...queuedJob, status: 'completed', output_refs: [{ title: 'New speech', asset_id: 'audio:new', audio_url: '/api/assets/audio%3Anew/audio' }],
        });
      }
      if (path.endsWith('/peaks')) return Response.json({ asset_id: 'audio:new', duration: 1, sample_rate: 24000, peaks: [0.1, 0.5, 0.2] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});

    renderVoice();
    expect(await screen.findByText('Old speech · 3 speakers')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Script'), { target: { value: 'Dave: New line.' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate Speech/ }));

    expect(await screen.findByText('Generating new speech… · 1 speaker')).toBeInTheDocument();
    expect(await screen.findByText('New speech · 1 speaker', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(document.querySelector('audio')).toHaveAttribute('src', '/api/assets/audio%3Anew/audio');
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => requestPath(input as RequestInfo | URL) === '/api/voice/assets/audio%3Anew/peaks')).toBe(true));
  });

  it('pins the job to the selected engine and sends effect ids, delivery and pauses', async () => {
    let created: Record<string, unknown> | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/tts/engines') return Response.json(fishEngines());
      if (path === '/api/settings/profile') {
        return Response.json({
          success: true,
          settings: { settings_control_center: {
            revision: 'voice-r1',
            global: { providers: { tts: 'faster-qwen3-tts' } },
            voice: { language: 'English', speed: 1.25, effects: ['Compression', 'reverb'] },
          } },
        });
      }
      if (path === '/api/assets') return Response.json({ assets: libraryAssets });
      if (path === '/api/jobs' && init?.method === 'POST') {
        created = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ ...queuedJob, id: 'job:tts' });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderVoice();
    // Saved labels are off; saved ids apply.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reverb' })).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.getByRole('button', { name: 'Compression' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByLabelText('Output speed')).toHaveValue('1.25');

    fireEvent.change(screen.getByLabelText('Script'), { target: { value: 'Narrator: One.\n{pause 600ms}\nNarrator: Two.' } });
    fireEvent.change(screen.getByLabelText('Narrator voice'), { target: { value: 'voice-cloning:jinx2' } });
    fireEvent.change(screen.getByLabelText('Narrator delivery'), { target: { value: 'Whispering' } });
    fireEvent.click(screen.getByRole('button', { name: 'Equalizer' }));
    fireEvent.click(screen.getByRole('button', { name: /Generate Speech/ }));

    await waitFor(() => expect(created).toBeDefined());
    const payload = created?.input_payload as Record<string, unknown>;
    expect(payload.provider_id).toBe('fish-s2-pro');
    expect(payload.audio_effects).toEqual(['eq', 'reverb']);
    expect(payload.character_voice_assignments).toEqual([{ speaker: 'Narrator', voice_id: 'voice-cloning:jinx2', delivery_instruction: 'Whispering', line_count: 2 }]);
    expect(payload.script_segments).toEqual([
      { index: 0, speaker: 'Narrator', text: 'One.' },
      { index: 1, speaker: 'Narrator', text: 'Two.', pause_before_ms: 600 },
    ]);
    expect(screen.getByText('pause 600 ms')).toBeInTheDocument();
  });

  it('disables delivery and unused sliders with a reason on engines that ignore them', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/tts/engines') return Response.json(fishEngines(false));
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));

    renderVoice();
    await waitFor(() => expect(screen.getByLabelText('Output similarity')).toBeDisabled());
    expect(screen.getByLabelText('Output similarity').closest('label')).toHaveTextContent('Not used');
    expect(screen.getByLabelText('Output stability')).toBeEnabled();
    expect(screen.getAllByLabelText(/delivery$/)[0]).toBeDisabled();
    expect(screen.getByText('Fish Audio S2 Pro does not read delivery instructions.')).toBeInTheDocument();
    // "Style" is a sampling control now called Variation.
    expect(screen.getByLabelText('Output style').closest('label')).toHaveTextContent('Variation');
  });

  it('exports the current take with a format, rate and loudness preset', async () => {
    let exportRequest: Record<string, unknown> | undefined;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/jobs/voice-summaries') {
        return Response.json({ jobs: [{ ...queuedJob, id: 'job:done', status: 'completed', output_refs: [{ title: 'Take', asset_id: 'audio:take', audio_url: '/api/assets/audio%3Atake/audio' }] }] });
      }
      if (path === '/api/assets') {
        return Response.json({ assets: [{ id: 'export:take-mp3', module: 'voice', type: 'export', mime_type: 'audio/mpeg', file_name: 'take.mp3', metadata: { title: 'Take (MP3)' }, parent_asset_ids: ['audio:take'], created_at: '2026-06-14T00:00:02Z' }] });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        exportRequest = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ ...queuedJob, id: 'job:export', type: 'voice.export', resource_class: 'cpu' });
      }
      if (path.endsWith('/peaks')) return Response.json({ asset_id: 'audio:take', duration: 1, sample_rate: 24000, peaks: [0.2] });
      return new Response('not found', { status: 404 });
    }));

    renderVoice();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export take' })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Export format'), { target: { value: 'opus' } });
    // Opus offers only its own rates.
    expect(within(screen.getByLabelText('Export sample rate')).queryByRole('option', { name: '44.10 kHz' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Export loudness'), { target: { value: 'podcast' } });
    fireEvent.click(screen.getByRole('button', { name: 'Export take' }));
    await waitFor(() => expect(exportRequest).toBeDefined());
    expect(exportRequest?.type).toBe('voice.export');
    expect(exportRequest?.input_payload).toEqual({ asset_id: 'audio:take', format: 'opus', sample_rate: null, loudness: 'podcast' });
    expect(screen.getByRole('link', { name: 'Take (MP3)' })).toHaveAttribute('href', '/api/assets/export%3Atake-mp3/download');
  });

  it('casts a library voice, deletes one, and clones with a transcript reviewed first', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    let cloneRequest: Record<string, unknown> | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/settings/profile') {
        return Response.json({ success: true, settings: { settings_control_center: {
          revision: 'voice-clone-r1',
          global: { providers: { tts: 'faster-qwen3-tts', stt: 'parakeet', voiceCloning: 'faster-qwen3-tts' } },
          voice: { cloningLanguage: 'French', cloningQuality: 'Standard' },
        } } });
      }
      if (path === '/api/assets') return Response.json({ assets: libraryAssets });
      if (path === '/api/voice-cloning/assets/voice-cloning%3Ajinx2' && init?.method === 'DELETE') {
        return Response.json({ ok: true, asset_id: 'voice-cloning:jinx2', deleted: true, file_deleted: true });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        const request = JSON.parse(String(init.body)) as Record<string, unknown>;
        if (request.type === 'voice-cloning.transcribe-sample') {
          return Response.json({ ...queuedJob, id: 'job:transcribe', module: 'voice-cloning', type: request.type, status: 'completed', output_refs: [{ type: 'transcript', content: 'Sofia speaks these exact words.' }] });
        }
        cloneRequest = request;
        return Response.json({ ...queuedJob, id: 'job:clone', module: 'voice-cloning', type: request.type, status: 'completed', output_refs: [{ type: 'voice_profile', asset_id: 'voice-cloning:maya', sample_check: { warnings: ['Background noise is high.'] } }] });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Voices' }));
    expect((await screen.findAllByText('jinx2')).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByLabelText('Quality')).toHaveValue('Standard'));
    expect(screen.getByLabelText('Language / Accent')).toHaveValue('French');

    fireEvent.click(screen.getByRole('button', { name: 'Delete jinx2' }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) => requestPath(input as RequestInfo | URL) === '/api/voice-cloning/assets/voice-cloning%3Ajinx2' && init?.method === 'DELETE')).toBe(true));
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('permanently removes'));

    fireEvent.change(screen.getByLabelText('Voice Name'), { target: { value: 'Maya' } });
    fireEvent.change(screen.getByLabelText(/Audio sample/), { target: { files: [new File(['voice sample'], 'maya.wav', { type: 'audio/wav' })] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Generate Transcript' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Generate Transcript' }));
    await waitFor(() => expect(screen.getByLabelText('Reference transcript (optional)')).toHaveValue('Sofia speaks these exact words.'));
    expect(screen.getByRole('checkbox', { name: /Generate transcript with STT/ })).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: 'Create Clone' }));
    await waitFor(() => expect(cloneRequest).toBeDefined());
    const payload = cloneRequest?.input_payload as Record<string, unknown>;
    expect(payload.reference_text).toBe('Sofia speaks these exact words.');
    expect(payload.generate_transcript).toBe(false);
    expect(payload.stt_provider_id).toBe('parakeet');
    expect(payload.quality).toBe('Standard');
    expect(await screen.findByText(/Background noise is high\./)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: 'Use' })[0]);
    expect(await screen.findByRole('region', { name: 'Speak' })).toBeInTheDocument();
    expect(screen.getByText(/Cast Dave as dave\./)).toBeInTheDocument();
  });

  it('lists no invented jobs when nothing has run', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    expect(await screen.findByText('No jobs are running.')).toBeInTheDocument();
  });
});


describe('VoiceWorkspace saved scripts, takes and models (Phase 1)', () => {
  const savedScript = {
    id: 'vscript:1', title: 'Demo', text: 'dave: one\nbob: two', engine: 'faster-qwen3-tts', settings: {}, revision: 2,
    created_at: '2026-10-20T00:00:00Z', updated_at: '2026-10-20T00:00:00Z',
    lines: [
      { id: 'vline:d', position: 0, speaker: 'dave', text: 'one', pause_before_ms: null, delivery_instruction: '', voice_id: '', selected_take_id: 'vtake:d1',
        takes: [{ id: 'vtake:d1', line_id: 'vline:d', asset_id: 'voice_take:d1', job_id: 'job:1', engine: 'faster-qwen3-tts', text_hash: 'h', duration: 1.2, pinned: false, created_at: '2026-10-20T00:00:00Z' }] },
      { id: 'vline:b', position: 1, speaker: 'bob', text: 'two', pause_before_ms: null, delivery_instruction: '', voice_id: '', selected_take_id: 'vtake:b2',
        takes: [
          { id: 'vtake:b2', line_id: 'vline:b', asset_id: 'voice_take:b2', job_id: 'job:2', engine: 'faster-qwen3-tts', text_hash: 'h', duration: 0.9, pinned: false, created_at: '2026-10-20T00:01:00Z' },
          { id: 'vtake:b1', line_id: 'vline:b', asset_id: 'voice_take:b1', job_id: 'job:1', engine: 'faster-qwen3-tts', text_hash: 'h', duration: 1.0, pinned: false, created_at: '2026-10-20T00:00:00Z' },
        ] },
    ],
  };

  it('opens a saved script, renders one line again, picks a take and rebuilds from takes', async () => {
    const jobs: Array<Record<string, unknown>> = [];
    let selected = '';
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/voice/scripts' && (!init?.method || init.method === 'GET')) return Response.json({ scripts: [savedScript] });
      if (path === '/api/voice/scripts/vscript%3A1') return Response.json(savedScript);
      if (path.endsWith('/select') && init?.method === 'POST') {
        selected = decodeURIComponent(path.split('/takes/')[1].replace('/select', ''));
        return Response.json({ ...savedScript, lines: [savedScript.lines[0], { ...savedScript.lines[1], selected_take_id: selected }] });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        const request = JSON.parse(String(init.body)) as Record<string, unknown>;
        jobs.push(request);
        return Response.json({ ...queuedJob, id: `job:${jobs.length}`, type: request.type });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: libraryAssets });
      return new Response('not found', { status: 404 });
    }));

    renderVoice();
    await waitFor(() => expect(within(screen.getByLabelText('Saved scripts', { selector: 'select' })).getByRole('option', { name: 'Demo' })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Saved scripts', { selector: 'select' }), { target: { value: 'vscript:1' } });
    await waitFor(() => expect(screen.getByLabelText('Script')).toHaveValue('dave: one\nbob: two'));
    expect(await screen.findByLabelText('Line 2 take')).toHaveValue('vtake:b2');

    fireEvent.click(screen.getByRole('button', { name: 'Render line 2 again' }));
    await waitFor(() => expect(jobs).toHaveLength(1));
    const payload = jobs[0].input_payload as Record<string, unknown>;
    expect(payload.script_id).toBe('vscript:1');
    expect(payload.render_line_ids).toEqual(['vline:b']);
    expect((payload.script_segments as Array<Record<string, unknown>>).map((segment) => segment.line_id)).toEqual(['vline:d', 'vline:b']);

    fireEvent.change(screen.getByLabelText('Line 2 take'), { target: { value: 'vtake:b1' } });
    await waitFor(() => expect(selected).toBe('vtake:b1'));

    fireEvent.click(screen.getByRole('button', { name: 'Rebuild from takes' }));
    await waitFor(() => expect(jobs).toHaveLength(2));
    expect(jobs[1].type).toBe('voice.restitch');
    expect(jobs[1].input_payload).toMatchObject({ script_id: 'vscript:1' });
  });

  it('retries a failed job', async () => {
    let retried = '';
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [{ ...queuedJob, id: 'job:bad', status: 'failed', error: { message: 'engine missing' } }] });
      if (path.endsWith('/retry') && init?.method === 'POST') {
        retried = decodeURIComponent(path.split('/')[3]);
        return Response.json({ ...queuedJob, id: 'job:again' });
      }
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    fireEvent.click(await screen.findByRole('button', { name: /Failed \(1\)/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(retried).toBe('job:bad'));
  });

  it('installs a non-commercial model only after its terms are accepted', async () => {
    let installRequest: Record<string, unknown> | undefined;
    const model = {
      id: 'sortformer-4spk-v1', kind: 'stt', label: 'NVIDIA Sortformer diarizer (4 speakers)', repo_id: 'nvidia/diar_sortformer_4spk-v1',
      revision: 'main', licence: 'CC-BY-NC-4.0', licence_url: 'https://huggingface.co/nvidia/diar_sortformer_4spk-v1', size_gb: 0.5,
      vram_gb: 1, residency: 'helper', service: 'stt', commercial_use: false, gated: false, source: 'huggingface',
      output_terms: 'Non-commercial use only; opt in to use it.', capabilities: ['diarization'], requires_acceptance: true,
      status: 'missing', installed_revision: '', accepted_terms: false, disk_bytes: 0,
    };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/voice/models') return Response.json({ models: [model], hub_token_source: 'missing' });
      if (path === '/api/jobs' && init?.method === 'POST') {
        installRequest = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ ...queuedJob, id: 'job:install', type: 'models.install' });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    expect(await screen.findByText('NVIDIA Sortformer diarizer (4 speakers)')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'CC-BY-NC-4.0' })).toHaveAttribute('href', model.licence_url);
    const install = screen.getByRole('button', { name: 'Install' });
    expect(install).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: /Accept non-commercial terms/ }));
    fireEvent.click(install);
    await waitFor(() => expect(installRequest).toBeDefined());
    expect(installRequest?.type).toBe('models.install');
    expect(installRequest?.input_payload).toEqual({ model_id: 'sortformer-4spk-v1', accept_terms: true });
  });
});


describe('VoiceWorkspace Transcribe tool (Phase 2)', () => {
  const recording = { id: 'audio:talk', module: 'voice', type: 'audio', mime_type: 'audio/wav', file_name: 'talk.wav', metadata: { title: 'Team call' }, created_at: '2026-10-19T00:00:00Z' };
  const transcriptAsset = { id: 'transcript:job-t', module: 'stt', type: 'transcript', mime_type: 'application/json', file_name: 'job-t.json', metadata: { title: 'Transcript of Team call' }, created_at: '2026-10-19T00:01:00Z' };
  const document = {
    schema: 'omnix-transcript-v1', language: 'de', duration: 6, engine: 'Parakeet-TDT', diarized: true,
    speakers: ['Speaker 1', 'Speaker 2'], text: 'Hallo zusammen. Guten Tag.', source_asset_id: 'audio:talk',
    segments: [
      { start: 0, end: 2, speaker: 'Speaker 1', text: 'Hallo zusammen.', words: [
        { start: 0, end: 0.8, word: 'Hallo', confidence: 0.9 }, { start: 0.9, end: 2, word: 'zusammen.', confidence: 0.3 },
      ] },
      { start: 3, end: 5, speaker: 'Speaker 2', text: 'Guten Tag.', words: [
        { start: 3, end: 3.8, word: 'Guten', confidence: 0.9 }, { start: 3.9, end: 5, word: 'Tag.', confidence: 0.95 },
      ] },
    ],
  };

  it('transcribes a recording, edits the transcript, saves it and hands a speaker to cloning', async () => {
    const jobs: Array<Record<string, unknown>> = [];
    let saved: Record<string, unknown> | undefined;
    let assets: Array<Record<string, unknown>> = [...libraryAssets, recording];
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/jobs' && init?.method === 'POST') {
        jobs.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ ...queuedJob, id: 'job:t', module: 'stt', type: 'stt.transcribe' });
      }
      if (path === '/api/jobs/job%3At') {
        assets = [...assets, transcriptAsset];
        return Response.json({ ...queuedJob, id: 'job:t', status: 'completed', output_refs: [{ type: 'transcript', asset_id: 'transcript:job-t' }] });
      }
      if (path === '/api/voice/transcripts/transcript%3Ajob-t' && init?.method === 'PUT') {
        saved = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ asset_id: 'transcript:job-t', title: 'Transcript of Team call', revision: 2, document: saved.document });
      }
      if (path === '/api/voice/transcripts/transcript%3Ajob-t') return Response.json({ asset_id: 'transcript:job-t', title: 'Transcript of Team call', revision: 1, document });
      if (path === '/api/voice/transcripts/transcript%3Ajob-t/speaker-sample') {
        return Response.json({ speaker: 'Host', text: 'Hallo zusammen.', duration: 12, sample_rate: 16000, mime_type: 'audio/wav', audio_base64: btoa('RIFF'), spans: [{ start: 0, end: 2 }] });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets });
      return new Response('not found', { status: 404 });
    }));

    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Transcribe' }));
    const recordingSelect = await screen.findByLabelText('Recording');
    await waitFor(() => expect(within(recordingSelect).getByRole('option', { name: 'Team call' })).toBeInTheDocument());
    fireEvent.change(recordingSelect, { target: { value: 'audio:talk' } });
    fireEvent.change(screen.getByLabelText('Speakers'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Transcript language'), { target: { value: 'de' } });
    fireEvent.click(within(screen.getByRole('region', { name: 'Transcribe' })).getByRole('button', { name: 'Transcribe' }));
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(jobs[0]).toMatchObject({ type: 'stt.transcribe', input_ref: { asset_id: 'audio:talk' } });
    expect(jobs[0].input_payload).toMatchObject({ timed: true, diarize: true, speakers: 2, language: 'de' });

    // The finished transcript opens: low-confidence words are flagged and words seek playback.
    const word = await screen.findByRole('button', { name: 'zusammen.' });
    expect(word).toHaveClass('low');
    fireEvent.click(screen.getByRole('button', { name: 'Guten' }));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Rename Speaker 1'), { target: { value: 'Host' } });
    fireEvent.blur(screen.getByLabelText('Rename Speaker 1'));
    fireEvent.click(screen.getByRole('button', { name: 'Split segment 2' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tag.' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(saved).toBeDefined());
    expect(saved?.expected_revision).toBe(1);
    const savedDocument = saved?.document as { speakers: string[]; segments: Array<{ text: string }> };
    expect(savedDocument.speakers).toEqual(['Host', 'Speaker 2']);
    expect(savedDocument.segments.map((segment) => segment.text)).toEqual(['Hallo zusammen.', 'Guten', 'Tag.']);

    fireEvent.click(await screen.findByRole('button', { name: 'Make a voice from Host' }));
    expect(await screen.findByText("Host's sample is ready to clone below.")).toBeInTheDocument();
    expect(screen.getByLabelText('Reference transcript (optional)')).toHaveValue('Hallo zusammen.');
    expect(screen.getByText(/Host-sample\.wav/)).toBeInTheDocument();
  });
});


describe('VoiceWorkspace Design tool (Phase 3)', () => {
  const designModel = {
    id: 'qwen3-tts-1.7b-voicedesign', kind: 'tts', label: 'Qwen3-TTS 1.7B VoiceDesign', repo_id: 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign',
    revision: 'main', licence: 'Apache-2.0', licence_url: 'https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign', size_gb: 4.5,
    vram_gb: 7, residency: 'swapped', service: 'tts', commercial_use: true, gated: false, source: 'huggingface', output_terms: '',
    capabilities: ['voice_design'], requires_acceptance: false, status: 'installed', installed_revision: 'abc', accepted_terms: false, disk_bytes: 1,
  };

  it('designs three candidates from chips and text, varies them, and saves one as a voice', async () => {
    const jobs: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/voice/models') return Response.json({ models: [designModel], hub_token_source: 'missing' });
      if (path === '/api/jobs' && init?.method === 'POST') {
        const request = JSON.parse(String(init.body)) as Record<string, unknown>;
        jobs.push(request);
        return Response.json({ ...queuedJob, id: `job:d${jobs.length}`, type: request.type });
      }
      if (path.startsWith('/api/jobs/job%3Ad')) {
        const index = Number(path.slice('/api/jobs/job%3Ad'.length)) - 1;
        const request = jobs[index];
        if (request.type === 'voice.design') {
          const seeds = (request.input_payload as { seeds: number[] }).seeds;
          return Response.json({ ...queuedJob, id: `job:d${index + 1}`, status: 'completed', output_refs: seeds.map((seed, position) => ({
            type: 'audio', kind: 'voice_design_candidate', asset_id: `audio:c${index}-${position}`, audio_url: `/api/assets/audio:c${index}-${position}/audio`,
            title: `Candidate ${position + 1}`, seed, description: (request.input_payload as { description: string }).description,
          })) });
        }
        return Response.json({ ...queuedJob, id: `job:d${index + 1}`, status: 'completed', output_refs: [{ type: 'audio', title: 'Granny Rose', asset_id: 'voice-cloning:Granny-Rose' }] });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: libraryAssets });
      return new Response('not found', { status: 404 });
    }));

    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Design' }));
    const generate = await screen.findByRole('button', { name: 'Generate 3' });
    expect(generate).toBeDisabled();  // nothing described yet
    fireEvent.click(within(screen.getByRole('group', { name: 'Age' })).getByRole('button', { name: 'elderly' }));
    fireEvent.click(within(screen.getByRole('group', { name: 'Gender' })).getByRole('button', { name: 'female' }));
    fireEvent.click(within(screen.getByRole('group', { name: 'Accent' })).getByRole('button', { name: 'Irish' }));
    fireEvent.change(screen.getByLabelText('Voice description'), { target: { value: 'kind, a little husky' } });
    fireEvent.change(screen.getByLabelText('Seed'), { target: { value: '100' } });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(jobs[0]).toMatchObject({ type: 'voice.design', input_payload: {
      description: 'elderly female Irish-accented voice, kind, a little husky', seeds: [100, 101, 102], language: 'en',
    } });
    expect(await screen.findByLabelText('Candidate 3 preview')).toHaveAttribute('src', '/api/assets/audio:c0-2/audio');

    fireEvent.click(screen.getByRole('button', { name: 'Vary' }));
    await waitFor(() => expect(jobs).toHaveLength(2));
    const varied = (jobs[1].input_payload as { seeds: number[]; description: string });
    expect(varied.description).toBe('elderly female Irish-accented voice, kind, a little husky');
    expect(varied.seeds).not.toEqual([100, 101, 102]);

    const name = await screen.findByLabelText('Name for Candidate 2');
    fireEvent.change(name, { target: { value: 'Granny Rose' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save as voice' })[1]);
    await waitFor(() => expect(jobs).toHaveLength(3));
    expect(jobs[2]).toMatchObject({ type: 'voice.design.save', input_payload: { seed: varied.seeds[1], profile_name: 'Granny Rose', language: 'en' } });
    expect(await screen.findByText('Granny Rose is in your voice library.')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Clone a Voice' })).toBeInTheDocument();
  });

  it('asks for the design model before designing', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/voice/models') return Response.json({ models: [{ ...designModel, status: 'missing' }], hub_token_source: 'missing' });
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Design' }));
    expect(await screen.findByText(/Install “Qwen3-TTS 1.7B VoiceDesign”/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Voice description'), { target: { value: 'a pirate' } });
    expect(screen.getByRole('button', { name: 'Generate 3' })).toBeDisabled();
  });
});


describe('VoiceWorkspace Audio Tools (Phase 4)', () => {
  const interview = { id: 'audio:interview', module: 'voice', type: 'audio', mime_type: 'audio/wav', file_name: 'interview.wav', metadata: { title: 'Interview' }, created_at: '2026-10-19T00:00:00Z' };

  it('isolates vocals from a recording and turns watermarking on', async () => {
    const jobs: Array<Record<string, unknown>> = [];
    let watermark = false;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/voice/audio-tools') return Response.json({ configured: true, available: true, detail: '', tools: {}, watermark: { enabled: watermark } });
      if (path === '/api/voice/watermark' && init?.method === 'PUT') {
        watermark = (JSON.parse(String(init.body)) as { enabled: boolean }).enabled;
        return Response.json({ enabled: watermark });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        jobs.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ ...queuedJob, id: 'job:iso', type: 'audio.isolate' });
      }
      if (path === '/api/jobs/job%3Aiso') {
        return Response.json({ ...queuedJob, id: 'job:iso', status: 'completed', output_refs: [
          { type: 'audio', kind: 'stem_vocals', asset_id: 'audio:v', title: 'Interview (vocals)', audio_url: '/api/assets/audio:v/audio' },
          { type: 'audio', kind: 'stem_background', asset_id: 'audio:b', title: 'Interview (background)', audio_url: '/api/assets/audio:b/audio' },
        ] });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [...libraryAssets, interview] });
      return new Response('not found', { status: 404 });
    }));

    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Audio Tools' }));
    const source = await screen.findByLabelText('Audio source');
    await waitFor(() => expect(within(source).getByRole('option', { name: 'Interview' })).toBeInTheDocument());
    fireEvent.change(source, { target: { value: 'audio:interview' } });
    fireEvent.change(screen.getByLabelText('Separation model'), { target: { value: 'demucs' } });
    const isolate = screen.getByRole('button', { name: 'Isolate vocals' });
    await waitFor(() => expect(isolate).toBeEnabled());
    fireEvent.click(isolate);
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(jobs[0]).toMatchObject({ type: 'audio.isolate', resource_class: 'gpu:audio', input_payload: { asset_id: 'audio:interview', model: 'demucs' } });
    expect(await screen.findByLabelText('Interview (vocals) playback')).toHaveAttribute('src', '/api/assets/audio:v/audio');
    expect(screen.getByLabelText('Interview (background) playback')).toBeInTheDocument();

    const toggle = screen.getByRole('checkbox', { name: 'Watermark every render' });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(watermark).toBe(true));
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Watermark every render' })).toBeChecked());
  });

  it('says when the audio service is down, and the clone switches wait for it', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/voice/audio-tools') return Response.json({ configured: false, available: false, detail: 'The audio service is not configured (OMNIX_AUDIO_URL)', tools: {}, watermark: { enabled: false } });
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [interview] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Audio Tools' }));
    expect(await screen.findByText(/The audio service is not running: The audio service is not configured/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Voices' }));
    expect(await screen.findByRole('checkbox', { name: 'Isolate vocals first' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'Clean up noise' })).toBeDisabled();
  });
});

describe('VoiceWorkspace Models tool and engine groups (Phase 5)', () => {
  const omnivoice = {
    id: 'omnivoice', kind: 'tts', label: 'OmniVoice (600+ languages)', repo_id: 'k2-fsa/OmniVoice', revision: 'main',
    licence: 'CC-BY-NC-4.0', licence_url: 'https://huggingface.co/k2-fsa/OmniVoice', size_gb: 2.5, vram_gb: 3, residency: 'engine',
    service: 'omnivoice', commercial_use: false, gated: false, source: 'huggingface', output_terms: 'Non-commercial use only.',
    capabilities: ['synthesis', 'voice_clone', 'many_languages'], requires_acceptance: true, status: 'missing', installed_revision: '',
    accepted_terms: false, disk_bytes: 0,
    environment: { name: 'omnix-omnivoice', ready: false, setup: 'conda create -n omnix-omnivoice python=3.11 && conda run -n omnix-omnivoice python -m pip install --require-hashes -r src/services/omnivoice/omnivoice.lock.txt' },
  };
  const parakeet = {
    ...omnivoice, id: 'parakeet-tdt-0.6b-v3', label: 'NVIDIA Parakeet-TDT 0.6B v3', licence: 'CC-BY-4.0', commercial_use: true,
    requires_acceptance: false, service: 'stt', residency: 'helper', capabilities: ['transcription', 'word_timestamps'],
    status: 'installed', installed_revision: '541d1f99c6b0c3cd', disk_bytes: 2_500_000_000, environment: { name: 'rpg-stt', ready: true, setup: '' },
  };

  it('shows the GPU, each model against the 24 GB target, setup for missing environments, and updates', async () => {
    const jobs: Array<Record<string, unknown>> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/voice/models') {
        return Response.json({ models: [omnivoice, parakeet], hub_token_source: 'missing', vram_target_gb: 24,
          hardware: { device: 'NVIDIA GeForce RTX 4090', vram_total_bytes: 25_769_803_776, vram_free_bytes: 4_294_967_296 } });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        jobs.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return Response.json({ ...queuedJob, id: 'job:m', type: 'models.install' });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    expect(await screen.findByText(/NVIDIA GeForce RTX 4090 · 24.0 GB VRAM, 4.0 GB free now/)).toBeInTheDocument();
    const omni = screen.getByText('OmniVoice (600+ languages)').closest('li') as HTMLElement;
    expect(within(omni).getByText(/conda create -n omnix-omnivoice/)).toBeInTheDocument();
    expect(within(omni).queryByRole('button', { name: 'Install' })).toBeNull();
    expect(within(omni).getByText('600+ languages')).toBeInTheDocument();
    const stt = screen.getByText('NVIDIA Parakeet-TDT 0.6B v3').closest('li') as HTMLElement;
    expect(within(stt).getByText(/revision 541d1f99/)).toBeInTheDocument();
    fireEvent.click(within(stt).getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(jobs).toHaveLength(1));
    expect(jobs[0]).toMatchObject({ type: 'models.install', input_payload: { model_id: 'parakeet-tdt-0.6b-v3' } });
  });

  it('reports Apple Silicon as unified memory, not VRAM', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/voice/models') {
        return Response.json({ models: [parakeet], hub_token_source: 'missing', vram_target_gb: 24,
          hardware: { device: 'Apple Silicon (MPS)', vram_total_bytes: 22_548_578_304, vram_free_bytes: 17_179_869_184, unified_memory: true } });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    expect(await screen.findByText(/Apple Silicon \(MPS\) · 21.0 GB unified memory for the GPU, 16.0 GB free now/)).toBeInTheDocument();
  });

  it('groups the engine picker by what each engine is best at', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/tts/engines') {
        return Response.json({ selected: 'faster-qwen3-tts', switch: { provider: null, phase: 'idle', error: null, voices: { prepared: [], failed: [], already_ready: 0 } }, engines: [
          { id: 'faster-qwen3-tts', label: 'Faster Qwen3 TTS', description: '', selected: true, installed: true, unavailable_reason: '', needs_transcripts: false, voice_controls: [], delivery_instruction: false, group: 'clone' },
          { id: 'fish-s2-pro', label: 'Fish Audio S2 Pro', description: '', selected: false, installed: true, unavailable_reason: '', needs_transcripts: true, voice_controls: [], delivery_instruction: true, group: 'delivery' },
          { id: 'omnivoice', label: 'OmniVoice', description: '', selected: false, installed: false, unavailable_reason: 'not installed', needs_transcripts: true, voice_controls: [], delivery_instruction: false, group: 'many_languages' },
        ] });
      }
      if (path === '/api/jobs/voice-summaries') return Response.json({ jobs: [] });
      if (path === '/api/assets') return Response.json({ assets: [] });
      return new Response('not found', { status: 404 });
    }));
    renderVoice();
    const picker = await screen.findByLabelText('TTS engine');
    await waitFor(() => expect(picker.querySelectorAll('optgroup')).toHaveLength(3));
    expect([...picker.querySelectorAll('optgroup')].map((group) => group.getAttribute('label'))).toEqual(['Voice cloning', 'Expressive (delivery directions)', 'Many languages']);
    expect(within(picker).getByRole('option', { name: 'OmniVoice (not installed)' })).toBeDisabled();
  });
});
