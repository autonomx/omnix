import type { CharacterAvatarPack, CharacterLiveCallRuntime } from './characterClient';
import { isActiveView } from '../../app/viewApiScope';
import './liveCharacterAvatarBridge.css';

export type AvatarMouthFrame = 'closed' | 'small' | 'medium' | 'wide';
export type AvatarPresentationState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

const AVATAR_FRAME_EVENT = 'omnix:character-avatar-frame';
export const CHARACTER_AVATAR_RUNTIME_EVENT = 'omnix:character-avatar-runtime';
const AVATAR_PCM_EVENT = 'omnix:character-avatar-pcm';
const LIVE_CALL_DIAGNOSTIC_EVENT = 'omnix:live-call-diagnostic';
const LIVE2D_RENDER_EVENT = 'omnix:character-live2d-render';
const AVATAR_HOST_CLASS = 'assistant-live-character-avatar';
const LIVE_VISUAL_STAGE_CLASS = 'assistant-live-visual-stage';
const TTS_STREAM_PATH = '/api/tts/stream/server-sent-events';
const INSTALL_KEY = '__omnixCharacterAvatarBridgeInstalled';
const AUDIO_ELEMENT_FRAME_MS = 50;
const AUDIO_ELEMENT_FFT_SIZE = 1_024;
const AUDIO_BUFFER_WINDOW_MS = 60;
const ENVELOPE_FRAME_ALIASES: Record<AvatarMouthFrame, string[]> = {
  closed: ['closed', 'silence', 'MBP'],
  small: ['small', 'U', 'WQ', 'FV', 'other'],
  medium: ['medium', 'E', 'L', 'other', 'U'],
  wide: ['wide', 'A', 'O', 'other', 'E'],
};

type AudioMonitorWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
};

type CapturableAudioElement = HTMLAudioElement & {
  captureStream?: () => MediaStream;
  mozCaptureStream?: () => MediaStream;
};

type PatchedCreateBufferSource = AudioContext['createBufferSource'] & {
  __omnixAvatarAudioMonitor?: boolean;
};

type LiveCallDiagnosticDetail = {
  source?: string;
  event?: string;
  details?: Record<string, unknown>;
};

let currentRuntime: CharacterLiveCallRuntime | null = null;
let currentMouthFrame: AvatarMouthFrame = 'closed';
let nextAudioFrameAt = 0;
let blinkClosed = false;
let blinkTimer: ReturnType<typeof setTimeout> | null = null;
const audioElementStops = new WeakMap<HTMLAudioElement, () => void>();

export function publishCharacterAvatarRuntime(runtime: CharacterLiveCallRuntime | null): void {
  currentRuntime = runtime;
  currentMouthFrame = 'closed';
  nextAudioFrameAt = 0;
  blinkClosed = false;
  scheduleBlink();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(CHARACTER_AVATAR_RUNTIME_EVENT, { detail: runtime }));
  }
  renderAvatarHost();
}

/** Apply a newly selected pack to the runtime currently driving the live host. */
export function applyAvatarPackToCurrentRuntime(
  characterId: string,
  avatarPack: CharacterAvatarPack | null,
): boolean {
  if (!currentRuntime || currentRuntime.character_id !== characterId) return false;
  publishCharacterAvatarRuntime({ ...currentRuntime, avatar_pack: avatarPack });
  return true;
}

export function mouthFrameForRms(rms: number): AvatarMouthFrame {
  if (!Number.isFinite(rms) || rms < 0.015) return 'closed';
  if (rms < 0.035) return 'small';
  if (rms < 0.075) return 'medium';
  return 'wide';
}

export function floatPcmMouthFrame(samples: Float32Array): AvatarMouthFrame {
  if (!samples.length) return 'closed';
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return mouthFrameForRms(Math.sqrt(sum / samples.length));
}

