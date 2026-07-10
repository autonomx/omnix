export type CharacterViseme = 'silence' | 'A' | 'E' | 'O' | 'U' | 'MBP' | 'FV' | 'L' | 'WQ' | 'other';

export interface TimedCharacterViseme {
  viseme: CharacterViseme;
  startMs: number;
  durationMs: number;
}

type RuntimeAvatarPack = {
  render_mode: 'audio_envelope' | 'viseme' | 'static';
  renderer?: 'sprite' | 'live2d' | 'rive';
  rig_asset_id?: string | null;
  base_asset_id?: string | null;
  mouth_frames: Record<string, string>;
};

type RuntimeDetail = {
  display_name: string;
  avatar_pack?: RuntimeAvatarPack | null;
};

const RUNTIME_EVENT = 'omnix:character-avatar-runtime';
const FRAME_EVENT = 'omnix:character-avatar-frame';
const RIG_VISEME_EVENT = 'omnix:character-rig-viseme';
const TTS_STREAM_PATH = '/api/tts/stream/server-sent-events';
const INSTALL_KEY = '__omnixCharacterVisemeBridgeInstalled';
const FALLBACK_FRAME: Record<CharacterViseme, string> = {
  silence: 'closed', A: 'wide', E: 'medium', O: 'wide', U: 'small', MBP: 'closed', FV: 'small', L: 'medium', WQ: 'small', other: 'medium',
};

let runtime: RuntimeDetail | null = null;
let currentViseme: CharacterViseme = 'silence';
let nextVisemeAudioAt = 0;

export function visemeSequenceFromText(text: string): CharacterViseme[] {
  const result: CharacterViseme[] = [];
  const tokens = String(text || '').match(/[a-z]+|[^a-z\s]/gi) ?? [];
  for (const token of tokens) {
    const lowered = token.toLowerCase();
    if (!/^[a-z]+$/.test(lowered)) {
      appendUnique(result, 'silence');
      continue;
    }
    for (let index = 0; index < lowered.length; index += 1) {
      const pair = lowered.slice(index, index + 2);
      if (pair === 'qu' || pair === 'wh') {
        appendUnique(result, 'WQ');
        index += 1;
        continue;
      }
      const character = lowered[index];
      appendUnique(result,
        'mbp'.includes(character) ? 'MBP'
          : 'fv'.includes(character) ? 'FV'
            : character === 'l' ? 'L'
              : 'wq'.includes(character) ? 'WQ'
                : character === 'a' ? 'A'
                  : 'eiy'.includes(character) ? 'E'
                    : character === 'o' ? 'O'
                      : character === 'u' ? 'U'
                        : 'other');
    }
    appendUnique(result, 'silence');
  }
  if (!result.length) return ['silence'];
  if (result.at(-1) !== 'silence') result.push('silence');
  return result;
}

export function fitVisemesToDuration(text: string, durationMs: number): TimedCharacterViseme[] {
  const duration = Math.max(1, durationMs);
  const sequence = visemeSequenceFromText(text);
  const weights = sequence.map((viseme) => viseme === 'silence' ? 0.45 : 1);
  const totalWeight = weights.reduce((total, weight) => total + weight, 0) || 1;
  let cursor = 0;
  return sequence.map((viseme, index) => {
    const cueDuration = index === sequence.length - 1 ? duration - cursor : duration * weights[index] / totalWeight;
    const cue = { viseme, startMs: cursor, durationMs: Math.max(1, cueDuration) };
    cursor += cueDuration;
    return cue;
  });
}

function install(): void {
  if (typeof window === 'undefined') return;
  const state = window as typeof window & Record<string, unknown>;
  if (state[INSTALL_KEY]) return;
  state[INSTALL_KEY] = true;
  window.addEventListener(RUNTIME_EVENT, (event) => {
    runtime = (event as CustomEvent<RuntimeDetail | null>).detail;
    currentViseme = 'silence';
  });
  window.addEventListener(FRAME_EVENT, () => {
    if (runtime?.avatar_pack?.render_mode === 'viseme') window.setTimeout(() => renderViseme(currentViseme), 0);
  });
  installFetchMonitor();
}

