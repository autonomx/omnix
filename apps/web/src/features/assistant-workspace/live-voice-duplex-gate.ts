import {
  LIVE_CONVERSATION_PROFILE_CHANGED_EVENT,
  readEffectiveLiveConversationProfile,
  type DuplexMode,
  type LiveConversationProfile,
} from '../chatbot/liveConversationProfileClient';
import { assessAcousticBargeIn, calculatePcm16Rms } from './live-voice-barge-in-detector';
import {
  LIVE_VOICE_CALIBRATION_UPDATED_EVENT,
  readLatestLiveVoiceCalibration,
  resolveCalibrationDuplex,
  type LiveVoiceCalibrationRecord,
} from './live-voice-calibration';
import { liveConversationStore } from './live-conversation-store';

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
let activeCalibration: LiveVoiceCalibrationRecord | null = null;
let playbackRms = 0;
let playbackReferenceAt = 0;
let candidateTimer: ReturnType<typeof setTimeout> | null = null;
let ducked = false;

export type ResolvedDuplexMode = 'half_duplex' | 'echo_aware';

export function resolveDuplexMode(
  mode: DuplexMode,
  echoAwareSupported = true,
  calibration: LiveVoiceCalibrationRecord | null = readLatestLiveVoiceCalibration(),
): ResolvedDuplexMode {
  if (!echoAwareSupported || mode === 'half_duplex') return 'half_duplex';
  if (mode === 'echo_aware') return 'echo_aware';
  return resolveCalibrationDuplex(calibration).mode;
}

export function shouldMuteLiveMic(
  speaking: boolean,
  mode: ResolvedDuplexMode = resolveDuplexMode(configuredMode, true, activeCalibration),
): boolean {
  return speaking && mode === 'half_duplex';
}

export function initializeLiveVoiceDuplexGate(): () => void {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return () => undefined;
  const mediaDevices = navigator.mediaDevices;
  if (!mediaDevices?.getUserMedia) return () => undefined;

  configuredMode = readEffectiveLiveConversationProfile()?.duplex_mode ?? 'automatic';
  activeCalibration = readLatestLiveVoiceCalibration();
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
    assistantSpeaking = announcedSpeaking;
    if (!assistantSpeaking) clearCandidate('playback-finished');
    applyDuplexGate();
  };
  const handleProfile = (event: Event): void => {
    const detail = (event as CustomEvent<LiveConversationProfile>).detail;
    configuredMode = detail?.duplex_mode ?? readEffectiveLiveConversationProfile()?.duplex_mode ?? 'automatic';
    liveConversationStore.dispatch({ type: 'profile', profile: detail ?? readEffectiveLiveConversationProfile() });
    clearCandidate('duplex-mode-changed');
    applyDuplexGate();
  };
  const handleCalibration = (event: Event): void => {
    activeCalibration = (event as CustomEvent<LiveVoiceCalibrationRecord>).detail
      ?? readLatestLiveVoiceCalibration();
    clearCandidate('calibration-updated');
    applyDuplexGate();
  };
  const handlePlaybackPcm = (event: Event): void => {
    const detail = (event as CustomEvent<{ samples?: Int16Array }>).detail;
    if (!(detail?.samples instanceof Int16Array)) return;
    playbackRms = calculatePcm16Rms(detail.samples);
    playbackReferenceAt = performance.now();
  };
  const handleUserSpeech = (event: Event): void => {
    if (!assistantSpeaking || resolveDuplexMode(configuredMode, true, activeCalibration) !== 'echo_aware') return;
    const detail = (event as CustomEvent<{ rms?: number; assistantSpeaking?: boolean }>).detail;
    const microphoneRms = typeof detail?.rms === 'number' ? detail.rms : 0;
    const assessment = assessAcousticBargeIn({
      assistantSpeaking: detail?.assistantSpeaking ?? assistantSpeaking,
      microphoneRms,
      playbackRms,
      playbackReferenceAgeMs: Math.max(0, performance.now() - playbackReferenceAt),
      speechThreshold: adaptiveSpeechThreshold(activeCalibration),
    });
    dispatchPerf('barge_in_acoustic_candidate', {
      decision: assessment.decision,
      confidence: assessment.confidence,
      reason: assessment.reason,
      microphone_rms: assessment.microphoneRms,
      playback_rms: assessment.playbackRms,
      energy_ratio: assessment.energyRatio,
      calibration_confidence: activeCalibration?.confidence ?? 0,
    });
    if (assessment.decision === 'likely_echo' || assessment.decision === 'no_playback') return;
    setDucked(true, assessment.reason);
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'barge_in', value: 'confirming' } });
    projectBargeIn('confirming');
    if (candidateTimer) window.clearTimeout(candidateTimer);
    candidateTimer = window.setTimeout(() => clearCandidate('candidate-timeout'), CANDIDATE_TIMEOUT_MS);
  };
  const handlePerf = (event: Event): void => {
    const detail = (event as CustomEvent<{ stage?: unknown; intent?: unknown; reason?: unknown }>).detail;
    if (detail?.stage !== 'overlap_classified' || !ducked) return;
    if (detail.intent === 'noise' || detail.intent === 'backchannel' || detail.intent === 'uncertain') {
      liveConversationStore.dispatch({ type: 'conversation', event: { type: 'barge_in', value: 'rejected' } });
      clearCandidate(String(detail.reason ?? detail.intent ?? 'candidate-rejected'));
      return;
    }
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'barge_in', value: 'accepted' } });
    projectBargeIn('accepted');
  };
  const handleStop = () => clearCandidate('playback-stopped');

  window.addEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
  window.addEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);
  window.addEventListener(LIVE_VOICE_CALIBRATION_UPDATED_EVENT, handleCalibration);
  window.addEventListener(PLAYBACK_PCM_EVENT, handlePlaybackPcm);
  window.addEventListener(USER_SPEECH_EVENT, handleUserSpeech);
  window.addEventListener(PERF_EVENT, handlePerf);
  window.addEventListener(INTERRUPT_EVENT, handleStop);
  window.addEventListener(STOP_EVENT, handleStop);
  applyDuplexGate();

  return () => {
    window.removeEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
    window.removeEventListener(LIVE_CONVERSATION_PROFILE_CHANGED_EVENT, handleProfile);
    window.removeEventListener(LIVE_VOICE_CALIBRATION_UPDATED_EVENT, handleCalibration);
    window.removeEventListener(PLAYBACK_PCM_EVENT, handlePlaybackPcm);
    window.removeEventListener(USER_SPEECH_EVENT, handleUserSpeech);
    window.removeEventListener(PERF_EVENT, handlePerf);
    window.removeEventListener(INTERRUPT_EVENT, handleStop);
    window.removeEventListener(STOP_EVENT, handleStop);
    mediaDevices.getUserMedia = originalGetUserMedia;
    announcedSpeaking = false;
    assistantSpeaking = false;
    configuredMode = 'automatic';
    activeCalibration = null;
    playbackRms = 0;
    playbackReferenceAt = 0;
    clearCandidate('gate-disposed');
    trackedStreams.clear();
  };
}

