import type { AssistantSettings, DesktopCompanionRolloutStage } from '../settings/settingsDocumentTypes';

export type DesktopCompanionRolloutStatus = {
  requested_stage: DesktopCompanionRolloutStage;
  effective_stage: DesktopCompanionRolloutStage;
  enabled: boolean;
  reason: string;
  release_gate_status: 'pass' | 'fail' | 'insufficient';
  evidence_evaluation_ids: string[];
};

export type DesktopCompanionRolloutEvidenceIdentity = {
  exactCommitSha: string;
  observationSchemaVersion?: number;
  attentionPolicyVersion?: number;
  visionProvider?: string | null;
  visionModelHash?: string | null;
  remoteProvider?: boolean;
};

export type EffectiveDesktopCompanionSettings = {
  requestedStage: DesktopCompanionRolloutStage;
  enabled: boolean;
  shadowMode: boolean;
  textEnabled: boolean;
  speechEnabled: boolean;
  visionModelId: string;
  remoteVisionAllowed: boolean;
  showDiagnostics: boolean;
  backgroundCallsPerMinute: number;
  minimumObservationIntervalMs: number;
  observationTimeoutMs: number;
  observationTtlMs: number;
  commentaryCooldownMs: number;
  minimumChangeConfidence: number;
};

export function effectiveDesktopCompanionSettings(value: AssistantSettings): EffectiveDesktopCompanionSettings {
  const requestedStage = value.desktopCompanionEnabled ? value.desktopCompanionRolloutStage : 'disabled';
  return {
    requestedStage,
    enabled: requestedStage !== 'disabled',
    shadowMode: requestedStage === 'shadow',
    textEnabled: requestedStage === 'text' || requestedStage === 'speech',
    speechEnabled: requestedStage === 'speech' && value.autoSpeakReplies,
    visionModelId: value.desktopCompanionVisionModelId.trim(),
    remoteVisionAllowed: value.desktopCompanionRemoteVisionAllowed,
    showDiagnostics: value.desktopCompanionShowDiagnostics,
    backgroundCallsPerMinute: clampInt(value.desktopCompanionBackgroundCallsPerMinute, 1, 30),
    minimumObservationIntervalMs: clampInt(value.desktopCompanionMinimumObservationIntervalMs, 2_000, 120_000),
    observationTimeoutMs: clampInt(value.desktopCompanionObservationTimeoutMs, 1_000, 60_000),
    observationTtlMs: clampInt(value.desktopCompanionObservationTtlMs, 2_000, 120_000),
    commentaryCooldownMs: clampInt(value.desktopCompanionCommentaryCooldownMs, 5_000, 300_000),
    minimumChangeConfidence: clamp(value.desktopCompanionMinimumChangeConfidence, 0, 1),
  };
}

export async function fetchDesktopCompanionRolloutStatus(
  stage: DesktopCompanionRolloutStage,
  identity?: DesktopCompanionRolloutEvidenceIdentity,
  signal?: AbortSignal,
): Promise<DesktopCompanionRolloutStatus> {
  const params = new URLSearchParams({ requested_stage: stage });
  if (identity) {
    params.set('exact_commit_sha', identity.exactCommitSha);
    params.set('observation_schema_version', String(identity.observationSchemaVersion ?? 1));
    params.set('attention_policy_version', String(identity.attentionPolicyVersion ?? 1));
    if (identity.visionProvider) params.set('vision_provider', identity.visionProvider);
    if (identity.visionModelHash) params.set('vision_model_hash', identity.visionModelHash);
    params.set('remote_provider', String(identity.remoteProvider === true));
  }
  const response = await fetch(`/api/desktop-companion/rollout-status?${params}`, { signal });
  if (!response.ok) throw new Error(`Desktop Companion rollout status failed with status ${response.status}.`);
  return response.json() as Promise<DesktopCompanionRolloutStatus>;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, Number.isFinite(value) ? value : minimum));
}

function clampInt(value: number, minimum: number, maximum: number): number {
  return Math.round(clamp(value, minimum, maximum));
}
