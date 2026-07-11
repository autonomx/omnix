import type { CharacterAvatarPack, CharacterLiveCallRuntime } from './characterClient';
import './liveCharacterAvatarBridge.css';

export type AvatarMouthFrame = 'closed' | 'small' | 'medium' | 'wide';
export type AvatarPresentationState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

const AVATAR_FRAME_EVENT = 'omnix:character-avatar-frame';
const AVATAR_RUNTIME_EVENT = 'omnix:character-avatar-runtime';
const AVATAR_PCM_EVENT = 'omnix:character-avatar-pcm';
const AVATAR_HOST_CLASS = 'assistant-live-character-avatar';
const LIVE_VISUAL_STAGE_CLASS = 'assistant-live-visual-stage';
const TTS_STREAM_PATH = '/api/tts/stream/server-sent-events';
const INSTALL_KEY = '__omnixCharacterAvatarBridgeInstalled';

let currentRuntime: CharacterLiveCallRuntime | null = null;
let currentMouthFrame: AvatarMouthFrame = 'closed';
let nextAudioFrameAt = 0;
let blinkClosed = false;
let blinkTimer: ReturnType<typeof setTimeout> | null = null;

export function publishCharacterAvatarRuntime(runtime: CharacterLiveCallRuntime | null): void {
  currentRuntime = runtime;
  currentMouthFrame = 'closed';
  blinkClosed = false;
  scheduleBlink();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AVATAR_RUNTIME_EVENT, { detail: runtime }));
  }
  renderAvatarHost();
}

export function mouthFrameForRms(rms: number): AvatarMouthFrame {
  if (!Number.isFinite(rms) || rms < 0.015) return 'closed';
  if (rms < 0.035) return 'small';
  if (rms < 0.075) return 'medium';
  return 'wide';
}

export function pcmMouthTimeline(
  samples: Int16Array,
  sampleRate: number,
  windowMs = 60,
): Array<{ offsetMs: number; frame: AvatarMouthFrame }> {
  if (!samples.length || !Number.isFinite(sampleRate) || sampleRate <= 0) return [];
  const windowSamples = Math.max(1, Math.floor(sampleRate * (windowMs / 1000)));
  const timeline: Array<{ offsetMs: number; frame: AvatarMouthFrame }> = [];
  let lastFrame: AvatarMouthFrame | null = null;
  for (let start = 0; start < samples.length; start += windowSamples) {
    const end = Math.min(samples.length, start + windowSamples);
    let sum = 0;
    for (let index = start; index < end; index += 1) {
      const normalized = samples[index] / 32768;
      sum += normalized * normalized;
    }
    const frame = mouthFrameForRms(Math.sqrt(sum / Math.max(1, end - start)));
    if (frame !== lastFrame) {
      timeline.push({ offsetMs: (start / sampleRate) * 1000, frame });
      lastFrame = frame;
    }
  }
  return timeline;
}

export function characterAvatarAssetUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}

export function presentationStateFromDom(
  voiceMode: string | undefined,
  inlineStatus: string,
): AvatarPresentationState {
  if (voiceMode === 'speaking') return 'speaking';
  if (voiceMode === 'error') return 'error';
  const normalized = inlineStatus.toLowerCase();
  if (/contacting|sending|streaming|synthesizing|generating|response ready/.test(normalized)) return 'thinking';
  if (voiceMode === 'listening') return 'listening';
  return 'idle';
}

function installLiveCharacterAvatarBridge(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const state = window as typeof window & Record<string, unknown>;
  if (state[INSTALL_KEY]) return;
  state[INSTALL_KEY] = true;

  const observer = new MutationObserver(() => renderAvatarHost());
  const observe = () => {
    if (!document.body) return;
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['data-voice-mode'],
    });
    renderAvatarHost();
  };
  if (document.body) observe();
  else window.addEventListener('DOMContentLoaded', observe, { once: true });

  window.addEventListener(AVATAR_FRAME_EVENT, (event) => {
    const detail = (event as CustomEvent<{ frame?: AvatarMouthFrame }>).detail;
    if (!detail?.frame) return;
    currentMouthFrame = detail.frame;
    updateAvatarImage();
  });
  window.addEventListener(AVATAR_RUNTIME_EVENT, () => renderAvatarHost());
  window.addEventListener(AVATAR_PCM_EVENT, (event) => {
    const detail = (event as CustomEvent<{ samples?: Int16Array; sampleRate?: number }>).detail;
    if (!(detail?.samples instanceof Int16Array)) return;
    schedulePcmSamples(detail.samples, Number(detail.sampleRate) || 24_000);
  });

  installTtsFetchMonitor();
}

