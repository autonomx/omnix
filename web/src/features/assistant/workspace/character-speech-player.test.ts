import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  sessions: [] as Array<{
    voiceId: string | null;
    options: Record<string, unknown>;
    phrases: Array<{ text: string; index: number; ownership: { outputId: string; generationEpoch: number; outputOrder: number } }>;
    ends: Array<[string, number]>;
    waits: Array<() => void>;
    stopped: boolean;
  }>,
  portrait: {
    wantedForCharacter: vi.fn((speaker: { pack?: { renderer?: string } | null }) => speaker.pack?.renderer === 'portrait'),
    beginForCharacter: vi.fn(() => ({ onHello: vi.fn(), onWorkletEvent: vi.fn(), onSegmentRate: vi.fn() })),
    attachSession: vi.fn(),
    end: vi.fn(),
  },
}));

vi.mock('../chat/portrait/livePortrait', () => ({ livePortrait: mocks.portrait }));
vi.mock('./live-call-diagnostics-client', () => ({
  createLiveCallTraceId: (key: string) => `trace:${key}`,
  createLiveCallDiagnosticsReporter: () => ({ record: vi.fn(), close: vi.fn(async () => undefined) }),
}));
vi.mock('./live-voice-pcm-session', () => ({
  createLiveVoicePcmSession: vi.fn(async (_trace: string, voiceId: string | null, _reporter: unknown, options: Record<string, unknown>) => {
    const state = { voiceId, options, phrases: [], ends: [], waits: [], stopped: false } as (typeof mocks.sessions)[number];
    mocks.sessions.push(state);
    return {
      enqueueOutputPhrase: vi.fn(async (text: string, index: number, ownership: (typeof state.phrases)[number]['ownership']) => {
        state.phrases.push({ text, index, ownership });
      }),
      sendOutputEnd: vi.fn((outputId: string, epoch: number) => { state.ends.push([outputId, epoch]); }),
      waitForOutputItem: vi.fn(() => new Promise<void>((resolve) => { state.waits.push(resolve); })),
      isClosed: () => state.stopped,
      hasFailed: () => false,
      stop: vi.fn(async () => {
        state.stopped = true;
        state.waits.splice(0).forEach((resolve) => resolve()); // a stop settles what waits on it
      }),
    };
  }),
}));

import { linePhrases, speakAsCharacters } from './character-speech-player';

const MAYA = { id: 'char:maya', pack: { renderer: 'portrait', base_asset_id: 'image:maya' } };
const BEA = { id: 'char:bea', pack: { renderer: 'sprite' } };

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

/** Every output queued so far has been heard. */
async function hearAll(): Promise<void> {
  await settle();
  for (const session of mocks.sessions) session.waits.splice(0).forEach((resolve) => resolve());
  await settle();
}

afterEach(() => {
  mocks.sessions.length = 0;
  vi.clearAllMocks();
});

describe('lines spoken as characters (D4)', () => {
  it('splits a line into sentences, and a long one at a comma or a space', () => {
    expect(linePhrases('  Hello there.  How are you?\nFine! ')).toEqual(['Hello there.', 'How are you?', 'Fine!']);
    const long = `${'word '.repeat(60)}end`;
    const phrases = linePhrases(long);
    expect(phrases.length).toBeGreaterThan(1);
    expect(phrases.every((phrase) => phrase.length <= 220)).toBe(true);
    expect(phrases.join(' ')).toBe(long);
  });

  it("gives each speaker its own session with its voice and face, one output a phrase, each line's last one ended", async () => {
    const heard: string[] = [];
    const run = speakAsCharacters('podcast:1', [
      { text: 'Welcome. Today we talk.', voiceId: 'Maya', speaker: MAYA },
      { text: 'More from me.', voiceId: 'Maya', speaker: MAYA },
      { text: 'Thanks for having me.', voiceId: 'Bea', speaker: BEA },
    ], (index, line) => heard.push(`${index}:${line.speaker?.id}`));

    await hearAll();
    await hearAll();
    await hearAll();
    await run.done;

    expect(heard).toEqual(['0:char:maya', '1:char:maya', '2:char:bea']);
    expect(mocks.sessions.map((session) => session.voiceId)).toEqual(['Maya', 'Bea']); // the same speaker keeps its session
    const [maya, bea] = mocks.sessions;
    expect(maya.options).toMatchObject({ sessionScoped: true, affinityKey: 'podcast:1' });
    expect(maya.options.portrait).toBeDefined();
    expect(bea.options.portrait).toBeUndefined(); // a sprite has no live portrait
    expect(mocks.portrait.beginForCharacter).toHaveBeenCalledTimes(1);
    expect(mocks.portrait.beginForCharacter).toHaveBeenCalledWith('podcast:1', MAYA);
    expect(maya.phrases.map((phrase) => [phrase.text, phrase.index, phrase.ownership])).toEqual([
      ['Welcome.', 0, { outputId: 'line-0-0', generationEpoch: 1, outputOrder: 0 }],
      ['Today we talk.', 1, { outputId: 'line-0-1', generationEpoch: 1, outputOrder: 1 }],
      ['More from me.', 2, { outputId: 'line-1-0', generationEpoch: 2, outputOrder: 2 }],
    ]);
    expect(maya.ends).toEqual([['line-0-1', 1], ['line-1-0', 2]]);
    expect(bea.phrases[0].ownership).toEqual({ outputId: 'line-2-0', generationEpoch: 3, outputOrder: 3 });
    expect(maya.stopped && bea.stopped).toBe(true);
  });

  it('stops mid-line without an error, and speaks nothing after', async () => {
    const run = speakAsCharacters('podcast:2', [
      { text: 'First line.', voiceId: 'Maya', speaker: MAYA },
      { text: 'Never heard.', voiceId: 'Bea', speaker: BEA },
    ]);
    await settle();
    run.stop();
    await expect(run.done).resolves.toBeUndefined();
    expect(mocks.sessions).toHaveLength(1);
    expect(mocks.sessions[0].stopped).toBe(true);
    expect(mocks.portrait.end).toHaveBeenCalled();
  });

  it('pauses once the line playing ends, and goes on from the next line on resume; a stop while paused ends it', async () => {
    const heard: number[] = [];
    const run = speakAsCharacters('podcast:3', [
      { text: 'First line.', voiceId: 'Maya', speaker: MAYA },
      { text: 'Second line.', voiceId: 'Maya', speaker: MAYA },
      { text: 'Third line.', voiceId: 'Maya', speaker: MAYA },
    ], (index) => heard.push(index));
    await settle();
    run.pause();
    await hearAll(); // the first line finishes
    await hearAll();
    expect(heard).toEqual([0]); // onLine fires as a line starts: the second never started
    run.resume();
    await settle();
    expect(heard).toEqual([0, 1]);
    run.pause();
    await hearAll(); // the second line finishes; the third waits
    await hearAll();
    expect(heard).toEqual([0, 1]);
    run.stop();
    await expect(run.done).resolves.toBeUndefined();
    expect(heard).toEqual([0, 1]);
  });
});