/** Compatibility-only inspection helper. Duplex policy itself is event/store-driven. */
export function assistantAudioIsActive(root: ParentNode = document): boolean {
  const orbSpeaking = Array.from(root.querySelectorAll<HTMLElement>('.assistant-voice-orb'))
    .some((orb) => orb.dataset.voiceMode === 'speaking');
  const streamSpeaking = Boolean(root.querySelector(STREAM_AUDIO_BUTTON_SELECTOR));
  return announcedSpeaking || orbSpeaking || streamSpeaking;
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
  const resolvedMode = resolveDuplexMode(configuredMode, true, activeCalibration);
  const calibration = resolveCalibrationDuplex(activeCalibration);
  const reason = configuredMode === 'automatic' ? calibration.reason : 'explicit_user_selection';
  const confidence = activeCalibration?.confidence ?? 0;
  liveConversationStore.dispatch({
    type: 'duplex',
    duplex: {
      configuredMode,
      resolvedMode,
      reason,
      confidence,
      calibration: activeCalibration,
    },
  });
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
    card.dataset.duplexReason = reason;
    card.dataset.calibrationConfidence = String(confidence);
    card.dataset.duplexGate = assistantSpeaking
      ? resolvedMode === 'echo_aware' ? 'echo-aware-listening' : 'assistant-speaking'
      : 'listening';
  });
}

function adaptiveSpeechThreshold(calibration: LiveVoiceCalibrationRecord | null): number {
  if (!calibration) return 0.012;
  return Math.max(0.008, Math.min(0.08, calibration.noiseFloorRms * 2.6));
}

function setDucked(value: boolean, reason: string): void {
  if (ducked === value) return;
  ducked = value;
  liveConversationStore.dispatch({
    type: 'conversation',
    event: { type: 'barge_in', value: value ? 'ducking' : 'inactive' },
  });
  window.dispatchEvent(new CustomEvent(DUCK_EVENT, {
    detail: { ducked: value, gain: value ? 0.18 : 1, reason, timestamp: performance.now() },
  }));
  dispatchPerf(value ? 'barge_in_ducked' : 'barge_in_restored', { reason });
}

function clearCandidate(reason: string): void {
  if (candidateTimer) window.clearTimeout(candidateTimer);
  candidateTimer = null;
  setDucked(false, reason);
  projectBargeIn('inactive');
}

function projectBargeIn(value: string): void {
  document.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
    card.dataset.bargeIn = value;
  });
}

function dispatchPerf(stage: string, details: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...details },
  }));
}

if (typeof window !== 'undefined') initializeLiveVoiceDuplexGate();