export function floatPcmMouthTimeline(
  samples: Float32Array,
  sampleRate: number,
  windowMs = AUDIO_BUFFER_WINDOW_MS,
): Array<{ offsetMs: number; frame: AvatarMouthFrame }> {
  if (!samples.length || !Number.isFinite(sampleRate) || sampleRate <= 0) return [];
  const windowSamples = Math.max(1, Math.floor(sampleRate * (windowMs / 1000)));
  const timeline: Array<{ offsetMs: number; frame: AvatarMouthFrame }> = [];
  let lastFrame: AvatarMouthFrame | null = null;
  for (let start = 0; start < samples.length; start += windowSamples) {
    const frame = floatPcmMouthFrame(samples.subarray(start, Math.min(samples.length, start + windowSamples)));
    if (frame !== lastFrame) {
      timeline.push({ offsetMs: (start / sampleRate) * 1000, frame });
      lastFrame = frame;
    }
  }
  return timeline;
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

export function avatarMouthAssetForFrame(
  pack: CharacterAvatarPack,
  frame: AvatarMouthFrame,
): string {
  for (const key of ENVELOPE_FRAME_ALIASES[frame]) {
    const assetId = pack.mouth_frames[key];
    if (assetId) return assetId;
  }
  return pack.base_asset_id || '';
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
  window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, () => renderAvatarHost());
  window.addEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, (event) => {
    if (currentRuntime?.avatar_pack?.renderer !== 'live2d') return;
    const detail = (event as CustomEvent<LiveCallDiagnosticDetail>).detail;
    if (detail?.source !== 'audio_worklet') return;
    if (detail.event === 'worklet_avatar_frame') {
      const frame = detail.details?.frame;
      if (isAvatarMouthFrame(frame)) dispatchAvatarFrame(frame);
      return;
    }
    if (
      detail.event === 'worklet_idle'
      || detail.event === 'worklet_drained'
      || detail.event === 'worklet_stopped'
      || detail.event === 'worklet_underrun'
    ) {
      dispatchAvatarFrame('closed');
    }
  });
  window.addEventListener(AVATAR_PCM_EVENT, (event) => {
    // Live2D live-call lip sync is driven from the AudioWorklet's actual
    // playback envelope. Arrival-time PCM can be hundreds of milliseconds
    // ahead of what is audible when playback is buffered or rebuffering.
    if (currentRuntime?.avatar_pack?.renderer === 'live2d') return;
    const detail = (event as CustomEvent<{
      samples?: Int16Array;
      sampleRate?: number;
      startDelayMs?: number;
    }>).detail;
    if (!(detail?.samples instanceof Int16Array)) return;
    schedulePcmSamples(
      detail.samples,
      Number(detail.sampleRate) || 24_000,
      Number(detail.startDelayMs) || 0,
    );
  });

  installTtsFetchMonitor();
  installAudioElementMonitor();
  installAudioBufferSourceMonitor();
}

