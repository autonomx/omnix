const PERF_EVENT = 'omnix:assistant-voice-perf';
const PLAYBACK_STATE_EVENT = 'omnix:assistant-audio-playback-state';
const DEFAULT_SUPPRESSION_MS = 800;

type EchoSuppressionWindow = Window & typeof globalThis & {
  __omnixLiveVoiceEchoSuppressionInstalled?: boolean;
};

type AcousticCandidateDetail = {
  stage?: unknown;
  decision?: unknown;
  confidence?: unknown;
  reason?: unknown;
};

let suppressionUntilMs = 0;
let suppressionReason: string | null = null;

export function markPlaybackEchoSuppressed(
  reason = 'playback_echo',
  nowMs = currentTimeMs(),
  durationMs = DEFAULT_SUPPRESSION_MS,
): void {
  suppressionUntilMs = Math.max(suppressionUntilMs, nowMs + Math.max(0, durationMs));
  suppressionReason = reason;
}

export function clearPlaybackEchoSuppression(): void {
  suppressionUntilMs = 0;
  suppressionReason = null;
}

export function isPlaybackEchoSuppressed(nowMs = currentTimeMs()): boolean {
  if (suppressionUntilMs <= nowMs) {
    clearPlaybackEchoSuppression();
    return false;
  }
  return true;
}

export function playbackEchoSuppressionReason(nowMs = currentTimeMs()): string | null {
  return isPlaybackEchoSuppressed(nowMs) ? suppressionReason : null;
}

export function initializePlaybackEchoSuppression(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as EchoSuppressionWindow;
  if (liveWindow.__omnixLiveVoiceEchoSuppressionInstalled) return () => undefined;
  liveWindow.__omnixLiveVoiceEchoSuppressionInstalled = true;

  const handlePerf = (event: Event): void => {
    const detail = (event as CustomEvent<AcousticCandidateDetail>).detail;
    if (detail?.stage !== 'barge_in_acoustic_candidate') return;
    const decision = typeof detail.decision === 'string' ? detail.decision : '';
    const confidence = typeof detail.confidence === 'number' && Number.isFinite(detail.confidence)
      ? detail.confidence
      : 0;
    if (decision === 'likely_echo' && confidence >= 0.8) {
      markPlaybackEchoSuppressed(
        typeof detail.reason === 'string' ? detail.reason : 'playback_echo',
      );
      return;
    }
    if (decision === 'independent_speech') clearPlaybackEchoSuppression();
  };
  const handlePlaybackState = (event: Event): void => {
    const speaking = Boolean((event as CustomEvent<{ speaking?: boolean }>).detail?.speaking);
    if (!speaking) clearPlaybackEchoSuppression();
  };

  window.addEventListener(PERF_EVENT, handlePerf);
  window.addEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
  return () => {
    window.removeEventListener(PERF_EVENT, handlePerf);
    window.removeEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
    clearPlaybackEchoSuppression();
    liveWindow.__omnixLiveVoiceEchoSuppressionInstalled = false;
  };
}

function currentTimeMs(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

initializePlaybackEchoSuppression();
