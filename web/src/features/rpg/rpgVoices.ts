/**
 * A campaign's voices on the play screen (evolution roadmap EV-13): a finished response is spoken block by block, each
 * in its speaker's cast voice (a quote inside narration in its speaker's), sentence by sentence, each sentence's audio
 * from the campaign's cache or streamed as it is synthesized (and kept), heard as one stream from its first audio.
 * Only text shown as final is spoken; a response still being written has nothing to play. Press to play by default; auto-play is a setting, off until the player switches it on. With the
 * speech service down the text stands, silent, and the play button says so.
 */
import { api } from './api/gateway';
import { openPcmSink, type RpgPcmSink } from './rpgSpeechSink';

const AUTOPLAY_KEY = 'omnix:rpg:voice-autoplay';

export interface RpgSpokenBlock {
  speakerId: string;
  text: string;
}

export interface RpgVoiceSpan {
  speaker_id: string;
  start: number;
  end: number;
}

export type RpgSpeechOutcome = 'played' | 'silent' | 'stopped';

export function voiceAutoplay(): boolean {
  try {
    return window.localStorage.getItem(AUTOPLAY_KEY) === 'on';
  } catch {
    return false;
  }
}

export function setVoiceAutoplay(on: boolean): void {
  try {
    window.localStorage.setItem(AUTOPLAY_KEY, on ? 'on' : 'off');
  } catch {
    // a private window: the setting lasts the page
  }
}

/** A narration's text as its spoken blocks: the narrator's, and each quote in its speaker's voice. */
export function narrationBlocks(text: string, voices: RpgVoiceSpan[] = [], speakerId = 'narrator'): RpgSpokenBlock[] {
  const blocks: RpgSpokenBlock[] = [];
  const points = Array.from(text);  // the engine counts characters (code points); the page, UTF-16 units
  const unit = (index: number) => points.slice(0, index).join('').length;
  let at = 0;
  for (const span of [...voices].map((row) => ({ ...row, start: unit(row.start), end: unit(row.end) }))
    .sort((a, b) => a.start - b.start)) {
    if (span.start < at || span.end > text.length) continue;
    if (span.start > at) blocks.push({ speakerId, text: text.slice(at, span.start) });
    blocks.push({ speakerId: span.speaker_id, text: text.slice(span.start, span.end) });
    at = span.end;
  }
  if (at < text.length) blocks.push({ speakerId, text: text.slice(at) });
  return blocks.filter((block) => block.text.trim());
}

let playing = 0;
let stopCurrent: (() => void) | null = null;  // the response being heard, let go when another starts or it stops

/** One sentence's audio, pushed into ``sink`` as it arrives; false when the service could not speak it. */
async function streamSentence(sessionId: string, sentence: { speakerId: string; text: string }, sink: RpgPcmSink,
  signal: AbortSignal): Promise<boolean> {
  const { data, response } = await api.POST('/api/rpg/sessions/{session_id}/speech-audio', {
    params: { path: { session_id: sessionId } },
    body: { speaker_id: sentence.speakerId, text: sentence.text },
    parseAs: 'stream',
    signal,
  });
  const body = data as ReadableStream<Uint8Array> | null | undefined;
  if (!response.ok || !body) return false;
  const rate = Number(response.headers.get('X-Omnix-Sample-Rate')) || 24_000;
  const reader = body.getReader();
  let carry = new Uint8Array(0);  // an odd byte waits for its sample's other half
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return true;
    const bytes = new Uint8Array(carry.length + value.length);
    bytes.set(carry);
    bytes.set(value, carry.length);
    const whole = bytes.length - (bytes.length % 2);
    carry = bytes.slice(whole);
    if (whole) sink.push(new Int16Array(bytes.buffer.slice(0, whole)), rate);
  }
}

/** Speak ``blocks`` (a finished response's): each in its speaker's voice, sentence by sentence, as one stream heard
 * from its first audio; a new call stops the one before, its requests too. Anything failing leaves the text silent. */
export async function speakResponse(sessionId: string, blocks: RpgSpokenBlock[]): Promise<RpgSpeechOutcome> {
  const spoken = blocks.filter((block) => block.text.trim());
  if (!sessionId || !spoken.length) return 'silent';
  const run = ++playing;
  stopCurrent?.();
  const requests = new AbortController();
  let sink: RpgPcmSink | null = null;
  stopCurrent = () => {
    requests.abort();
    sink?.stop();
  };
  try {
    const { data, error } = await api.POST('/api/rpg/sessions/{session_id}/speech-plan', {
      params: { path: { session_id: sessionId } },
      body: { blocks: spoken.map((block) => ({ speaker_id: block.speakerId || 'narrator', text: block.text })) },
      signal: requests.signal,
    });
    const segments = (data as { segments?: Array<{ speaker_id: string; sentences: string[] }> } | undefined)?.segments;
    if (error || !segments) return run === playing ? 'silent' : 'stopped';
    const opened = await openPcmSink();
    if (run !== playing) {
      opened?.stop();
      return 'stopped';
    }
    if (!opened) return 'silent';
    sink = opened;
    // Each sentence is asked for when the one before has arrived, not when it has been heard: the service speaks
    // faster than real time, so the stream stays ahead of what is heard.
    for (const segment of segments) {
      for (const text of segment.sentences) {
        if (!await streamSentence(sessionId, { speakerId: segment.speaker_id, text }, opened, requests.signal)) {
          opened.stop();
          return run === playing ? 'silent' : 'stopped';
        }
      }
    }
    await opened.end();
    return run === playing ? 'played' : 'stopped';
  } catch {  // the service gone mid-sentence, or this response stopped: its requests aborted
    sink?.stop();
    return run === playing ? 'silent' : 'stopped';
  }
}

export function stopSpeaking(): void {
  playing += 1;
  stopCurrent?.();
  stopCurrent = null;
}
