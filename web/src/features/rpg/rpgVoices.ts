/**
 * A campaign's voices on the play screen (evolution roadmap EV-13): a finished response is spoken block by block, each
 * in its speaker's cast voice (a quote inside narration in its speaker's), sentence by sentence, each sentence's audio
 * from the campaign's cache or synthesized once. Only text shown as final is spoken; a response still being written
 * has nothing to play. Press to play by default; auto-play is a setting, off until the player switches it on. With the
 * speech service down the text stands, silent, and the play button says so.
 */
import { api } from './api/gateway';

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
let current: HTMLAudioElement | null = null;
let finishCurrent: (() => void) | null = null;  // a stopped sentence ends its run, and its audio is let go

function play(audio: Blob, run: number): Promise<void> {
  return new Promise((resolve) => {
    if (run !== playing || typeof Audio === 'undefined') {
      resolve();
      return;
    }
    const url = URL.createObjectURL(audio);
    const element = new Audio(url);
    current = element;
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      finishCurrent = null;
      URL.revokeObjectURL(url);
      resolve();
    };
    finishCurrent = done;
    element.addEventListener('ended', done, { once: true });
    element.addEventListener('error', done, { once: true });
    void element.play().catch(done);
  });
}

/** Speak ``blocks`` (a finished response's): each in its speaker's voice, a sentence at a time; a new call stops the
 * one before. */
export async function speakResponse(sessionId: string, blocks: RpgSpokenBlock[]): Promise<RpgSpeechOutcome> {
  const spoken = blocks.filter((block) => block.text.trim());
  if (!sessionId || !spoken.length) return 'silent';
  const run = ++playing;
  current?.pause();
  finishCurrent?.();
  const { data, error } = await api.POST('/api/rpg/sessions/{session_id}/speech-plan', {
    params: { path: { session_id: sessionId } },
    body: { blocks: spoken.map((block) => ({ speaker_id: block.speakerId || 'narrator', text: block.text })) },
  });
  const segments = (data as { segments?: Array<{ speaker_id: string; sentences: string[] }> } | undefined)?.segments;
  if (error || !segments) return 'silent';
  for (const segment of segments) {
    for (const sentence of segment.sentences) {
      if (run !== playing) return 'stopped';
      const { data: audio, response } = await api.POST('/api/rpg/sessions/{session_id}/speech-audio', {
        params: { path: { session_id: sessionId } },
        body: { speaker_id: segment.speaker_id, text: sentence },
        parseAs: 'blob',
      });
      if (!response.ok || !(audio instanceof Blob)) return 'silent';
      await play(audio, run);
    }
  }
  return run === playing ? 'played' : 'stopped';
}

export function stopSpeaking(): void {
  playing += 1;
  current?.pause();
  finishCurrent?.();
  current = null;
}
