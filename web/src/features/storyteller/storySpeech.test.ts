import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readStoryPage, setStoryAutoplay, storyAutoplay, withPronunciation } from './storySpeech';

type FakeSink = { line: number; pushed: number[]; ended: boolean; stopped: boolean; paused: boolean };
const sinks: FakeSink[] = [];
let sinkAvailable = true;

vi.mock('../assistant', () => ({
  openPcmSink: async () => {
    if (!sinkAvailable) return null;
    const sink: FakeSink = { line: sinks.length, pushed: [], ended: false, stopped: false, paused: false };
    sinks.push(sink);
    return {
      push: (samples: Int16Array) => { sink.pushed.push(...Array.from(samples)); },
      end: async () => { sink.ended = true; },
      pause: () => { sink.paused = true; },
      resume: () => { sink.paused = false; },
      stop: () => { sink.stopped = true; },
    };
  },
}));

const PLAN = {
  project_id: 'p1',
  page_id: 'page-1',
  segments: [
    { block_index: 0, speaker_id: 'narrator', voice_id: 'v-warm', sentences: ['Dusk fell over Aldmere.'], unknown_speaker: false },
    { block_index: 2, speaker_id: 'mara', voice_id: 'v-gravel', sentences: ['“Who goes there?”', '“Speak.”'], unknown_speaker: false },
  ],
};

type Asked = { path: string; body: Record<string, unknown> };

async function asked(input: RequestInfo | URL, init?: RequestInit): Promise<Asked> {
  const request = input instanceof Request ? input : null;
  const url = new URL(request ? request.url : String(input), 'http://localhost');
  const body = request ? await request.clone().text() : String(init?.body ?? '');
  return { path: url.pathname, body: body ? JSON.parse(body) as Record<string, unknown> : {} };
}

/** A sentence's audio: two samples per sentence, the first chunk split mid-sample. */
function pcm(first: number, held?: Promise<void>): Response {
  const bytes = new Uint8Array(new Int16Array([first, first + 1]).buffer);
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(bytes.slice(0, 3));
      if (held) await held;
      controller.enqueue(bytes.slice(3));
      controller.close();
    },
  });
  return new Response(stream, { headers: { 'Content-Type': 'application/x-omnix-pcm16', 'X-Omnix-Sample-Rate': '24000' } });
}

function speechServer({ down = false, hold = null as Promise<void> | null } = {}) {
  const sentences: Asked['body'][] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const { path, body } = await asked(input, init);
    if (path.endsWith('/speech-plan')) return Response.json(PLAN);
    if (path.endsWith('/speech-audio')) {
      sentences.push(body);
      if (down) return Response.json({ detail: { ok: false, error: 'speech_unavailable' } }, { status: 503 });
      return pcm(sentences.length * 10, sentences.length === 1 ? hold ?? undefined : undefined);
    }
    return new Response('not found', { status: 404 });
  }));
  return sentences;
}

beforeEach(() => {
  sinks.length = 0;
  sinkAvailable = true;
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('storySpeech', () => {
  it('says a noted word as its note, whole words only, in any case', () => {
    const notes = { Aldmere: 'ALD-meer', Ro: 'Row' };
    expect(withPronunciation('Dusk fell over aldmere. Ro rowed, Rory too.', notes)).toBe('Dusk fell over ALD-meer. Row rowed, Rory too.');
    expect(withPronunciation('No notes.', { '': 'x', word: ' ' })).toBe('No notes.');
  });

  it('reads a page line by line, each line through its own sink, with the word notes applied', async () => {
    const sentences = speechServer();
    const heard: Array<number | null> = [];
    const reader = readStoryPage('p1', 'page-1', { pauseMs: 0, pronunciation: { Aldmere: 'ALD-meer' }, onLine: (line) => heard.push(line) });
    await expect(reader.outcome).resolves.toBe('played');
    expect(heard).toEqual([0, 1, null]);
    expect(sentences).toEqual([
      { page_id: 'page-1', speaker_id: 'narrator', text: 'Dusk fell over ALD-meer.' },
      { page_id: 'page-1', speaker_id: 'mara', text: '“Who goes there?”' },
      { page_id: 'page-1', speaker_id: 'mara', text: '“Speak.”' },
    ]);
    // A sample split across chunks is joined; the second line holds both its sentences.
    expect(sinks.map((sink) => [sink.pushed, sink.ended])).toEqual([[[10, 11], true], [[20, 21, 30, 31], true]]);
  });

  it('is silent with the speech service down, and with no audio device', async () => {
    speechServer({ down: true });
    await expect(readStoryPage('p1', 'page-1', { pauseMs: 0, pronunciation: {}, onLine: () => undefined }).outcome).resolves.toBe('silent');
    expect(sinks[0].stopped).toBe(true);
    sinkAvailable = false;
    speechServer();
    await expect(readStoryPage('p1', 'page-1', { pauseMs: 0, pronunciation: {}, onLine: () => undefined }).outcome).resolves.toBe('silent');
  });

  it('skips the line being heard and goes on with the next', async () => {
    let release = () => undefined as void;
    const sentences = speechServer({ hold: new Promise<void>((resolve) => { release = resolve; }) });
    const lines: Array<number | null> = [];
    const reader = readStoryPage('p1', 'page-1', { pauseMs: 0, pronunciation: {}, onLine: (line) => lines.push(line) });
    await vi.waitFor(() => expect(lines).toEqual([0]));
    reader.skip();
    await expect(reader.outcome).resolves.toBe('played');
    release();
    expect(lines).toEqual([0, 1, null]);
    expect(sinks[0].stopped).toBe(true);
    expect(sinks[1].ended).toBe(true);
    expect(sentences.map((sentence) => sentence.speaker_id)).toEqual(['narrator', 'mara', 'mara']);
  });

  it('pauses and resumes the line being heard, and stops for good', async () => {
    let release = () => undefined as void;
    speechServer({ hold: new Promise<void>((resolve) => { release = resolve; }) });
    const reader = readStoryPage('p1', 'page-1', { pauseMs: 0, pronunciation: {}, onLine: () => undefined });
    await vi.waitFor(() => expect(sinks).toHaveLength(1));
    reader.pause();
    expect(sinks[0].paused).toBe(true);
    reader.resume();
    expect(sinks[0].paused).toBe(false);
    reader.stop();
    release();
    await expect(reader.outcome).resolves.toBe('stopped');
    expect(sinks).toHaveLength(1);
    expect(sinks[0].stopped).toBe(true);
  });

  it('keeps "read new pages aloud" off until it is turned on', () => {
    expect(storyAutoplay()).toBe(false);
    setStoryAutoplay(true);
    expect(storyAutoplay()).toBe(true);
    setStoryAutoplay(false);
    expect(storyAutoplay()).toBe(false);
  });
});
