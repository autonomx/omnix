import {
  LIVE_CONVERSATION_PROFILE_CHANGED_EVENT,
  readEffectiveLiveConversationProfile,
  type DuplexMode,
  type LiveConversationProfile,
} from '../chatbot/liveConversationProfileClient';
import { assessAcousticBargeIn, calculatePcm16Rms } from './live-voice-barge-in-detector';

const PLAYBACK_STATE_EVENT = 'omnix:assistant-audio-playback-state';
const PLAYBACK_PCM_EVENT = 'omnix:character-avatar-pcm';
const USER_SPEECH_EVENT = 'omnix:assistant-live-voice-user-speech';
const PERF_EVENT = 'omnix:assistant-voice-perf';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const DUCK_EVENT = 'omnix:assistant-audio-duck';
const STREAM_AUDIO_BUTTON_SELECTOR = 'button[data-omnix-stream-audio][aria-pressed="true"]';
const trackedStreams = new Set<MediaStream>();
const CANDIDATE_TIMEOUT_MS = 1_500;

let announcedSpeaking = false;
let assistantSpeaking = false;
let configuredMode: DuplexMode = 'automatic';
let playbackRms = 0;
let playbackReferenceAt = 0;
let candidateTimer: ReturnType<typeof setTimeout> | null = null;
let ducked = false;

export type ResolvedDuplexMode = 'half_duplex' | 'echo_aware';

export function resolveDuplexMode(mode: DuplexMode, echoAwareSupported = true): ResolvedDuplexMode {
  if (mode === 'echo_aware' && echoAwareSupported) return 'echo_aware';
  return 'half_duplex';
}

export function shouldMuteLiveMic(
  speaking: boolean,
  mode: ResolvedDuplexMode = resolveDuplexMode(configuredMode),
): boolean {
  return speaking && mode === 'half_duplex';
}

export function initializeLiveVoiceDuplexGate(): () => void {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return () => undefined;
  const mediaDevices = navigator.mediaDevices;
  if (!mediaDevices?.getUserMedia) return () => undefined;

  configuredMode = readEffectiveLiveConversationProfile()?.duplex_mode ?? 'automatic';
  const originalGetUserMedia = mediaDevices.getUserMedia.bind(mediaDevices);
  const patchedGetUserMedia: typeof mediaDevices.getUserMedia = async (constraints) => {
    const stream = await originalGetUserMedia(constraints);
    if (constraints?.audio && document.querySelector('.assistant-live-card')) trackLiveVoiceStream(stream);
    return stream;
  };
  mediaDevices.getUserMedia = patchedGetUserMedia;

  const handlePlaybackState = (event: Event): void => {
    const detail = (event as CustomEvent<{ speaking?: boolean }>).detail;
    announcedSpeaking = Boolean(detail?.speaking);
    if (!announcedSpeaking) clearCandidate('playback-finished');
    refreshDuplexGate();
  };
  const handleProfile = (event: Event): void => {
    const detail = (event as CustomEvent<LiveConversationProfile>).detail;
    configuredMode = detail?.duplex_mode ?? readEffectiveLiveConversationProfile()?.duplex_mode ?? 'automatic';
    clearCandidate('duplex-mode-changed');
    applyDuplexGate();
  };
  const handlePlaybackPcm = (event: Event): void => {
    const detail = (event as CustomEvent<{ samples?: Int16Array }>).detail;
    if (!(detail?.samples instanceof Int16Array)) return;
    playbackRms = calculatePcm16Rms(detail.samples);
    playbackReferenceAt = performance.now();
  };
  const handleUserSpeech = (event: Event): void => {
    if (!assistantSpeaking || resolveDuplexMode(configuredMode) !== 'echo_aware') return;
    const detail = (event as CustomEvent<{ rms?: number; assistantSpeaking?: boolean }>).detail;
    const microphoneRms = typeof detail?.rms === 'number' ? detail.rms : 0;
    const assessment = assessAcousticBargeIn({
      assistantSpeaking: detail?.assistantSpeaking ?? assistantSpeaking,
      microphoneRms,
      playbackRms,
      playbackReferenceAgeMs: Math.max(0, performance.now() - playbackReferenceAt),
      speechThreshold: 0.012,
    });
    dispatchPerf('barge_in_acoustic_candidate', {
      decision: assessment.decision,
      confidence: assessment.confidence,
      reason: assessment.reason,
      microphone_rms: assessment.microphoneRms,
      playback_rms: assessment.playbackRms,
      energy_ratio: assessment.energyRatio,
    });
    if (assessment.decision === 'likely_echo' || assessment.decision === 'no_playback') return;
    setDucked(true, assessment.reason);
    document.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
      card.dataset.bargeIn = 'confirming';
    });
    if (candidateTimer) window.clearTimeout(candidateTimer);
    candidateTimer = window.setTimeout(() => clearCandidate('candidate-timeout'), CANDIDATE_TIMEOUT_MS);
  };
  const handlePerf = (event: Event): void => {
    const detail = (event as CustomEvent<{ stage?: unknown; intent?: unknown; reason?: unknown }>).detail;
    if (detail?.stage !== 'overlap_classified' || !ducked) return;
    if (detail.intent === 'noise' || detail.intent === 'backchannel' || detail.intent === 'uncertain') {
      clearCandidate(String(detail.reason ?? detail.intent ?? 'candidate-rejected'));
      return;
    }
    document.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
      card.dataset.bargeIn = 'accepted';
    });
  };
  const handleStop = () => clearCandidate('playback-stopped');

  window.addEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
  window.addEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);
  window.addEventListener(PLAYBACK_PCM_EVENT, handlePlaybackPcm);
  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(PERF_EVENT, handlePerf);
  window.addEventListener(INTERRUPT_EVENT, handleStop);
  window.addEventListener(STOP_EVENT, handleStop);

  const observer = new MutationObserver(refreshDuplexGate);
  if (document.body) {
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['data-voice-mode', 'aria-pressed'],
    });
  }
  refreshDuplexGate();

  return () => {
    observer.disconnect();
    window.removeEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
    window.removeEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);
    window.removeEventListener(PLAYBACK_PCM_EVENT, handlePlaybackPcm);
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(PERF_EVENT, handlePerf);
    window.removeEventListener(INTERRUPT_EVENT, handleStop);
    window.removeEventListener(STOP_EVENT, handleStop);
    mediaDevices.getUserMedia = originalGetUserMedia;
    announcedSpeaking = false;
    assistantSpeaking = false;
    configuredMode = 'automatic';
    playbackRms = 0;
    playbackReferenceAt = 0;
    clearCandidate('gate-disposed');
    applyDuplexGate();
    trackedStreams.clear();
  };
}

