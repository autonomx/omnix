import {
  LIVE_STT_SPECULATION_CANDIDATE_EVENT,
  LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT,
  LIVE_STT_SPECULATION_FINAL_EVENT,
  LIVE_STT_SPECULATION_PARTIAL_EVENT,
} from './live-stt-authority-controller';

const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const INSTALLED_KEY = '__omnixLiveSpeculationEligibilityDiagnosticsInstalled';
const CORRECTION_PATTERN = /(?:^|\s)(?:uh+|um+|erm+|wait|sorry|actually|correction|no[,. ]+i mean)(?:\s|$)/i;
const WORD_PATTERN = /[\p{L}\p{N}_]+(?:['’][\p{L}\p{N}_]+)?/gu;

type EligibilityDiagnosticsWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationEligibilityDiagnosticsInstalled?: boolean;
};

type SttDetail = {
  chatSessionId?: string;
  segmentId?: string;
  sourceSequence?: number;
  text?: string;
  probability?: number;
  modelTimeMs?: number;
};

type EligibilityReason =
  | 'eligible'
  | 'disabled'
  | 'missing_partial'
  | 'too_short'
  | 'correction_shaped'
  | 'no_candidate_event'
  | 'eligible_candidate_not_started'
  | 'speculation_started';

type EligibilityClassification = {
  eligible: boolean;
  reason: EligibilityReason;
  wordCount: number;
  charCount: number;
};

type SegmentState = {
  sessionId: string | null;
  segmentId: string;
  sourceSequence: number;
  partialSeen: boolean;
  candidateSeen: boolean;
  finalSeen: boolean;
  speculationStarted: boolean;
  latestClassification: EligibilityClassification | null;
  candidateProbability: number | null;
  candidateModelTimeMs: number | null;
};

const segments = new Map<string, SegmentState>();

export function classifySpeculationEligibility(text: string): EligibilityClassification {
  const normalized = text.trim();
  const wordCount = [...normalized.matchAll(WORD_PATTERN)].length;
  if (wordCount < 2) {
    return { eligible: false, reason: 'too_short', wordCount, charCount: normalized.length };
  }
  if (CORRECTION_PATTERN.test(normalized)) {
    return {
      eligible: false,
      reason: 'correction_shaped',
      wordCount,
      charCount: normalized.length,
    };
  }
  return { eligible: true, reason: 'eligible', wordCount, charCount: normalized.length };
}

export function initializeLiveSpeculationEligibilityDiagnostics(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as EligibilityDiagnosticsWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;

  const handlePartial = (event: Event): void => {
    const detail = (event as CustomEvent<SttDetail>).detail;
    const state = stateFor(detail, true);
    if (!state) return;
    state.partialSeen = true;
    state.latestClassification = classifySpeculationEligibility(detail.text ?? '');
  };

  const handleCandidate = (event: Event): void => {
    const detail = (event as CustomEvent<SttDetail>).detail;
    const state = stateFor(detail, true);
    if (!state) {
      dispatchPerformance('llm_speculation_candidate_evaluated', {
        reason: 'missing_partial',
        eligible: false,
        hasSessionId: Boolean(detail?.chatSessionId),
        hasSegmentId: Boolean(detail?.segmentId),
        hasSourceSequence: typeof detail?.sourceSequence === 'number',
      });
      return;
    }
    state.candidateSeen = true;
    state.candidateProbability = finiteNumber(detail.probability);
    state.candidateModelTimeMs = finiteNumber(detail.modelTimeMs);
    const classification = !speculationEnabled()
      ? disabledClassification(state.latestClassification)
      : state.latestClassification ?? {
        eligible: false,
        reason: 'missing_partial' as const,
        wordCount: 0,
        charCount: 0,
      };
    state.latestClassification = classification;
    dispatchPerformance('llm_speculation_candidate_evaluated', {
      sessionId: state.sessionId,
      segmentId: state.segmentId,
      sourceSequence: state.sourceSequence,
      eligible: classification.eligible,
      reason: classification.reason,
      wordCount: classification.wordCount,
      charCount: classification.charCount,
      endpointProbability: state.candidateProbability,
      modelTimeMs: state.candidateModelTimeMs,
      partialSeen: state.partialSeen,
    });
  };

  const handleFinal = (event: Event): void => {
    const detail = (event as CustomEvent<SttDetail>).detail;
    const state = stateFor(detail, true);
    if (!state) return;
    state.finalSeen = true;
    const finalClassification = classifySpeculationEligibility(detail.text ?? '');
    const reason = finalReason(state);
    dispatchPerformance('llm_speculation_final_eligibility', {
      sessionId: state.sessionId,
      segmentId: state.segmentId,
      sourceSequence: state.sourceSequence,
      reason,
      candidateSeen: state.candidateSeen,
      partialSeen: state.partialSeen,
      speculationStarted: state.speculationStarted,
      candidateReason: state.latestClassification?.reason ?? null,
      finalWordCount: finalClassification.wordCount,
      finalCharCount: finalClassification.charCount,
      endpointProbability: state.candidateProbability,
      modelTimeMs: state.candidateModelTimeMs,
    });
  };

  const handleDeliverySettled = (event: Event): void => {
    const detail = (event as CustomEvent<SttDetail>).detail;
    const key = segmentKey(detail);
    if (!key) return;
    const state = segments.get(key);
    if (state && !state.speculationStarted) {
      dispatchPerformance('llm_speculation_not_started', {
        sessionId: state.sessionId,
        segmentId: state.segmentId,
        sourceSequence: state.sourceSequence,
        reason: finalReason(state),
        candidateSeen: state.candidateSeen,
        partialSeen: state.partialSeen,
        finalSeen: state.finalSeen,
        candidateReason: state.latestClassification?.reason ?? null,
        wordCount: state.latestClassification?.wordCount ?? 0,
        charCount: state.latestClassification?.charCount ?? 0,
        endpointProbability: state.candidateProbability,
        modelTimeMs: state.candidateModelTimeMs,
      });
    }
    segments.delete(key);
  };

  const handlePerformance = (event: Event): void => {
    const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
    if (detail.stage !== 'llm_speculation_started') return;
    const segmentId = typeof detail.segmentId === 'string' ? detail.segmentId : null;
    const sourceSequence = typeof detail.sourceSequence === 'number'
      ? detail.sourceSequence
      : null;
    if (!segmentId || sourceSequence === null) return;
    const key = `${segmentId}:${sourceSequence}`;
    const state = segments.get(key) ?? createState({
      chatSessionId: typeof detail.sessionId === 'string' ? detail.sessionId : undefined,
      segmentId,
      sourceSequence,
    });
    if (!state) return;
    state.speculationStarted = true;
    segments.set(key, state);
  };

  window.addEventListener(LIVE_STT_SPECULATION_PARTIAL_EVENT, handlePartial);
  window.addEventListener(LIVE_STT_SPECULATION_CANDIDATE_EVENT, handleCandidate);
  window.addEventListener(LIVE_STT_SPECULATION_FINAL_EVENT, handleFinal);
  window.addEventListener(LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT, handleDeliverySettled);
  window.addEventListener(LIVE_VOICE_PERF_EVENT, handlePerformance);

  return () => {
    window.removeEventListener(LIVE_STT_SPECULATION_PARTIAL_EVENT, handlePartial);
    window.removeEventListener(LIVE_STT_SPECULATION_CANDIDATE_EVENT, handleCandidate);
    window.removeEventListener(LIVE_STT_SPECULATION_FINAL_EVENT, handleFinal);
    window.removeEventListener(LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT, handleDeliverySettled);
    window.removeEventListener(LIVE_VOICE_PERF_EVENT, handlePerformance);
    segments.clear();
    liveWindow[INSTALLED_KEY] = false;
  };
}

function disabledClassification(
  previous: EligibilityClassification | null,
): EligibilityClassification {
  return {
    eligible: false,
    reason: 'disabled',
    wordCount: previous?.wordCount ?? 0,
    charCount: previous?.charCount ?? 0,
  };
}

function finalReason(state: SegmentState): EligibilityReason {
  if (state.speculationStarted) return 'speculation_started';
  if (!speculationEnabled()) return 'disabled';
  if (!state.candidateSeen) return 'no_candidate_event';
  if (state.latestClassification?.eligible) return 'eligible_candidate_not_started';
  return state.latestClassification?.reason ?? 'missing_partial';
}

function stateFor(detail: SttDetail | undefined, create: boolean): SegmentState | null {
  const key = segmentKey(detail);
  if (!key) return null;
  const existing = segments.get(key);
  if (existing || !create) return existing ?? null;
  const created = createState(detail);
  if (created) segments.set(key, created);
  return created;
}

function createState(detail: SttDetail | undefined): SegmentState | null {
  if (!detail?.segmentId || typeof detail.sourceSequence !== 'number') return null;
  return {
    sessionId: detail.chatSessionId ?? null,
    segmentId: detail.segmentId,
    sourceSequence: detail.sourceSequence,
    partialSeen: false,
    candidateSeen: false,
    finalSeen: false,
    speculationStarted: false,
    latestClassification: null,
    candidateProbability: null,
    candidateModelTimeMs: null,
  };
}

function segmentKey(detail: SttDetail | undefined): string | null {
  if (!detail?.segmentId || typeof detail.sourceSequence !== 'number') return null;
  return `${detail.segmentId}:${detail.sourceSequence}`;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function speculationEnabled(): boolean {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_LIVE_SPECULATION_ENABLED?.trim().toLowerCase() !== 'false';
}

function dispatchPerformance(stage: string, detail: Record<string, unknown>): void {
  window.dispatchEvent(new CustomEvent(LIVE_VOICE_PERF_EVENT, {
    detail: { stage, timestamp: new Date().toISOString(), ...detail },
  }));
}