function installFetchMonitor(): void {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const text = url.includes(TTS_STREAM_PATH) ? requestText(init?.body) : '';
    const response = await originalFetch(input, init);
    if (!text || !response.body || typeof response.body.tee !== 'function') return response;
    const [applicationBody, monitorBody] = response.body.tee();
    void monitorStream(monitorBody, text);
    return new Response(applicationBody, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
}

async function monitorStream(stream: ReadableStream<Uint8Array>, text: string): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const sequence = visemeSequenceFromText(text);
  let sequenceIndex = 0;
  let pending = '';
  nextVisemeAudioAt = performance.now() + 90;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split(/\n\n/);
      pending = events.pop() ?? '';
      for (const eventText of events) {
        const payload = parseSse(eventText);
        if (!payload) continue;
        if (payload.type === 'viseme' && typeof payload.viseme === 'string') {
          scheduleNativeViseme(payload);
          continue;
        }
        if (payload.type === 'chunk' && typeof payload.audio_b64 === 'string') {
          const durationMs = pcmDurationMs(payload.audio_b64, Number(payload.sample_rate) || 24_000);
          sequenceIndex = scheduleChunkVisemes(sequence, sequenceIndex, durationMs);
        }
        if (payload.type === 'done' || payload.type === 'error') scheduleViseme('silence', Math.max(0, nextVisemeAudioAt - performance.now()));
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function scheduleChunkVisemes(sequence: CharacterViseme[], startIndex: number, durationMs: number): number {
  if (!durationMs) return startIndex;
  const now = performance.now();
  const startAt = Math.max(nextVisemeAudioAt, now + 25);
  const cueCount = Math.max(1, Math.min(sequence.length, Math.round(durationMs / 90)));
  const cues: CharacterViseme[] = [];
  for (let index = 0; index < cueCount; index += 1) cues.push(sequence[(startIndex + index) % sequence.length]);
  const cueDuration = durationMs / cueCount;
  cues.forEach((viseme, index) => scheduleViseme(viseme, Math.max(0, startAt - now + index * cueDuration)));
  nextVisemeAudioAt = startAt + durationMs;
  return (startIndex + cueCount) % sequence.length;
}

function scheduleNativeViseme(payload: Record<string, unknown>): void {
  const viseme = normalizeViseme(String(payload.viseme || 'silence'));
  const startMs = Number(payload.start_ms) || 0;
  scheduleViseme(viseme, Math.max(0, nextVisemeAudioAt - performance.now() + startMs));
}

function scheduleViseme(viseme: CharacterViseme, delayMs: number): void {
  window.setTimeout(() => renderViseme(viseme), delayMs);
}

function renderViseme(viseme: CharacterViseme): void {
  currentViseme = viseme;
  const pack = runtime?.avatar_pack;
  if (!pack || pack.render_mode !== 'viseme') return;
  window.dispatchEvent(new CustomEvent(RIG_VISEME_EVENT, { detail: { viseme, renderer: pack.renderer ?? 'sprite', rigAssetId: pack.rig_asset_id ?? null } }));
  const host = document.querySelector<HTMLElement>('.assistant-live-character-avatar');
  const image = host?.querySelector<HTMLImageElement>('img');
  if (!host || !image) return;
  const assetId = pack.mouth_frames[viseme] || pack.mouth_frames[FALLBACK_FRAME[viseme]] || pack.mouth_frames.closed || pack.base_asset_id || '';
  if (!assetId) return;
  host.dataset.viseme = viseme;
  host.dataset.renderer = pack.renderer ?? 'sprite';
  image.src = `/api/assets/${encodeURIComponent(assetId)}/file`;
}

function requestText(body: BodyInit | null | undefined): string {
  if (typeof body !== 'string') return '';
  try {
    const payload = JSON.parse(body) as { text?: unknown };
    return typeof payload.text === 'string' ? payload.text : '';
  } catch {
    return '';
  }
}

function parseSse(eventText: string): Record<string, unknown> | null {
  const data = eventText.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('');
  if (!data) return null;
  try { return JSON.parse(data) as Record<string, unknown>; } catch { return null; }
}

function pcmDurationMs(audioBase64: string, sampleRate: number): number {
  try { return (window.atob(audioBase64).length / 2 / sampleRate) * 1000; } catch { return 0; }
}

function normalizeViseme(value: string): CharacterViseme {
  return ['silence', 'A', 'E', 'O', 'U', 'MBP', 'FV', 'L', 'WQ', 'other'].includes(value) ? value as CharacterViseme : 'other';
}

function appendUnique(values: CharacterViseme[], value: CharacterViseme): void {
  if (!values.length || values.at(-1) !== value) values.push(value);
}

install();