export function assistantAudioIsActive(root: ParentNode = document): boolean {
  const orbSpeaking = Array.from(root.querySelectorAll<HTMLElement>('.assistant-voice-orb'))
    .some((orb) => orb.dataset.voiceMode === 'speaking');
  const streamSpeaking = Boolean(root.querySelector(STREAM_AUDIO_BUTTON_SELECTOR));
  return announcedSpeaking || orbSpeaking || streamSpeaking;
}

function refreshDuplexGate(): void {
  const speaking = assistantAudioIsActive();
  if (speaking === assistantSpeaking) return;
  assistantSpeaking = speaking;
  applyDuplexGate();
}

function trackLiveVoiceStream(stream: MediaStream): void {
  if (!stream.getAudioTracks().length) return;
  trackedStreams.add(stream);
  for (const track of stream.getAudioTracks()) {
    track.addEventListener('ended', () => {
      if (stream.getAudioTracks().every((candidate) => candidate.readyState === 'ended')) trackedStreams.delete(stream);
    }, { once: true });
  }
  applyDuplexGate();
}

function applyDuplexGate(): void {
  const resolvedMode = resolveDuplexMode(configuredMode);
  const enabled = !shouldMuteLiveMic(assistantSpeaking, resolvedMode);
  for (const stream of Array.from(trackedStreams)) {
    const tracks = stream.getAudioTracks();
    if (!tracks.length || tracks.every((track) => track.readyState === 'ended')) {
      trackedStreams.delete(stream);
      continue;
    }
    for (const track of tracks) track.enabled = enabled;
  }
  document.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
    card.dataset.duplexMode = resolvedMode;
    card.dataset.duplexGate = assistantSpeaking
      ? resolvedMode === 'echo_aware' ? 'echo-aware-listening' : 'assistant-speaking'
      : 'listening';
  });
}

function setDucked(value: boolean, reason: string): void {
  if (ducked === value) return;
  ducked = value;
  window.dispatchEvent(new CustomEvent(DUCK_EVENT, {
    detail: { ducked: value, gain: value ? 0.18 : 1, reason, timestamp: performance.now() },
  }));
  dispatchPerf(value ? 'barge_in_ducked' : 'barge_in_restored', { reason });
}

function clearCandidate(reason: string): void {
  if (candidateTimer) window.clearTimeout(candidateTimer);
  candidateTimer = null;
  setDucked(false, reason);
  document.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
    card.dataset.bargeIn = 'inactive';
  });
}

function dispatchPerf(stage: string, details: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...details },
  }));
}

if (typeof window !== 'undefined') initializeLiveVoiceDuplexGate();
