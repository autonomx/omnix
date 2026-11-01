import { afterEach, describe, expect, it, vi } from 'vitest';
import { narrationBlocks, speakResponse, stopSpeaking } from './rpgVoices';

const sink = vi.hoisted(() => ({
  pushed: [] as number[][],
  ended: 0,
  stopped: 0,
  heard: null as (() => void) | null,
}));

vi.mock('./rpgSpeechSink', () => ({
  openPcmSink: async () => ({
    push: (samples: Int16Array) => { sink.pushed.push(Array.from(samples)); },
    end: () => new Promise<void>((resolve) => { sink.ended += 1; sink.heard = resolve; }),
    stop: () => { sink.stopped += 1; sink.heard?.(); },
  }),
}));

async function asked(input: RequestInfo | URL, init?: RequestInit): Promise<{ url: string; body: string }> {
  if (typeof input === 'object' && 'url' in input) return { url: input.url, body: await input.clone().text() };
  return { url: String(input), body: String(init?.body ?? '') };
}

function pcm(...samples: number[]): Uint8Array {
  return new Uint8Array(new Int16Array(samples).buffer);
}

describe('speakResponse', () => {
  afterEach(() => {
    stopSpeaking();
    vi.unstubAllGlobals();
    Object.assign(sink, { pushed: [], ended: 0, stopped: 0, heard: null });
  });

  it('streams each sentence into one sink as it arrives, asking for the next before the first is heard', async () => {
    const sentences: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = await asked(input, init);
      if (request.url.endsWith('/speech-plan')) {
        return new Response(JSON.stringify({ segments: [{ speaker_id: 'narrator', voice_id: 'default',
          sentences: ['The grove is quiet.', 'The wind rises.'] }] }), { status: 200 });
      }
      const text = JSON.parse(request.body).text as string;
      sentences.push(text);
      const bytes = text.startsWith('The grove') ? pcm(1, 2, 3) : pcm(4);
      // The first sentence arrives in two parts, split inside a sample.
      const parts = text.startsWith('The grove') ? [bytes.slice(0, 3), bytes.slice(3)] : [bytes];
      return new Response(new ReadableStream({ start(controller) {
        for (const part of parts) controller.enqueue(part);
        controller.close();
      } }), { status: 200, headers: { 'Content-Type': 'application/x-omnix-pcm16', 'X-Omnix-Sample-Rate': '24000' } });
    }));

    const outcome = speakResponse('campaign:test', [{ speakerId: 'narrator', text: 'The grove is quiet. The wind rises.' }]);
    await vi.waitFor(() => expect(sink.ended).toBe(1));
    expect(sentences).toEqual(['The grove is quiet.', 'The wind rises.']);  // both asked for; nothing heard to its end yet
    expect(sink.pushed.flat()).toEqual([1, 2, 3, 4]);
    sink.heard?.();
    expect(await outcome).toBe('played');
  });

  it('is silent when the service cannot speak a sentence, and lets the sink go', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if ((await asked(input, init)).url.endsWith('/speech-plan')) {
        return new Response(JSON.stringify({ segments: [{ speaker_id: 'narrator', voice_id: 'default',
          sentences: ['The grove is quiet.'] }] }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: { error: 'speech_unavailable' } }), { status: 503 });
    }));
    expect(await speakResponse('campaign:test', [{ speakerId: 'narrator', text: 'The grove is quiet.' }])).toBe('silent');
    expect(sink.stopped).toBe(1);
  });

  it('is silent when the service goes away, and a stop ends a stalled sentence and its request', async () => {
    const plan = () => new Response(JSON.stringify({ segments: [{ speaker_id: 'narrator', voice_id: 'default',
      sentences: ['The grove is quiet.'] }] }), { status: 200 });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if ((await asked(input, init)).url.endsWith('/speech-plan')) return plan();
      throw new TypeError('the service went away');
    }));
    expect(await speakResponse('campaign:test', [{ speakerId: 'narrator', text: 'The grove is quiet.' }])).toBe('silent');
    expect(sink.stopped).toBe(1);

    let aborted = false;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if ((await asked(input, init)).url.endsWith('/speech-plan')) return plan();
      const signal = (typeof input === 'object' && 'signal' in input ? input.signal : init?.signal) as AbortSignal;
      return new Response(new ReadableStream({ start(controller) {
        signal.addEventListener('abort', () => {
          aborted = true;
          controller.error(new DOMException('stopped', 'AbortError'));
        });
      } }), { status: 200 });
    }));
    const stoppedBefore = sink.stopped;
    const stalled = speakResponse('campaign:test', [{ speakerId: 'narrator', text: 'The grove is quiet.' }]);
    await vi.waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2));
    await new Promise((resolve) => { setTimeout(resolve, 0); });
    stopSpeaking();
    expect(await stalled).toBe('stopped');
    expect(aborted).toBe(true);
    expect(sink.stopped).toBeGreaterThan(stoppedBefore);
  });
});

describe('narrationBlocks', () => {
  it('speaks a quote inside narration in its speakers voice and the rest in the narrators', () => {
    const text = 'Liora leans close. "Stay near me." The wind rises.';
    const start = text.indexOf('"');
    expect(narrationBlocks(text, [{ speaker_id: 'npc:liora-fen', start, end: start + 15 }])).toEqual([
      { speakerId: 'narrator', text: 'Liora leans close. ' },
      { speakerId: 'npc:liora-fen', text: '"Stay near me."' },
      { speakerId: 'narrator', text: ' The wind rises.' },
    ]);
  });
});
