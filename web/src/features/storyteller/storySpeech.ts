/**
 * A story page read aloud (Storyteller roadmap ST-4.3): line by line in the cast's voices, through the shared speech
 * service. The server plans the page (`/speech-plan`: each line's voice, sentence by sentence); each sentence's audio
 * comes from the project's audio, else is streamed as it is synthesized. A line is heard through its own sink, so it
 * can be skipped, and the next line's audio is asked for once the current line's has arrived (one request on the
 * speech service at a time, as the RPG's), so it is waiting when the line before has been heard. Lines are separated
 * by the read settings' paragraph pause, and the word notes are applied to what is sent. With the speech service down
 * the text stands, silent.
 */
import { openPcmSink, type PcmSink } from '../assistant';
import { api } from './api/gateway';

const AUTOPLAY_KEY = 'omnix:story:voice-autoplay';
const SAMPLE_RATE = 24_000;  // the speech service's

export type StoryReadOutcome = 'played' | 'silent' | 'stopped';

export type StorySpokenLine = {
  /** The page block it reads (blocks with no text are not read). */
  blockIndex: number;
  speakerId: string;
  sentences: string[];
  /** Its speaker is not in the cast: it is read in a neutral voice. */
  unknownSpeaker: boolean;
};

export type StoryReader = {
  pause(): void;
  resume(): void;
  /** Stops the line being heard and goes on with the next. */
  skip(): void;
  stop(): void;
  readonly outcome: Promise<StoryReadOutcome>;
};

export type StoryReadOptions = {
  pauseMs: number;
  pronunciation: Record<string, string>;
  /** The line being heard (its index among the page's read lines), or null once the page is done. */
  onLine: (line: number | null) => void;
};

export function storyAutoplay(): boolean {
  try {
    return window.localStorage.getItem(AUTOPLAY_KEY) === 'on';
  } catch {
    return false;
  }
}

export function setStoryAutoplay(on: boolean): void {
  try {
    window.localStorage.setItem(AUTOPLAY_KEY, on ? 'on' : 'off');
  } catch {
    // a private window: the setting lasts the page
  }
}

const escaped = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** A sentence as it is sent to be spoken: each noted word (whole word, any case) replaced by how to say it. */
export function withPronunciation(text: string, pronunciation: Record<string, string>): string {
  let said = text;
  for (const [word, note] of Object.entries(pronunciation)) {
    if (!word.trim() || !note.trim()) continue;
    said = said.replace(new RegExp(`(?<![\\p{L}\\p{N}])${escaped(word.trim())}(?![\\p{L}\\p{N}])`, 'giu'), note.trim());
  }
  return said.slice(0, 300);
}

async function planPage(projectId: string, pageId: string, signal: AbortSignal): Promise<StorySpokenLine[] | null> {
  const { data, error } = await api.POST('/api/story/projects/{project_id}/speech-plan', {
    params: { path: { project_id: projectId } },
    body: { page_id: pageId },
    signal,
  });
  if (error || !data) return null;
  return data.segments.map((segment) => ({
    blockIndex: segment.block_index,
    speakerId: segment.speaker_id,
    sentences: segment.sentences,
    unknownSpeaker: segment.unknown_speaker,
  }));
}

/** One line's audio as it arrives, held until a sink takes it. */
class LineAudio {
  private held: Array<[Int16Array, number]> = [];
  private sink: PcmSink | null = null;
  private readonly requests = new AbortController();
  skipped = false;
  readonly arrived: Promise<boolean>;

  constructor(projectId: string, pageId: string, line: StorySpokenLine, pronunciation: Record<string, string>,
    page: AbortSignal) {
    page.addEventListener('abort', () => this.requests.abort(), { once: true });
    this.arrived = this.fetchLine(projectId, pageId, line, pronunciation);
  }

  attach(sink: PcmSink): void {
    for (const [samples, rate] of this.held) sink.push(samples, rate);
    this.held = [];
    this.sink = sink;
  }

  skip(): void {
    this.skipped = true;
    this.requests.abort();
  }

  private push(samples: Int16Array, rate: number): void {
    if (this.sink) this.sink.push(samples, rate);
    else this.held.push([samples, rate]);
  }

  private async fetchLine(projectId: string, pageId: string, line: StorySpokenLine,
    pronunciation: Record<string, string>): Promise<boolean> {
    try {
      for (const sentence of line.sentences) {
        const text = withPronunciation(sentence, pronunciation);
        if (text.trim() && !await this.fetchSentence(projectId, pageId, line.speakerId, text)) return false;
      }
      return true;
    } catch {  // the service gone mid-sentence, or the line skipped or the page stopped: its requests aborted
      return false;
    }
  }

