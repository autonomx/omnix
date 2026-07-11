export type AcousticBargeInDecision = 'independent_speech' | 'likely_echo' | 'uncertain' | 'no_playback';

export type AcousticBargeInInput = {
  assistantSpeaking: boolean;
  microphoneRms: number;
  playbackRms: number;
  playbackReferenceAgeMs: number;
  speechThreshold: number;
};

export type AcousticBargeInAssessment = {
  decision: AcousticBargeInDecision;
  confidence: number;
  reason: string;
  microphoneRms: number;
  playbackRms: number;
  energyRatio: number | null;
};

const MAX_REFERENCE_AGE_MS = 750;
const MIN_REFERENCE_RMS = 0.002;

export function calculatePcm16Rms(samples: Int16Array): number {
  if (!samples.length) return 0;
  let sum = 0;
  for (const sample of samples) {
    const normalized = sample / 32768;
    sum += normalized * normalized;
  }
  return Math.sqrt(sum / samples.length);
}

export function assessAcousticBargeIn(input: AcousticBargeInInput): AcousticBargeInAssessment {
  const microphoneRms = finiteNonNegative(input.microphoneRms);
  const playbackRms = finiteNonNegative(input.playbackRms);
  const referenceAge = finiteNonNegative(input.playbackReferenceAgeMs);
  const threshold = Math.max(0.001, finiteNonNegative(input.speechThreshold));
  const energyRatio = playbackRms > 0 ? microphoneRms / playbackRms : null;

  if (!input.assistantSpeaking) {
    return assessment('no_playback', 1, 'assistant_not_speaking', microphoneRms, playbackRms, energyRatio);
  }
  if (microphoneRms < threshold) {
    return assessment('likely_echo', 0.85, 'below_user_speech_threshold', microphoneRms, playbackRms, energyRatio);
  }
  if (referenceAge > MAX_REFERENCE_AGE_MS || playbackRms < MIN_REFERENCE_RMS) {
    return assessment('independent_speech', 0.74, 'no_recent_playback_reference', microphoneRms, playbackRms, energyRatio);
  }
  if (energyRatio !== null && energyRatio <= 0.48) {
    return assessment('likely_echo', 0.82, 'microphone_energy_tracks_playback', microphoneRms, playbackRms, energyRatio);
  }
  if (energyRatio !== null && energyRatio >= 0.9) {
    return assessment('independent_speech', 0.8, 'microphone_energy_exceeds_echo_envelope', microphoneRms, playbackRms, energyRatio);
  }
  return assessment('uncertain', 0.5, 'candidate_requires_partial_stt', microphoneRms, playbackRms, energyRatio);
}

function assessment(
  decision: AcousticBargeInDecision,
  confidence: number,
  reason: string,
  microphoneRms: number,
  playbackRms: number,
  energyRatio: number | null,
): AcousticBargeInAssessment {
  return { decision, confidence, reason, microphoneRms, playbackRms, energyRatio };
}

function finiteNonNegative(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}
