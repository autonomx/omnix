import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { PodcastWorkspace, finalRenderTiming, finalRenderWaitMs } from './PodcastWorkspace';
import { createTestQueryClient } from '../../test/renderWithProviders';

const GENERATED_AUDIO_DATA_URL = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=';
const STITCHED_AUDIO_BLOB_URL = 'blob:stitched-podcast-preview';

function renderPodcast() {
  const queryClient = createTestQueryClient();
  const module = omnixModules.find((entry) => entry.id === 'podcast');

  if (!module) {
    throw new Error('Podcast module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <PodcastWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const speech = vi.hoisted(() => ({ speakAsCharacters: vi.fn() }));
vi.mock('../assistant', async (importOriginal) => ({ ...(await importOriginal<typeof import('../assistant')>()), speakAsCharacters: speech.speakAsCharacters }));

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === 'string') return new URL(input, 'http://localhost').pathname;
  return new URL(input instanceof Request ? input.url : input.toString()).pathname;
}

function jobPosts(fetchMock: ReturnType<typeof vi.fn>, type: string) {
  return fetchMock.mock.calls.filter(
    ([input, init]) => typeof input === 'string' && requestPath(input) === '/api/jobs' && init?.method === 'POST' && requestBody(init).type === type,
  );
}

function requestBody(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(String(init?.body || '{}'));
}

/** A finished job for a POST to `/api/jobs`: the script job writes a line per speaker, every other job returns audio. */
/** A posted job as these tests read it. */
type JobBody = { type?: string; resource_class?: string; stages?: unknown[]; input_payload?: JobPayload };
type JobPayload = Record<string, unknown> & { speakers?: string[]; title?: string; speaker_profiles?: Array<{ name: string }>; duration_minutes?: number };

function finishedJob(body: JobBody, script?: Record<string, unknown>) {
  const speakers: string[] = body.input_payload?.speakers ?? [];
  const outputRefs = body.type === 'podcast.generate'
    ? [{ type: 'podcast_script', title: body.input_payload?.title, content: JSON.stringify({ segments: speakers.map((speaker, index) => ({ speaker, text: `Point ${index + 1}, from ${speaker}.` })) }) }]
    : [{ type: 'audio', asset_id: 'audio:podcast-job', title: 'Generated podcast audio', data_url: GENERATED_AUDIO_DATA_URL, duration: 2, mime_type: 'audio/wav' }];
  return Response.json({
    id: body.type === 'podcast.generate' ? 'job:script' : 'job:podcast',
    module: 'podcast',
    type: body.type,
    status: 'completed',
    resource_class: body.resource_class,
    input_payload: body.input_payload,
    stages: body.stages ?? [],
    output_refs: outputRefs,
    created_at: '2026-06-14T00:00:01Z',
    updated_at: '2026-06-14T00:00:01Z',
    priority: 0,
    ...(body.type === 'podcast.generate' ? script : {}),
  });
}

function responseFromDataUrl(value: string): Response {
  const [, metadata = '', payload = ''] = value.match(/^data:([^,]*),(.*)$/) ?? [];
  const isBase64 = metadata.includes(';base64');
  const binary = isBase64 ? atob(payload) : decodeURIComponent(payload);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  const mimeType = metadata.split(';')[0] || 'application/octet-stream';
  return new Response(bytes, { headers: { 'Content-Type': mimeType } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('PodcastWorkspace', () => {
  it('lists finished podcasts in the library and plays one with its transcript', async () => {
    const finalJob = {
      id: 'job:final-1', module: 'podcast', type: 'tts.multi_speaker_synthesize', status: 'completed', resource_class: 'gpu:tts',
      input_payload: { title: 'Signals at Night', format: 'debate', script_speakers: [{ name: 'Ada', count: 1 }, { name: 'Ben', count: 1 }] },
      stages: [], output_refs: [{ type: 'audio', asset_id: 'audio:voice-studio-job_final-1', title: 'Signals at Night', audio_url: '/api/assets/audio:voice-studio-job_final-1/file', duration: 754, mime_type: 'audio/wav' }],
      created_at: '2026-11-24T09:07:00Z', updated_at: '2026-11-24T09:07:00Z', priority: 0,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/voice-library') return Response.json({ assets: [] });
      if (path === '/api/jobs') {
        const query = new URL(String(input), 'http://localhost').searchParams;
        return Response.json({ jobs: query.get('type') === 'tts.multi_speaker_synthesize' ? [finalJob] : [], has_more: false, next_cursor: null });
      }
      if (decodeURIComponent(path) === '/api/jobs/job:final-1') {
        return Response.json({ ...finalJob, input_payload: { ...finalJob.input_payload, script_segments: [{ index: 0, speaker: 'Ada', text: 'Welcome to the night shift.' }, { index: 1, speaker: 'Ben', text: 'Glad to be here.' }] } });
      }
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderPodcast();

    const library = await screen.findByRole('article', { name: 'Podcast library' });
    expect(await screen.findByText('Signals at Night')).toBeInTheDocument();
    expect(library).toHaveTextContent('Debate - 2 voices - 12:34');
    expect(library).toHaveTextContent('Ada, Ben');
    const listed = fetchMock.mock.calls.map(([input]) => new URL(String(input), 'http://localhost')).find((url) => url.pathname === '/api/jobs' && url.searchParams.get('type'));
    expect(Object.fromEntries(listed?.searchParams ?? [])).toMatchObject({ module: 'podcast', type: 'tts.multi_speaker_synthesize', status: 'completed' });

    fireEvent.click(screen.getByRole('button', { name: 'Play Signals at Night' }));
    expect(await screen.findByText('Welcome to the night shift.')).toBeInTheDocument();
    expect(screen.getByText('Glad to be here.')).toBeInTheDocument();
    const audio = document.querySelector('.podcast-audio-player audio') as HTMLAudioElement;
    await waitFor(() => expect(audio.getAttribute('src')).toBe('/api/assets/audio:voice-studio-job_final-1/file'));
    expect(screen.getByRole('button', { name: 'Play Signals at Night' })).toHaveTextContent('Playing');
  });

  it('says so when there are no finished podcasts yet', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/voice-library') return Response.json({ assets: [] });
      if (path === '/api/jobs') return Response.json({ jobs: [], has_more: false, next_cursor: null });
      return new Response('not found', { status: 404 });
    }));
    renderPodcast();
    expect(await screen.findByText('No finished podcasts yet. Each final render is kept here.')).toBeInTheDocument();
  });

  it('opens a speaker field in a large box on double-click, and edits the cell as you type', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/voice-library') return Response.json({ assets: [] });
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    }));
    renderPodcast();
    const cell = await screen.findByLabelText('Speaker 1 beliefs') as HTMLTextAreaElement;
    fireEvent.doubleClick(cell);

    const big = await screen.findByLabelText(/beliefs \(expanded\)/) as HTMLTextAreaElement;
    expect(big.value).toBe(cell.value);
    fireEvent.change(big, { target: { value: 'Three years old. Loves her mama.' } });
    expect((screen.getByLabelText('Speaker 1 beliefs') as HTMLTextAreaElement).value).toBe('Three years old. Loves her mama.');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByLabelText(/beliefs \(expanded\)/)).not.toBeInTheDocument());

    fireEvent.doubleClick(screen.getByLabelText('Speaker 2 identity'));
    expect(await screen.findByLabelText(/identity \(expanded\)/)).toBeInTheDocument();
  });

  it('pauses, resumes and stops a run: Stop cancels the job in flight and starts nothing after it', async () => {
    const cancelled: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = decodeURIComponent(requestPath(input));
      if (path === '/api/voice-library') return Response.json({ assets: [] });
      if (path === '/api/jobs/job:script/cancel') {
        cancelled.push(String(requestBody(init).reason));
        return Response.json({ id: 'job:script', module: 'podcast', type: 'podcast.generate', status: 'cancel_requested' });
      }
      const running = { id: 'job:script', module: 'podcast', type: 'podcast.generate', status: 'running', output_refs: [], created_at: '2026-11-24T00:00:00Z', updated_at: '2026-11-24T00:00:00Z' };
      if (path === '/api/jobs' && init?.method === 'POST') return Response.json(running);
      if (path === '/api/jobs/job:script') return Response.json(running);
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPodcast();
    fireEvent.change(await screen.findByLabelText(/Episode brief/), { target: { value: 'Local AI at home.' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));

    fireEvent.click(await screen.findByRole('button', { name: 'Pause' }));
    expect(await screen.findByRole('button', { name: 'Resume' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

    expect((await screen.findAllByText('Podcast stopped.')).length).toBeGreaterThan(0);
    expect(cancelled).toEqual(['Stopped by the producer.']);
    expect(jobPosts(fetchMock, 'tts.synthesize')).toHaveLength(0);
    expect(jobPosts(fetchMock, 'tts.multi_speaker_synthesize')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Generate live podcast/i })).toBeEnabled();
  });

  it('adds web research to the source notes, after the producer\'s own, and says when there is nothing', async () => {
    const research: Record<string, unknown>[] = [];
    const replies = [
      { status: 'ok', message: 'Added notes from 1 web source. Check them before you generate.', query: 'Signals', notes: 'Web research, 1 sources (check before use):\n\n- GPU prices (https://example.org)\n  A 4090 sells for $1,600.', sources: [{ title: 'GPU prices', url: 'https://example.org' }], provider: 'brave' },
      { status: 'empty', message: 'The web search found nothing on this topic.', query: 'Signals', notes: '', sources: [], provider: 'brave' },
    ];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/podcast/research' && init?.method === 'POST') {
        research.push(requestBody(init));
        return Response.json(replies[research.length - 1]);
      }
      if (path === '/api/voice-library') return Response.json({ assets: [] });
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    }));

    renderPodcast();
    fireEvent.click(await screen.findByRole('button', { name: 'New podcast' }));
    const button = screen.getByRole('button', { name: 'Research the topic' });
    expect(button).toBeDisabled(); // nothing to search for yet

    fireEvent.change(screen.getByLabelText('Topic / Episode title'), { target: { value: ' Signals ' } });
    fireEvent.change(screen.getByLabelText(/Source notes/), { target: { value: 'My own note.' } });
    fireEvent.click(button);

    expect(await screen.findByText('Added notes from 1 web source. Check them before you generate.')).toBeInTheDocument();
    expect(research[0]).toEqual({ title: 'Signals', brief: '' });
    const notes = screen.getByLabelText(/Source notes/) as HTMLTextAreaElement;
    expect(notes.value).toBe('My own note.\n\nWeb research, 1 sources (check before use):\n\n- GPU prices (https://example.org)\n  A 4090 sells for $1,600.');

    fireEvent.click(screen.getByRole('button', { name: 'Research the topic' }));
    expect(await screen.findByText('The web search found nothing on this topic.')).toBeInTheDocument();
    expect(notes.value.startsWith('My own note.\n\nWeb research')).toBe(true); // nothing found, nothing changed
  });

  it('queues podcast voice generation through the Voice Studio TTS path and exposes playback audio', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue(STITCHED_AUDIO_BLOB_URL);
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (typeof input === 'string' && input.startsWith('data:audio/')) {
        return responseFromDataUrl(input);
      }

      const path = requestPath(input);

      // The voice library: every clone on disk, Ehsan's included though it has no stored asset (2026-11-23).
      if (path === '/api/voice-library') {
        return Response.json({
          assets: [
            {
              id: 'voice-cloning:alex',
              module: 'voice-cloning',
              type: 'voice_profile',
              mime_type: 'audio/wav',
              file_name: 'alex.wav',
              metadata: { profile_name: 'Alex Voice' },
              created_at: '2026-06-14T00:00:00Z',
            },
            {
              id: 'voice-cloning:ehsan',
              module: 'voice-cloning',
              type: 'voice_profile',
              mime_type: 'audio/mpeg',
              file_name: 'Ehsan.mp3',
              metadata: { profile_name: 'Ehsan', voice_clone_id: 'Ehsan' },
              created_at: '2026-06-14T00:00:00Z',
            },
          ],
        });
      }

      if (path === '/api/jobs' && init?.method === 'POST') return finishedJob(JSON.parse(String(init.body)));

      if (path === '/api/jobs') {
        return Response.json({ jobs: [] });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPodcast();

    expect(await screen.findByRole('heading', { name: '1. Episode setup' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /New podcast/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole('option', { name: '2 min' })).toBeInTheDocument();
    expect((await screen.findAllByText('Alex Voice')).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('option', { name: 'Ehsan' }).length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls.some(([input]) => requestPath(input as RequestInfo | URL) === '/api/assets')).toBe(false);
    expect(screen.getByRole('heading', { name: '2. Participants and voice casting' })).toBeInTheDocument();
    expect(screen.getByText('Voice')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Topic / Episode title'), { target: { value: 'Signals' } });
    fireEvent.change(screen.getByLabelText(/Episode brief/), { target: { value: 'Discuss local AI workstation design.' } });
    fireEvent.change(screen.getByLabelText(/Source notes/), { target: { value: 'A 4090 has 24 GB of VRAM.' } });
    expect(screen.getByLabelText(/Intro and outro sting/)).not.toBeChecked();
    expect(screen.getByLabelText(/Room tone/)).not.toBeChecked();
    fireEvent.click(screen.getByLabelText(/Intro and outro sting/));
    fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));

    expect((await screen.findAllByText('Podcast audio ready: job:podcast')).length).toBeGreaterThan(0);
    // The producer's notes go to the script; the sting, asked for, goes to the final render (room tone was not).
    expect(requestBody(jobPosts(fetchMock, 'podcast.generate')[0][1])).toMatchObject({ input_payload: { sources: 'A 4090 has 24 GB of VRAM.' } });
    const render = requestBody(jobPosts(fetchMock, 'tts.multi_speaker_synthesize')[0][1]) as JobBody & { input_payload: Required<JobPayload> };
    expect(render.input_payload.bookends).toBe(true);
    expect(render.input_payload).not.toHaveProperty('room_tone');
    expect((await screen.findAllByText(/Live preview stitched|Stitched live preview/i)).length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Podcast audio player').querySelectorAll('audio')).toHaveLength(1);
    await waitFor(() => expect(screen.getByLabelText('Podcast audio player').querySelector('audio')?.getAttribute('src')).toBe(STITCHED_AUDIO_BLOB_URL));

    await waitFor(() => {
      const previewCall = fetchMock.mock.calls.find(
        ([input, init]) => typeof input === 'string'
          && requestPath(input as RequestInfo | URL) === '/api/jobs'
          && init?.method === 'POST'
          && requestBody(init).type === 'tts.synthesize',
      );
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => typeof input === 'string'
          && requestPath(input as RequestInfo | URL) === '/api/jobs'
          && init?.method === 'POST'
          && requestBody(init).type === 'tts.multi_speaker_synthesize',
      );
      expect(previewCall?.[1]?.body).toContain('"renderer":"podcast-live-preview"');
      expect(previewCall?.[1]?.body).toContain('"voice_mapping"');
      expect(createCall?.[1]?.body).toContain('"module":"podcast"');
      expect(createCall?.[1]?.body).toContain('"type":"tts.multi_speaker_synthesize"');
      expect(createCall?.[1]?.body).toContain('"resource_class":"gpu:tts"');
      expect(createCall?.[1]?.body).toContain('"script_segments"');
      expect(createCall?.[1]?.body).toContain('"character_voice_assignments"');
      expect(createCall?.[1]?.body).toContain('"voice_id":"voice-cloning:alex"');
      expect(createCall?.[1]?.body).toContain('"voice_mapping"');
      expect(createCall?.[1]?.body).toContain('"speakerInstructions"');
      expect(createCall?.[1]?.body).toContain('"maxSpeakerTurnSeconds":45');
    });
    // The script is the model's, written in a durable job from the episode and the cast (owner report 2026-11-24).
    const scriptPosts = jobPosts(fetchMock, 'podcast.generate');
    expect(scriptPosts).toHaveLength(1);
    const script = requestBody(scriptPosts[0][1]) as JobBody & { input_payload: Required<JobPayload> };
    expect(script).toMatchObject({ module: 'podcast', resource_class: 'gpu:llm', input_payload: { title: 'Signals', brief: 'Discuss local AI workstation design.' } });
    expect(script.input_payload.duration_minutes).toBeGreaterThan(0);
    expect(script.input_payload.speaker_profiles.map((profile: { name: string }) => profile.name)).toEqual(script.input_payload.speakers);
    expect(screen.getAllByText(`Point 1, from ${script.input_payload.speakers[0]}.`).length).toBeGreaterThan(0);
  });

  it('waits out a long final render, showing which line it is on (owner report 2026-11-24)', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue(STITCHED_AUDIO_BLOB_URL);
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    finalRenderTiming.pollMs = 1;
    let rendered = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (typeof input === 'string' && input.startsWith('data:audio/')) return responseFromDataUrl(input);
      const path = requestPath(input);
      if (path === '/api/voice-library') {
        return Response.json({ assets: [{ id: 'voice-cloning:alex', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'alex.wav', metadata: { profile_name: 'Alex Voice' }, created_at: '2026-06-14T00:00:00Z' }] });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body));
        // The final render is still speaking its lines when it is created.
        return body.type === 'tts.multi_speaker_synthesize'
          ? Response.json({ ...(await finishedJob(body).json()), status: 'running', output_refs: [] })
          : finishedJob(body);
      }
      if (path === '/api/jobs/job%3Apodcast') {
        const job = await finishedJob({ type: 'tts.multi_speaker_synthesize', resource_class: 'gpu:tts', input_payload: {} }).json();
        return Response.json(rendered ? job : { ...job, status: 'running', output_refs: [], progress: { current: 1, total: 3, message: 'Line 2 of 3' } });
      }
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      renderPodcast();
      expect((await screen.findAllByText('Alex Voice')).length).toBeGreaterThan(0);
      fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));

      expect((await screen.findAllByText('Rendering the final podcast audio: line 2 of 3...')).length).toBeGreaterThan(0);
      // The bar covers the whole run: script and preview are done (55%), and one of the render's three steps (15%).
      const bar = screen.getByRole('progressbar', { name: 'Podcast progress' });
      expect(bar).toHaveAttribute('value', '70');
      expect(screen.getByText('Final render: Line 2 of 3')).toBeInTheDocument();
      expect(screen.getByText('70%')).toBeInTheDocument();
      expect(document.querySelector('.stage-rail .active')).toHaveTextContent('Mix');
      rendered = true;
      expect((await screen.findAllByText('Podcast audio ready: job:podcast')).length).toBeGreaterThan(0);
      expect(screen.queryByRole('progressbar', { name: 'Podcast progress' })).not.toBeInTheDocument();
    } finally {
      finalRenderTiming.pollMs = 1250;
    }
    // The wait grows with the script: a minute a line, and never less than fifteen minutes.
    expect(finalRenderWaitMs(3)).toBe(15 * 60000);
    expect(finalRenderWaitMs(120)).toBe(120 * 60000);
  });

  it('keeps the preview lines as takes for the final render, and highlights the line being heard (owner request 2026-11-24)', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue(STITCHED_AUDIO_BLOB_URL);
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (typeof input === 'string' && input.startsWith('data:audio/')) return responseFromDataUrl(input);
      const path = requestPath(input);
      if (path === '/api/voice-library') {
        return Response.json({ assets: [{ id: 'voice-cloning:alex', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'alex.wav', metadata: { profile_name: 'Alex Voice' }, created_at: '2026-06-14T00:00:00Z' }] });
      }
      // The run's script, saved for its takes: one line per "speaker: text" row.
      if (path === '/api/voice/scripts' && init?.method === 'POST') {
        const { text } = JSON.parse(String(init.body)) as { text: string };
        const lines = text.split('\n').map((row, position) => ({ id: `line-${position}`, position, speaker: row.slice(0, row.indexOf(':')), text: row.slice(row.indexOf(':') + 1).trim(), takes: [] }));
        return Response.json({ id: 'script:run', title: 'Signals (podcast)', revision: 1, lines });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        const body = JSON.parse(String(init.body));
        if (body.type !== 'tts.multi_speaker_synthesize') return finishedJob(body);
        const job = await finishedJob(body).json();
        // The render reports where each line starts, after a 1.5 s opening sting.
        job.output_refs[0].timeline = [{ segment: 0, start: 1.5, end: 4 }, { segment: 1, start: 4, end: 7 }];
        return Response.json(job);
      }
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
    renderPodcast();
    expect((await screen.findAllByText('Alex Voice')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));
    expect((await screen.findAllByText('Podcast audio ready: job:podcast')).length).toBeGreaterThan(0);

    // Each preview line is spoken under its saved line; the final render asks for none again, so it reuses them all.
    const previews = jobPosts(fetchMock, 'tts.synthesize').map(([, init]) => requestBody(init).input_payload as JobPayload);
    expect(previews.length).toBeGreaterThan(1);
    previews.forEach((payload, position) => expect(payload).toMatchObject({ script_id: 'script:run', script_segments: [{ line_id: `line-${position}` }] }));
    const final = requestBody(jobPosts(fetchMock, 'tts.multi_speaker_synthesize')[0][1]).input_payload as JobPayload;
    expect(final).toMatchObject({ script_id: 'script:run', render_line_ids: [], script_segments: previews.map((_, position) => ({ line_id: `line-${position}` })) });

    // The stitched preview ends and the final render takes the player; the transcript follows it: nothing during the
    // sting, then the line being heard.
    // (The player mounts a new audio element for each output.)
    const player = () => screen.getByLabelText('Podcast audio player').querySelector('audio') as HTMLAudioElement;
    await waitFor(() => {
      fireEvent.ended(player());
      expect(player().getAttribute('src')).toBe(GENERATED_AUDIO_DATA_URL);
    });
    const audio = player();
    const at = (seconds: number) => {
      Object.defineProperty(audio, 'currentTime', { configurable: true, value: seconds });
      fireEvent.timeUpdate(audio);
      return document.querySelector('.live-transcript p.active');
    };
    expect(at(0.5)).toBeNull();
    expect(at(2)).toHaveTextContent(`Point 1, from ${previews[0].speaker}.`);
    expect(at(5)).toHaveTextContent(`Point 2, from ${previews[1].speaker}.`);
    expect(at(5)).toHaveAttribute('aria-current', 'true');
  });

  it('says why the script could not be written, and voices no stand-in script', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/voice-library') {
        return Response.json({ assets: [{ id: 'voice-cloning:alex', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'alex.wav', metadata: { profile_name: 'Alex Voice' }, created_at: '2026-06-14T00:00:00Z' }] });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        return finishedJob(JSON.parse(String(init.body)), { status: 'failed', output_refs: [], error: { code: 'story_job_failed', message: 'LLM response was empty' } });
      }
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPodcast();
    expect((await screen.findAllByText('Alex Voice')).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));

    expect((await screen.findAllByText('The podcast script could not be written: LLM response was empty')).length).toBeGreaterThan(0);
    expect(jobPosts(fetchMock, 'podcast.generate')).toHaveLength(1);
    expect(jobPosts(fetchMock, 'tts.synthesize')).toHaveLength(0);
    expect(jobPosts(fetchMock, 'tts.multi_speaker_synthesize')).toHaveLength(0);
  });

  it('casts a library character as a speaker and, with live avatars on, has the cast speak the preview live (D4)', async () => {
    speech.speakAsCharacters.mockImplementation(() => ({ done: Promise.resolve(), stop: vi.fn() }));
    const portraitLoads: unknown[] = [];
    const assetTypes: (string | null)[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (typeof input === 'string' && input.startsWith('data:audio/')) return responseFromDataUrl(input);
      const path = requestPath(input);
      // An older gateway without the voice library: the stored voice profiles are listed instead.
      if (path === '/api/assets') {
        assetTypes.push(new URL(input instanceof Request ? input.url : String(input), 'http://localhost').searchParams.get('type'));
        return Response.json({ assets: [{ id: 'voice-cloning:alex', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'alex.wav', metadata: { profile_name: 'Alex Voice' }, created_at: '2026-06-14T00:00:00Z' }] });
      }
      if (path === '/api/characters') {
        return Response.json({ characters: [{ id: 'char:maya', display_name: 'Maya', description: 'A field biologist.', personality_prompt: 'Warm and curious.', default_voice_asset_id: 'voice-cloning:alex', enabled: true }] });
      }
      if (path === '/api/characters/char%3Amaya/avatar-pack' || path === '/api/characters/char:maya/avatar-pack') {
        return Response.json({ character_id: 'char:maya', renderer: 'portrait', base_asset_id: 'image:maya' });
      }
      if (path === '/api/jobs' && init?.method === 'POST') return finishedJob(JSON.parse(String(init.body)));
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      if (path === '/api/tts/live-call/portrait-load') {
        const method = input instanceof Request ? input.method : init?.method ?? 'GET';
        if (method !== 'POST') return Response.json({ status: 'ready' });
        portraitLoads.push(input instanceof Request ? await input.clone().json() : JSON.parse(String(init?.body)));
        return Response.json({ status: 'ready', code: '', message: '' });
      }
      if (path === '/api/tts/live-call/portrait-idle') return Response.json({ ok: true, frame_ms: 80, idle: [btoa('a')], blink: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPodcast();

    const casting = await screen.findByLabelText('Speaker 1 character');
    await screen.findAllByRole('option', { name: 'Maya (live portrait)' }); // offered to every speaker
    await waitFor(() => expect(assetTypes).toEqual(['voice_profile']));
    fireEvent.change(casting, { target: { value: 'char:maya' } });
    expect(screen.getAllByDisplayValue('Maya').length).toBeGreaterThan(0); // the character's name fills the speaker
    fireEvent.click(screen.getByLabelText(/Live avatars/));
    expect(screen.getByRole('group', { name: 'Live avatars' })).toBeInTheDocument();
    // The cast's faces load before generation, as a call's "Load live video" does (owner request 2026-11-23).
    fireEvent.click(await screen.findByRole('button', { name: 'Load live avatars' }));
    expect(await screen.findByRole('button', { name: 'Live avatars ready' })).toBeInTheDocument();
    expect(portraitLoads).toEqual([{ asset_id: 'image:maya' }]);

    fireEvent.change(screen.getByLabelText('Topic / Episode title'), { target: { value: 'Signals' } });
    fireEvent.change(screen.getByLabelText(/Episode brief/), { target: { value: 'Discuss field work.' } });
    fireEvent.click(screen.getByRole('button', { name: /Generate live podcast/i }));

    expect((await screen.findAllByText('Podcast audio ready: job:podcast')).length).toBeGreaterThan(0);
    expect(speech.speakAsCharacters).toHaveBeenCalledTimes(1);
    const [runKey, lines] = speech.speakAsCharacters.mock.calls[0];
    // The run speaks under the stage's key, which kept the loops the load fetched.
    expect(runKey).toMatch(/^podcast-stage:/);
    const mayaLines = lines.filter((line: { speaker: { id: string } | null }) => line.speaker?.id === 'char:maya');
    expect(mayaLines.length).toBeGreaterThan(0);
    expect(mayaLines[0]).toMatchObject({ voiceId: 'alex', speaker: { pack: { renderer: 'portrait' } } }); // the clone's speaker id
    expect(jobPosts(fetchMock, 'tts.synthesize')).toHaveLength(0); // no per-line preview jobs
    expect(jobPosts(fetchMock, 'tts.multi_speaker_synthesize')).toHaveLength(1); // the final render is unchanged
    // Nothing was stitched, so the final render takes the player rather than it waiting for a segment (2026-11-23).
    const player = screen.getByLabelText('Podcast audio player');
    await waitFor(() => expect(player.querySelector('audio')?.getAttribute('src')).toBeTruthy());
    expect(player).toHaveTextContent('Generated podcast audio');
    expect(player).not.toHaveTextContent(/Waiting for first stitched/);
    expect(player).toHaveTextContent('AUDIO READY');
  });
});
