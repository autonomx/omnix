import { readLiveConversationEvaluationSnapshot } from './live-conversation-evaluation-controller';
import { liveConversationStore } from './live-conversation-store';
import {
  liveChatEvaluationClient,
  type VoiceSessionEvaluationCreate,
} from './live-chat-evaluation-client';

export const LIVE_DURABLE_EVALUATION_SAVED_EVENT = 'omnix:live-conversation-durable-evaluation-saved';
const CALL_START_EVENT = 'omnix:assistant-live-voice-call-start';
const STOP_EVENT = 'omnix:assistant-live-voice-stop';
const PERF_EVENT = 'omnix:assistant-voice-perf';
const RELEASE_SCENARIO_KEY = 'omnix.liveCall.releaseScenario';

type DurableEvaluationWindow = Window & typeof globalThis & {
  __omnixLiveDurableEvaluationInstalled?: boolean;
};

type ActiveCall = {
  callId: string;
  startedAt: string;
  eosTerminationCounts: Record<string, number>;
};

let activeCall: ActiveCall | null = null;

export function initializeLiveConversationDurableEvaluationController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as DurableEvaluationWindow;
  if (liveWindow.__omnixLiveDurableEvaluationInstalled) return () => undefined;
  liveWindow.__omnixLiveDurableEvaluationInstalled = true;

  const handleStart = () => {
    activeCall = {
      callId: createCallId(),
      startedAt: new Date().toISOString(),
      eosTerminationCounts: {
        natural_eos: 0,
        forced_eos: 0,
        token_limit: 0,
        sequence_limit: 0,
        model_stopped: 0,
      },
    };
  };
  const handlePerf = (event: Event) => {
    if (!activeCall) return;
    const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
    const reason = terminationReason(detail);
    if (reason && Object.hasOwn(activeCall.eosTerminationCounts, reason)) {
      activeCall.eosTerminationCounts[reason] += 1;
    }
  };
  const handleStop = () => {
    const call = activeCall;
    activeCall = null;
    if (!call) return;
    void persistCallEvaluation(call);
  };

  window.addEventListener(CALL_START_EVENT, handleStart);
  window.addEventListener(PERF_EVENT, handlePerf);
  window.addEventListener(STOP_EVENT, handleStop);

  return () => {
    window.removeEventListener(CALL_START_EVENT, handleStart);
    window.removeEventListener(PERF_EVENT, handlePerf);
    window.removeEventListener(STOP_EVENT, handleStop);
    activeCall = null;
    liveWindow.__omnixLiveDurableEvaluationInstalled = false;
  };
}

export function buildDurableEvaluationPayload(
  call: ActiveCall,
  endedAt = new Date().toISOString(),
): VoiceSessionEvaluationCreate {
  const runtime = liveConversationStore.getState();
  const report = readLiveConversationEvaluationSnapshot().report;
  const calibration = runtime.duplex.calibration;
  return {
    call_id: call.callId,
    session_id: runtime.sessionId,
    started_at: call.startedAt,
    ended_at: endedAt,
    exact_commit_sha: currentCommitSha(),
    app_version: currentAppVersion(),
    character_id: runtime.identity.characterId,
    profile_version: runtime.identity.profileVersion,
    presence_preset: runtime.profile?.presence_preset ?? 'natural',
    conversation_stance: runtime.profile?.conversation_stance ?? 'automatic',
    configured_duplex_mode: runtime.duplex.configuredMode,
    resolved_duplex_mode: runtime.duplex.resolvedMode,
    calibration_version: calibration?.version ?? null,
    input_device_hash: calibration?.deviceKey ?? null,
    output_device_hash: calibration?.deviceKey ?? null,
    environment_hash: calibration ? environmentHash(calibration) : null,
    latency_summary: {
      first_audio_average_ms: report.firstAudioLatencyMs.average,
      first_audio_p95_ms: report.firstAudioLatencyMs.p95,
      cancellation_average_ms: report.cancellationLatencyMs.average,
      cancellation_p95_ms: report.cancellationLatencyMs.p95,
      turn_duration_median_ms: report.turnDurationMs.median,
      turn_duration_p95_ms: report.turnDurationMs.p95,
    },
    quality_metrics: {
      event_count: report.eventCount,
      false_endpoint_rate: report.falseEndpointRate,
      talk_over_duration_ms: report.talkOverDurationMs,
      interruption_success_rate: report.interruptionSuccessRate,
      silence_fill_regret_rate: report.silenceFillRegretRate,
      proactive_acceptance_rate: report.proactiveAcceptanceRate,
      backchannel_collision_rate: report.backchannelCollisionRate,
      question_density: report.questionDensity,
      assistant_user_speaking_ratio: report.assistantUserSpeakingRatio,
      repair_success_rate: report.repairSuccessRate,
      repeated_topic_rate: report.repeatedTopicRate,
      unanswered_obligation_rate: report.unansweredObligationRate,
      perceived_listening_score: report.perceivedListeningScore,
      perceived_pressure_score: report.perceivedPressureScore,
    },
    eos_termination_counts: { ...call.eosTerminationCounts },
    scenario_labels: currentScenarioLabels(),
    release_gate_status: 'insufficient',
    listening_score: report.perceivedListeningScore,
    pressure_score: report.perceivedPressureScore,
  };
}

async function persistCallEvaluation(call: ActiveCall): Promise<void> {
  try {
    const record = await liveChatEvaluationClient.upsert(buildDurableEvaluationPayload(call));
    window.dispatchEvent(new CustomEvent(LIVE_DURABLE_EVALUATION_SAVED_EVENT, { detail: record }));
  } catch (error) {
    window.dispatchEvent(new CustomEvent(PERF_EVENT, {
      detail: {
        stage: 'durable_evaluation_save_failed',
        error_name: error instanceof Error ? error.name : 'unknown',
        timestamp: new Date().toISOString(),
      },
    }));
  }
}

function terminationReason(detail: Record<string, unknown>): string {
  const direct = detail.termination_reason;
  if (typeof direct === 'string') return direct;
  const timing = detail.provider_timing;
  if (timing && typeof timing === 'object' && typeof (timing as Record<string, unknown>).termination_reason === 'string') {
    return String((timing as Record<string, unknown>).termination_reason);
  }
  return '';
}

function createCallId(): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `live-call:${suffix}`;
}

function currentCommitSha(): string {
  const value = document.querySelector<HTMLMetaElement>('meta[name="omnix-commit-sha"]')?.content
    || document.documentElement.dataset.commitSha
    || 'unknown0';
  return value.trim().slice(0, 64) || 'unknown0';
}

function currentAppVersion(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="omnix-app-version"]')?.content
    || document.documentElement.dataset.appVersion
    || 'unknown';
}

function currentScenarioLabels(): string[] {
  const raw = window.localStorage.getItem(RELEASE_SCENARIO_KEY) ?? '';
  return raw.split(',')
    .map((value) => value.trim().toLocaleLowerCase())
    .filter((value) => /^[a-z0-9_.:-]{1,160}$/.test(value))
    .slice(0, 64);
}

function environmentHash(calibration: { deviceKey: string; confidence: number; delayMs: number; noiseFloorRms: number }): string {
  const source = `${calibration.deviceKey}|${calibration.confidence.toFixed(3)}|${calibration.delayMs.toFixed(1)}|${calibration.noiseFloorRms.toFixed(5)}`;
  let hash = 2166136261;
  for (const character of source) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `environment-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