function installTtsFetchMonitor(): void {
  if (typeof window.fetch !== 'function') return;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await originalFetch(input, init);
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    if (!url.includes(TTS_STREAM_PATH) || !response.body || typeof response.body.tee !== 'function') return response;

    const [applicationBody, monitorBody] = response.body.tee();
    void monitorTtsStream(monitorBody);
    return new Response(applicationBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  };
}

async function monitorTtsStream(stream: ReadableStream<Uint8Array>): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  nextAudioFrameAt = performance.now() + 90;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split(/\n\n/);
      pending = events.pop() ?? '';
      for (const eventText of events) {
        const payload = parseSsePayload(eventText);
        if (!payload) continue;
        if (payload.type === 'chunk' && typeof payload.audio_b64 === 'string') {
          schedulePcmFrames(payload.audio_b64, Number(payload.sample_rate) || 24_000);
        }
        if (payload.type === 'done' || payload.type === 'error') scheduleClosedFrame();
      }
    }
  } catch {
    scheduleClosedFrame();
  } finally {
    reader.releaseLock();
  }
}

function parseSsePayload(eventText: string): Record<string, unknown> | null {
  const data = eventText
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('');
  if (!data) return null;
  try {
    return JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function schedulePcmFrames(audioBase64: string, sampleRate: number): void {
  const binary = window.atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  const evenLength = bytes.byteLength - (bytes.byteLength % 2);
  if (!evenLength) return;
  const samples = new Int16Array(bytes.buffer, bytes.byteOffset, evenLength / 2);
  schedulePcmSamples(samples, sampleRate);
}

function schedulePcmSamples(samples: Int16Array, sampleRate: number): void {
  const now = performance.now();
  const startAt = Math.max(nextAudioFrameAt, now + 25);
  const timeline = pcmMouthTimeline(samples, sampleRate);
  for (const point of timeline) {
    window.setTimeout(() => dispatchAvatarFrame(point.frame), Math.max(0, startAt - now + point.offsetMs));
  }
  const durationMs = (samples.length / sampleRate) * 1000;
  nextAudioFrameAt = startAt + durationMs;
  window.setTimeout(() => dispatchAvatarFrame('closed'), Math.max(0, nextAudioFrameAt - now));
}

function scheduleClosedFrame(): void {
  window.setTimeout(() => dispatchAvatarFrame('closed'), Math.max(0, nextAudioFrameAt - performance.now()));
}

function dispatchAvatarFrame(frame: AvatarMouthFrame): void {
  window.dispatchEvent(new CustomEvent(AVATAR_FRAME_EVENT, { detail: { frame } }));
}

function scheduleBlink(): void {
  if (typeof window === 'undefined') return;
  if (blinkTimer !== null) clearTimeout(blinkTimer);
  const pack = currentRuntime?.avatar_pack;
  if (!pack?.blink_frames.closed) return;
  blinkTimer = window.setTimeout(() => {
    if (currentMouthFrame !== 'closed' || currentPresentationState() === 'speaking') {
      scheduleBlink();
      return;
    }
    blinkClosed = true;
    updateAvatarImage();
    window.setTimeout(() => {
      blinkClosed = false;
      updateAvatarImage();
      scheduleBlink();
    }, 120);
  }, 3_800 + Math.round(Math.random() * 2_400));
}

function normalizeLiveVoiceLayout(): {
  card: HTMLElement;
  stage: HTMLElement;
  orb: HTMLElement;
} | null {
  if (typeof document === 'undefined') return null;
  const card = document.querySelector<HTMLElement>('.assistant-live-card');
  const orb = card?.querySelector<HTMLElement>('.assistant-voice-orb') ?? null;
  if (!card || !orb) return null;

  let stage = card.querySelector<HTMLElement>(`.${LIVE_VISUAL_STAGE_CLASS}`);
  if (!stage) {
    stage = document.createElement('div');
    stage.className = LIVE_VISUAL_STAGE_CLASS;
    stage.setAttribute('aria-label', 'Live character visual');
    orb.insertAdjacentElement('beforebegin', stage);
  }
  if (orb.parentElement !== stage) stage.append(orb);

  const controls = card.querySelector<HTMLElement>('.assistant-voice-controls');
  const transcript = card.querySelector<HTMLElement>('.assistant-voice-transcript');
  if (controls && transcript) {
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', 'Live voice controls');
    transcript.setAttribute('role', 'region');
    transcript.setAttribute('aria-label', 'Live voice transcript');
    if (controls.nextElementSibling !== transcript) controls.insertAdjacentElement('afterend', transcript);
  }

  return { card, stage, orb };
}

function renderAvatarHost(): void {
  const layout = normalizeLiveVoiceLayout();
  const existing = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>(`.${AVATAR_HOST_CLASS}`);
  const pack = currentRuntime?.avatar_pack;
  const assetId = resolveFrameAsset(pack, currentMouthFrame, currentPresentationState());
  if (!layout || !assetId || !currentRuntime) {
    if (layout) {
      delete layout.stage.dataset.hasCharacterAvatar;
      layout.orb.hidden = false;
    }
    existing?.remove();
    return;
  }

  layout.stage.dataset.hasCharacterAvatar = 'true';
  layout.orb.hidden = true;
  const host = existing ?? document.createElement('figure');
  host.className = AVATAR_HOST_CLASS;
  host.dataset.mouthFrame = currentMouthFrame;
  if (!existing) {
    const image = document.createElement('img');
    image.alt = `${currentRuntime.display_name} live avatar`;
    const caption = document.createElement('figcaption');
    host.append(image, caption);
  }
  if (host.parentElement !== layout.stage) layout.stage.append(host);
  updateAvatarImage();
}

function currentPresentationState(): AvatarPresentationState {
  if (currentMouthFrame !== 'closed') return 'speaking';
  const orb = document.querySelector<HTMLElement>('.assistant-live-card .assistant-voice-orb');
  const statusText = document.querySelector<HTMLElement>('.assistant-inline-status')?.textContent ?? '';
  return presentationStateFromDom(orb?.dataset.voiceMode, statusText);
}

function updateAvatarImage(): void {
  const host = document.querySelector<HTMLElement>(`.${AVATAR_HOST_CLASS}`);
  const image = host?.querySelector<HTMLImageElement>('img');
  const caption = host?.querySelector<HTMLElement>('figcaption');
  const pack = currentRuntime?.avatar_pack;
  const presentationState = currentPresentationState();
  const assetId = resolveFrameAsset(pack, currentMouthFrame, presentationState);
  if (!host || !image || !caption || !assetId || !currentRuntime) return;
  if (host.dataset.mouthFrame !== currentMouthFrame) host.dataset.mouthFrame = currentMouthFrame;
  if (host.dataset.voiceMode !== presentationState) host.dataset.voiceMode = presentationState;
  const imageUrl = characterAvatarAssetUrl(assetId);
  if (image.getAttribute('src') !== imageUrl) image.src = imageUrl;
  const imageAlt = `${currentRuntime.display_name} live avatar`;
  if (image.alt !== imageAlt) image.alt = imageAlt;
  const backgroundId = pack?.active_background ? pack.background_asset_ids[pack.active_background] : '';
  const backgroundImage = backgroundId
    ? `linear-gradient(rgba(6, 10, 22, 0.12), rgba(6, 10, 22, 0.42)), url("${characterAvatarAssetUrl(backgroundId)}")`
    : '';
  if (host.style.backgroundImage !== backgroundImage) host.style.backgroundImage = backgroundImage;
  const captionText = presentationState === 'speaking'
    ? `${currentRuntime.display_name} is speaking`
    : presentationState === 'listening'
      ? `${currentRuntime.display_name} is listening`
      : presentationState === 'thinking'
        ? `${currentRuntime.display_name} is thinking`
        : currentRuntime.display_name;
  if (caption.textContent !== captionText) caption.textContent = captionText;
}

function resolveFrameAsset(
  pack: CharacterAvatarPack | null | undefined,
  frame: AvatarMouthFrame,
  state: AvatarPresentationState,
): string {
  if (!pack) return '';
  if (blinkClosed && pack.blink_frames.closed) return pack.blink_frames.closed;
  if (frame !== 'closed') {
    return pack.mouth_frames[frame] || pack.mouth_frames.closed || pack.base_asset_id || '';
  }
  if (pack.expression_frames[state]) return pack.expression_frames[state];
  if (pack.active_outfit && pack.outfit_frames[pack.active_outfit]) return pack.outfit_frames[pack.active_outfit];
  return pack.mouth_frames.closed || pack.base_asset_id || '';
}

installLiveCharacterAvatarBridge();