  private async fetchSentence(projectId: string, pageId: string, speakerId: string, text: string): Promise<boolean> {
    const { data, response } = await api.POST('/api/story/projects/{project_id}/speech-audio', {
      params: { path: { project_id: projectId } },
      body: { page_id: pageId, speaker_id: speakerId, text },
      parseAs: 'stream',
      signal: this.requests.signal,
    });
    const body = data as ReadableStream<Uint8Array> | null | undefined;
    if (!response.ok || !body) return false;
    const rate = Number(response.headers.get('X-Omnix-Sample-Rate')) || SAMPLE_RATE;
    const reader = body.getReader();
    const cancel = () => void reader.cancel().catch(() => undefined);
    this.requests.signal.addEventListener('abort', cancel, { once: true });
    let carry = new Uint8Array(0);  // an odd byte waits for its sample's other half
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        this.requests.signal.removeEventListener('abort', cancel);
        return !this.requests.signal.aborted;  // a line skipped or a page stopped is not whole
      }
      const bytes = new Uint8Array(carry.length + value.length);
      bytes.set(carry);
      bytes.set(value, carry.length);
      const whole = bytes.length - (bytes.length % 2);
      carry = bytes.slice(whole);
      if (whole) this.push(new Int16Array(bytes.buffer.slice(0, whole)), rate);
    }
  }
}

/** Reads a page aloud from its first line; a reader is stopped by the caller before another starts. */
export function readStoryPage(projectId: string, pageId: string, options: StoryReadOptions): StoryReader {
  const page = new AbortController();
  let stopped = false;
  let paused = false;
  let resumed: (() => void) | null = null;
  let current: { audio: LineAudio; sink: PcmSink } | null = null;
  let skipGap: (() => void) | null = null;

  const holdWhilePaused = () => paused && !stopped
    ? new Promise<void>((resolve) => { resumed = resolve; })
    : Promise.resolve();
  const gap = (ms: number) => new Promise<void>((resolve) => {
    if (ms <= 0) return resolve();
    const timer = window.setTimeout(resolve, ms);
    skipGap = () => { window.clearTimeout(timer); resolve(); };
  });

  async function read(): Promise<StoryReadOutcome> {
    const lines = await planPage(projectId, pageId, page.signal).catch(() => null);
    if (stopped) return 'stopped';
    if (!lines) return 'silent';
    const audio: LineAudio[] = [];
    const start = (index: number) => {
      audio[index] ??= new LineAudio(projectId, pageId, lines[index], options.pronunciation, page.signal);
      return audio[index];
    };
    for (let index = 0; index < lines.length; index += 1) {
      const line = start(index);
      void line.arrived.then((whole) => {
        if (whole && !stopped && index + 1 < lines.length) start(index + 1);
      });
      const sink = await openPcmSink();
      if (stopped) {
        sink?.stop();
        return 'stopped';
      }
      if (!sink) return 'silent';
      current = { audio: line, sink };
      if (paused) sink.pause();
      options.onLine(index);
      line.attach(sink);
      const whole = await line.arrived;
      if (!whole) sink.stop();
      if (stopped) return 'stopped';
      if (!whole && !line.skipped) return 'silent';
      if (whole) await sink.end();
      current = null;
      if (stopped) return 'stopped';
      if (!whole && index + 1 < lines.length) start(index + 1);  // a skipped line's next is asked for now
      await holdWhilePaused();
      if (!line.skipped && index + 1 < lines.length) await gap(options.pauseMs);
      skipGap = null;
      await holdWhilePaused();
      if (stopped) return 'stopped';
    }
    return 'played';
  }

  const outcome = read().catch(() => (stopped ? 'stopped' as const : 'silent' as const)).finally(() => {
    current?.sink.stop();
    options.onLine(null);
  });

  return {
    outcome,
    pause() {
      paused = true;
      current?.sink.pause();
    },
    resume() {
      paused = false;
      current?.sink.resume();
      resumed?.();
      resumed = null;
    },
    skip() {
      if (current) {
        current.audio.skip();
        current.sink.stop();
      } else {
        skipGap?.();
      }
    },
    stop() {
      stopped = true;
      page.abort();
      current?.sink.stop();
      skipGap?.();
      resumed?.();
    },
  };
}
