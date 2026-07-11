import { createLiveCallDiagnosticsReporter } from './live-call-diagnostics-client';

const PERF_EVENT = 'omnix:assistant-voice-perf';
const DIAGNOSTIC_EVENT = 'omnix:live-call-diagnostic';
const INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const QUALITY_EVENT = 'omnix:assistant-voice-release-quality';
const SCENARIO_KEY = 'omnix.liveCall.releaseScenario';
export const LIVE_VOICE_RELEASE_OBSERVATION_EVENT = 'omnix:live-voice-release-observation';

export type LiveVoiceLatencyMetric =
  | 'stt_finalize_ms'
  | 'final_to_first_token_ms'
  | 'first_token_to_first_audio_ms'
  | 'interruption_to_silence_ms';

export type LiveVoiceQualityMetric =
  | 'false_interruption'
  | 'missed_interruption'
  | 'backchannel_false_positive'
  | 'playback_echo_submission';

export type LiveVoiceReleaseObservation =
  | { kind: 'latency'; metricName: LiveVoiceLatencyMetric; valueMs: number; scenario: string }
  | { kind: 'quality'; qualityName: LiveVoiceQualityMetric; occurred: boolean; scenario: string };

type PerfDetail = {
  stage?: unknown;
  turnId?: unknown;
  sttFinalizeMs?: unknown;
};

type DiagnosticDetail = {
  traceId?: unknown;
  source?: unknown;
  event?: unknown;
  details?: Record<string, unknown>;
};

type QualityDetail = {
  qualityName?: unknown;
  occurred?: unknown;
  scenario?: unknown;
};

type ReleaseState = {
  sttRequestedAt: number | null;
  sttFinalAt: number | null;
  firstTokenAt: number | null;
  firstAudioAt: number | null;
  interruptionAt: number | null;
  turnId: string | null;
  activeTraceId: string | null;
};

const reporter = typeof window === 'undefined'
  ? null
  : createLiveCallDiagnosticsReporter('live-call:release-observer');
let initialized = false;
let state: ReleaseState = emptyState();

export function initializeLiveVoiceReleaseObserver(): void {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;
  window.addEventListener(PERF_EVENT, handlePerfEvent);
  window.addEventListener(DIAGNOSTIC_EVENT, handleDiagnosticEvent);
  window.addEventListener(INTERRUPT_EVENT, handleInterruption);
  window.addEventListener(QUALITY_EVENT, handleQualityEvent);
}

export function recordLiveVoiceReleaseQuality(
  qualityName: LiveVoiceQualityMetric,
  occurred: boolean,
  scenario = currentScenario(),
): void {
  reporter?.record('release_quality', {
    quality_name: qualityName,
    occurred,
    scenario,
  }, 'release_observer');
  dispatchObservation({ kind: 'quality', qualityName, occurred, scenario });
}

export function resetLiveVoiceReleaseObserver(): void {
  state = emptyState();
}

function handlePerfEvent(event: Event): void {
  const detail = (event as CustomEvent<PerfDetail>).detail ?? {};
  const stage = typeof detail.stage === 'string' ? detail.stage : '';
  const now = performance.now();
  if (stage === 'stt_final_requested') {
    state = {
      ...emptyState(),
      sttRequestedAt: now,
      turnId: typeof detail.turnId === 'string' ? detail.turnId : null,
    };
    return;
  }
  if (stage === 'stt_final_received') {
    const observed = finiteNonnegative(detail.sttFinalizeMs)
      ?? elapsed(state.sttRequestedAt, now);
    recordLatency('stt_finalize_ms', observed);
    state.sttFinalAt = now;
    if (typeof detail.turnId === 'string') state.turnId = detail.turnId;
  }
}

function handleDiagnosticEvent(event: Event): void {
  const detail = (event as CustomEvent<DiagnosticDetail>).detail ?? {};
  const diagnosticEvent = typeof detail.event === 'string' ? detail.event : '';
  const traceId = typeof detail.traceId === 'string' ? detail.traceId : null;
  if (!traceId || traceId === 'live-call:release-observer') return;
  const now = performance.now();

  if (diagnosticEvent === 'turn_intercepted') {
    state.activeTraceId = traceId;
    return;
  }
  if (state.activeTraceId && traceId !== state.activeTraceId) return;
  if (diagnosticEvent === 'llm_text_chunk_received' && state.firstTokenAt === null) {
    state.firstTokenAt = now;
    recordLatency('final_to_first_token_ms', elapsed(state.sttFinalAt, now));
    return;
  }
  if (diagnosticEvent === 'phrase_first_frame_received' && state.firstAudioAt === null) {
    state.firstAudioAt = now;
    recordLatency('first_token_to_first_audio_ms', elapsed(state.firstTokenAt, now));
    return;
  }
  if (diagnosticEvent === 'turn_stopped' && state.interruptionAt !== null) {
    recordLatency('interruption_to_silence_ms', elapsed(state.interruptionAt, now));
    state.interruptionAt = null;
  }
}

function handleInterruption(): void {
  state.interruptionAt = performance.now();
}

function handleQualityEvent(event: Event): void {
  const detail = (event as CustomEvent<QualityDetail>).detail ?? {};
  const qualityName = detail.qualityName;
  if (!isQualityMetric(qualityName) || typeof detail.occurred !== 'boolean') return;
  recordLiveVoiceReleaseQuality(
    qualityName,
    detail.occurred,
    typeof detail.scenario === 'string' ? detail.scenario : currentScenario(),
  );
}

function recordLatency(metricName: LiveVoiceLatencyMetric, valueMs: number | null): void {
  if (valueMs === null) return;
  const rounded = Math.round(valueMs * 1000) / 1000;
  const scenario = currentScenario();
  reporter?.record('release_metric', {
    metric_name: metricName,
    value_ms: rounded,
    scenario,
    turn_id: state.turnId,
    observed_trace_id: state.activeTraceId,
  }, 'release_observer');
  dispatchObservation({ kind: 'latency', metricName, valueMs: rounded, scenario });
}

function dispatchObservation(observation: LiveVoiceReleaseObservation): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, { detail: observation }));
}

function elapsed(start: number | null, end: number): number | null {
  return start === null ? null : Math.max(0, end - start);
}

function finiteNonnegative(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function currentScenario(): string {
  try {
    const value = window.localStorage.getItem(SCENARIO_KEY)?.trim();
    return value || 'unlabeled';
  } catch {
    return 'unlabeled';
  }
}

function isQualityMetric(value: unknown): value is LiveVoiceQualityMetric {
  return value === 'false_interruption'
    || value === 'missed_interruption'
    || value === 'backchannel_false_positive'
    || value === 'playback_echo_submission';
}

function emptyState(): ReleaseState {
  return {
    sttRequestedAt: null,
    sttFinalAt: null,
    firstTokenAt: null,
    firstAudioAt: null,
    interruptionAt: null,
    turnId: null,
    activeTraceId: null,
  };
}

initializeLiveVoiceReleaseObserver();