function installTtsFetchMonitor(): void {
  if (typeof window.fetch !== 'function') return;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await originalFetch(input, init);
    if (!isActiveView('chatbot')) return response;
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

function installAudioElementMonitor(): void {
  const prototype = window.HTMLMediaElement?.prototype;
  if (!prototype || typeof prototype.play !== 'function') return;
  const originalPlay = prototype.play;
  prototype.play = function patchedAvatarAudioPlay(this: HTMLMediaElement): Promise<void> {
    const audio = this instanceof HTMLAudioElement ? this : null;
    if (audio) startAudioElementMonitor(audio);
    const result = originalPlay.call(this);
    if (audio && result && typeof result.catch === 'function') {
      void result.catch(() => stopAudioElementMonitor(audio));
    }
    return result;
  };
}

function installAudioBufferSourceMonitor(): void {
  const liveWindow = window as AudioMonitorWindow;
  const constructors = [liveWindow.AudioContext, liveWindow.webkitAudioContext]
    .filter((value): value is typeof AudioContext => Boolean(value));
  const patchedPrototypes = new Set<AudioContext>();
  for (const AudioContextCtor of constructors) {
    const prototype = AudioContextCtor.prototype;
    if (patchedPrototypes.has(prototype)) continue;
    patchedPrototypes.add(prototype);
    const originalCreate = prototype.createBufferSource as PatchedCreateBufferSource;
    if (originalCreate.__omnixAvatarAudioMonitor) continue;
    const patchedCreate = function patchedAvatarBufferSource(this: AudioContext): AudioBufferSourceNode {
      const source = originalCreate.call(this);
      const originalStart = source.start.bind(source);
      source.start = ((when = 0, offset?: number, duration?: number): void => {
        if (typeof duration === 'number') originalStart(when, offset ?? 0, duration);
        else if (typeof offset === 'number') originalStart(when, offset);
        else originalStart(when);
        scheduleAudioBufferFrames(source.buffer, this, when, source.playbackRate.value, offset, duration);
      }) as AudioBufferSourceNode['start'];
      return source;
    } as PatchedCreateBufferSource;
    patchedCreate.__omnixAvatarAudioMonitor = true;
    prototype.createBufferSource = patchedCreate;
  }
}

function scheduleAudioBufferFrames(
  buffer: AudioBuffer | null,
  context: AudioContext,
  when: number,
  playbackRate: number,
  offset = 0,
  duration?: number,
): void {
  if (!buffer || !currentRuntime?.avatar_pack || buffer.numberOfChannels < 1) return;
  const rate = Number.isFinite(playbackRate) && playbackRate > 0 ? playbackRate : 1;
  const startFrame = Math.max(0, Math.min(buffer.length, Math.floor(Math.max(0, offset) * buffer.sampleRate)));
  const requestedEnd = typeof duration === 'number'
    ? startFrame + Math.floor(Math.max(0, duration) * buffer.sampleRate)
    : buffer.length;
  const endFrame = Math.max(startFrame, Math.min(buffer.length, requestedEnd));
  const samples = buffer.getChannelData(0).subarray(startFrame, endFrame);
  if (!samples.length) return;
  const startDelayMs = Math.max(0, (when - context.currentTime) * 1000);
  for (const point of floatPcmMouthTimeline(samples, buffer.sampleRate)) {
    window.setTimeout(() => dispatchAvatarFrame(point.frame), startDelayMs + (point.offsetMs / rate));
  }
  const durationMs = samples.length * 1000 / buffer.sampleRate / rate;
  window.setTimeout(() => dispatchAvatarFrame('closed'), startDelayMs + durationMs);
}

function startAudioElementMonitor(audio: HTMLAudioElement): void {
  if (!currentRuntime?.avatar_pack) return;
  stopAudioElementMonitor(audio);
  const liveWindow = window as AudioMonitorWindow;
  const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
  if (!AudioContextCtor) return;

  let context: AudioContext | null = null;
  let source: AudioNode | null = null;
  let analyser: AnalyserNode | null = null;
  let timer: number | null = null;
  let stopped = false;

  const stop = (): void => {
    if (stopped) return;
    stopped = true;
    if (timer !== null) window.clearInterval(timer);
    audio.removeEventListener('pause', stop);
    audio.removeEventListener('ended', stop);
    audio.removeEventListener('error', stop);
    if (audioElementStops.get(audio) === stop) audioElementStops.delete(audio);
    try { source?.disconnect(); } catch { /* ignore monitor cleanup failures */ }
    try { analyser?.disconnect(); } catch { /* ignore monitor cleanup failures */ }
    if (context && context.state !== 'closed') void context.close().catch(() => undefined);
    dispatchAvatarFrame('closed');
  };

  try {
    context = new AudioContextCtor({ latencyHint: 'interactive' });
    analyser = context.createAnalyser();
    analyser.fftSize = AUDIO_ELEMENT_FFT_SIZE;
    analyser.smoothingTimeConstant = 0.2;

    const capturable = audio as CapturableAudioElement;
    const capturedStream = capturable.captureStream?.() ?? capturable.mozCaptureStream?.();
    if (capturedStream && typeof context.createMediaStreamSource === 'function') {
      source = context.createMediaStreamSource(capturedStream);
      source.connect(analyser);
    } else {
      source = context.createMediaElementSource(audio);
      source.connect(analyser);
      analyser.connect(context.destination);
    }

    const waveform = new Float32Array(analyser.fftSize);
    timer = window.setInterval(() => {
      if (!analyser || audio.paused || audio.ended) return;
      analyser.getFloatTimeDomainData(waveform);
      dispatchAvatarFrame(floatPcmMouthFrame(waveform));
    }, AUDIO_ELEMENT_FRAME_MS);

    audioElementStops.set(audio, stop);
    audio.addEventListener('pause', stop, { once: true });
    audio.addEventListener('ended', stop, { once: true });
    audio.addEventListener('error', stop, { once: true });
    if (context.state !== 'running') void context.resume().catch(() => undefined);
  } catch {
    stop();
  }
}

function stopAudioElementMonitor(audio: HTMLAudioElement): void {
  audioElementStops.get(audio)?.();
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

function schedulePcmSamples(samples: Int16Array, sampleRate: number, startDelayMs = 0): void {
  const now = performance.now();
  const startAt = Math.max(nextAudioFrameAt, now + 25 + Math.max(0, startDelayMs));
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

function isAvatarMouthFrame(value: unknown): value is AvatarMouthFrame {
  return value === 'closed' || value === 'small' || value === 'medium' || value === 'wide';
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
  if (!isActiveView('chatbot')) {
    document.querySelectorAll<HTMLElement>(`.${AVATAR_HOST_CLASS}`).forEach((host) => host.remove());
    return;
  }
  const layout = normalizeLiveVoiceLayout();
  const fullscreenHost = typeof document === 'undefined'
    ? null
    : document.querySelector<HTMLElement>(`[data-live-chat-fullscreen-shell] .${AVATAR_HOST_CLASS}`);
  const existing = fullscreenHost
    ?? (typeof document === 'undefined' ? null : document.querySelector<HTMLElement>(`.${AVATAR_HOST_CLASS}`));
  const runtime = currentRuntime;
  const pack = runtime?.avatar_pack;
  const live2d = pack?.renderer === 'live2d' && Boolean(pack.rig_asset_id);
  const assetId = live2d ? '' : resolveFrameAsset(pack, currentMouthFrame, currentPresentationState());
  if (!layout || !runtime || (!live2d && !assetId)) {
    if (layout) {
      delete layout.stage.dataset.hasCharacterAvatar;
      layout.orb.hidden = false;
    }
    if (existing?.closest('.assistant-live-card')) existing.remove();
    return;
  }

  layout.stage.dataset.hasCharacterAvatar = 'true';
  layout.orb.hidden = true;
  const host = existing ?? document.createElement('figure');
  host.className = AVATAR_HOST_CLASS;
  host.dataset.mouthFrame = currentMouthFrame;
  host.dataset.renderer = live2d ? 'live2d' : 'sprite';
  if (!fullscreenHost && host.parentElement !== layout.stage) layout.stage.append(host);

  if (live2d) {
    const presentationState = currentPresentationState();
    if (host.dataset.voiceMode !== presentationState) host.dataset.voiceMode = presentationState;
    window.dispatchEvent(new CustomEvent(LIVE2D_RENDER_EVENT, { detail: { runtime, host } }));
    return;
  }

  if (!host.querySelector('img') || existing?.dataset.renderer === 'live2d') {
    const image = document.createElement('img');
    image.alt = `${runtime.display_name} live avatar`;
    const caption = document.createElement('figcaption');
    host.replaceChildren(image, caption);
  }
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
  const pack = currentRuntime?.avatar_pack;
  const presentationState = currentPresentationState();
  if (host && currentRuntime && pack?.renderer === 'live2d') {
    if (host.dataset.voiceMode !== presentationState) host.dataset.voiceMode = presentationState;
    const caption = host.querySelector<HTMLElement>('figcaption');
    if (caption) caption.textContent = captionForState(currentRuntime.display_name, presentationState);
    return;
  }

  const image = host?.querySelector<HTMLImageElement>('img');
  const caption = host?.querySelector<HTMLElement>('figcaption');
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
  const captionText = captionForState(currentRuntime.display_name, presentationState);
  if (caption.textContent !== captionText) caption.textContent = captionText;
}

function captionForState(displayName: string, state: AvatarPresentationState): string {
  return state === 'speaking'
    ? `${displayName} is speaking`
    : state === 'listening'
      ? `${displayName} is listening`
      : state === 'thinking'
        ? `${displayName} is thinking`
        : displayName;
}

function resolveFrameAsset(
  pack: CharacterAvatarPack | null | undefined,
  frame: AvatarMouthFrame,
  state: AvatarPresentationState,
): string {
  if (!pack || pack.renderer !== 'sprite') return '';
  if (blinkClosed && pack.blink_frames.closed) return pack.blink_frames.closed;
  if (frame !== 'closed') return avatarMouthAssetForFrame(pack, frame);
  if (pack.expression_frames[state]) return pack.expression_frames[state];
  if (pack.active_outfit && pack.outfit_frames[pack.active_outfit]) return pack.outfit_frames[pack.active_outfit];
  return avatarMouthAssetForFrame(pack, 'closed');
}

installLiveCharacterAvatarBridge();
