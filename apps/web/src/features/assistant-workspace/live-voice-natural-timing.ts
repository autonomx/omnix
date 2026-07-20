import type { SilenceReason } from './live-voice-playback-contract';

export type NaturalPause = {
  durationMs: number;
  reason: SilenceReason;
};

export type OnsetTimingPlan = {
  desiredPerceivedOnsetMs: number;
  elapsedMs: number;
  extraDelayMs: number;
};

const SERIOUS_PATTERN = /\b(?:sorry|grief|loss|afraid|hurt|serious|difficult|take your time)\b/i;
const REFLECTION_PATTERN = /\b(?:i think|perhaps|maybe|on balance|the tradeoff|looking at this)\b/i;

export function createOnsetTimingPlan(
  elapsedMs: number,
  options: {
    desiredPerceivedOnsetMs?: number;
    maximumAdditionalDelayMs?: number;
    urgent?: boolean;
  } = {},
): OnsetTimingPlan {
  const desired = Math.max(0, options.desiredPerceivedOnsetMs ?? 450);
  const maximum = Math.max(0, options.maximumAdditionalDelayMs ?? 350);
  const elapsed = Math.max(0, Number.isFinite(elapsedMs) ? elapsedMs : 0);
  const extraDelayMs = options.urgent
    ? 0
    : Math.min(maximum, Math.max(0, desired - elapsed));
  return {
    desiredPerceivedOnsetMs: desired,
    elapsedMs: elapsed,
    extraDelayMs: Math.round(extraDelayMs),
  };
}

export function naturalPauseAfterClause(text: string, sequence: number): NaturalPause | null {
  const normalized = text.trim();
  if (!normalized) return null;
  if (SERIOUS_PATTERN.test(normalized) || REFLECTION_PATTERN.test(normalized)) {
    return {
      durationMs: deterministicRange(normalized, sequence, 280, 420),
      reason: 'reflection',
    };
  }
  if (/[:;][\]})"'’”]*$/.test(normalized)) {
    return {
      durationMs: deterministicRange(normalized, sequence, 150, 240),
      reason: 'thought',
    };
  }
  if (/[.!?][\]})"'’”]*$/.test(normalized)) {
    return {
      durationMs: deterministicRange(normalized, sequence, 80, 140),
      reason: 'clause',
    };
  }
  return null;
}

function deterministicRange(text: string, sequence: number, minimum: number, maximum: number): number {
  let hash = sequence + 17;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash * 31) + text.charCodeAt(index)) >>> 0;
  }
  const span = Math.max(0, maximum - minimum);
  return minimum + (span ? hash % (span + 1) : 0);
}
