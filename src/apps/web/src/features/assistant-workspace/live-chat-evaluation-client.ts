import type { components } from '../../api/generated/types';
export type PresencePreset = 'quiet' | 'natural' | 'engaged' | 'listener';
export type ReleaseGateStatus = 'pass' | 'fail' | 'insufficient';

export type VoiceSessionEvaluationCreate = components['schemas']['VoiceSessionEvaluationCreate'];

export type VoiceSessionEvaluationRecord = components['schemas']['VoiceSessionEvaluationRecord'];

export type PresencePolicyValues = components['schemas']['PresencePolicyValues'];

export type PresencePolicyVersion = components['schemas']['PresencePolicyVersion'];

export type LiveChatReleaseMetric = {
  name: string;
  kind: 'latency' | 'rate' | 'score';
  status: ReleaseGateStatus;
  samples: number;
  observed: number | null;
  limit: number;
  comparison: 'maximum' | 'minimum';
};

export type LiveChatReleaseGateReport = components['schemas']['LiveChatReleaseGateReport'];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Live Chat evaluation request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    ...(body === undefined ? {} : {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  };
}

export const liveChatEvaluationClient = {
  upsert(input: VoiceSessionEvaluationCreate): Promise<VoiceSessionEvaluationRecord> {
    return request('/api/tts/live-call/evaluations', jsonInit('POST', input));
  },
  list(options: { sessionId?: string | null; preset?: PresencePreset | null; limit?: number } = {}): Promise<VoiceSessionEvaluationRecord[]> {
    const params = new URLSearchParams();
    if (options.sessionId) params.set('session_id', options.sessionId);
    if (options.preset) params.set('presence_preset', options.preset);
    params.set('limit', String(options.limit ?? 100));
    return request(`/api/tts/live-call/evaluations?${params}`);
  },
  releaseGate(options: { limit?: number; persistStatus?: boolean } = {}): Promise<LiveChatReleaseGateReport> {
    const params = new URLSearchParams({
      limit: String(options.limit ?? 1_000),
      persist_status: String(options.persistStatus ?? true),
    });
    return request(`/api/tts/live-call/evaluations/release-gate?${params}`);
  },
  export(): Promise<Record<string, unknown>> {
    return request('/api/tts/live-call/evaluations/export');
  },
  activePolicies(): Promise<Record<PresencePreset, PresencePolicyVersion>> {
    return request('/api/tts/live-call/presence-presets');
  },
  policyVersions(preset?: PresencePreset): Promise<PresencePolicyVersion[]> {
    return request(`/api/tts/live-call/presence-presets/versions${preset ? `?preset=${preset}` : ''}`);
  },
  createPolicyVersion(
    preset: PresencePreset,
    input: { values: PresencePolicyValues; reason: string; evidence_evaluation_ids: string[] },
  ): Promise<PresencePolicyVersion> {
    return request(`/api/tts/live-call/presence-presets/${preset}/versions`, jsonInit('POST', input));
  },
  activatePolicy(preset: PresencePreset, version: number): Promise<PresencePolicyVersion> {
    return request(`/api/tts/live-call/presence-presets/${preset}/activate/${version}`, jsonInit('POST'));
  },
  rollbackPolicy(preset: PresencePreset): Promise<PresencePolicyVersion> {
    return request(`/api/tts/live-call/presence-presets/${preset}/rollback`, jsonInit('POST'));
  },
};

export function suggestPresencePolicy(
  active: PresencePolicyVersion,
  evaluations: VoiceSessionEvaluationRecord[],
): PresencePolicyValues {
  const matching = evaluations.filter((record) => record.presence_preset === active.preset);
  const average = (key: string): number | null => {
    const values = matching
      .map((record) => record.quality_metrics[key])
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  };
  const regret = average('silence_fill_regret_rate');
  const collision = average('backchannel_collision_rate');
  const pressure = average('perceived_pressure_score');
  const listening = average('perceived_listening_score');
  const values = active.values;
  const higherPressure = (pressure ?? 0) > 2.5 || (regret ?? 0) > 0.1;
  const lowerListening = listening !== null && listening < 3.5;
  const collisionRisk = (collision ?? 0) > 0.05;
  return {
    silence_tolerance_ms: clampInt(values.silence_tolerance_ms + (higherPressure ? 2_000 : lowerListening ? -1_000 : 0), 5_000, 120_000),
    initiative_threshold_ms: clampInt(values.initiative_threshold_ms + (higherPressure ? 3_000 : lowerListening ? -1_000 : 0), 5_000, 120_000),
    initiative_cooldown_ms: clampInt(values.initiative_cooldown_ms + (higherPressure ? 5_000 : 0), 5_000, 300_000),
    listener_backchannel_frequency: clamp(values.listener_backchannel_frequency + (collisionRisk ? -0.03 : lowerListening ? 0.02 : 0), 0, 1),
    typical_turn_words: clampInt(values.typical_turn_words + (higherPressure ? -5 : lowerListening ? 5 : 0), 8, 240),
    interruption_sensitivity: clamp(values.interruption_sensitivity + (lowerListening ? 0.03 : 0), 0, 1),
    response_onset_ms: clampInt(values.response_onset_ms + (higherPressure ? 120 : 0), 0, 5_000),
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Number(Math.max(minimum, Math.min(maximum, value)).toFixed(3));
}

function clampInt(value: number, minimum: number, maximum: number): number {
  return Math.round(clamp(value, minimum, maximum));
}
