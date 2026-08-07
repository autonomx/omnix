import { liveConversationStore } from './live-conversation-store';
import { speculationCandidateCanStart } from './live-speculation-controller';
import {
  LIVE_STT_SPECULATION_CANDIDATE_EVENT,
  LIVE_STT_SPECULATION_PARTIAL_EVENT,
} from './live-stt-authority-controller';

const PERF_EVENT = 'omnix:assistant-voice-perf';
const INSTALLED_KEY = '__omnixLiveSpeculationEarlyTriggerInstalled';
const EARLY_SPECULATION_LONG_PROBABILITY = 0.35;
const EARLY_SPECULATION_MEDIUM_PROBABILITY = 0.45;
const EARLY_SPECULATION_SHORT_PROBABILITY = 0.6;
const EARLY_SPECULATION_SINGLE_WORD_PROBABILITY = 0.9;
const DUPLICATE_SUPPRESSION_MS = 160;
const WORD_PATTERN = /[\p{L}\p{N}_]+(?:['’][\p{L}\p{N}_]+)?/gu;

type EarlyTriggerWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationEarlyTriggerInstalled?: boolean;
};

type PerfDetail = Record<string, unknown> & {
  stage?: unknown;
  provider?: unknown;
  selectedProvider?: unknown;
  selected_provider?: unknown;
  authorityEnabled?: unknown;
  authority_enabled?: unknown;
  segmentId?: unknown;
  segment_id?: unknown;
  sourceSequence?: unknown;
  source_sequence?: unknown;
  probability?: unknown;
  modelTimeMs?: unknown;
  model_time_ms?: unknown;
};

type SpeculationPartialDetail = Record<string, unknown> & {
  chatSessionId?: unknown;
  chat_session_id?: unknown;
  segmentId?: unknown;
  segment_id?: unknown;
  sourceSequence?: unknown;
  source_sequence?: unknown;
  text?: unknown;
};

type CachedPartial = {
  chatSessionId: string;
  text: string;
};

type LastDispatch = {
  fingerprint: string;
  atMs: number;
};

export function earlySpeculationProbabilityFloor(text: string): number | null {
  const wordCount = [...text.matchAll(WORD_PATTERN)].length;
  if (wordCount === 1) {
    return speculationCandidateCanStart(
      text,
      EARLY_SPECULATION_SINGLE_WORD_PROBABILITY,
    )
      ? EARLY_SPECULATION_SINGLE_WORD_PROBABILITY
      : null;
  }
  if (wordCount < 2) return null;
  if (wordCount >= 4) return EARLY_SPECULATION_LONG_PROBABILITY;
  if (wordCount === 3) return EARLY_SPECULATION_MEDIUM_PROBABILITY;
  return EARLY_SPECULATION_SHORT_PROBABILITY;
}

export function earlySpeculationCandidateEligible(
  probability: number,
  text: string,
): boolean {
  const probabilityFloor = earlySpeculationProbabilityFloor(text);
  return probabilityFloor !== null
    && Number.isFinite(probability)
    && probability >= probabilityFloor
    && speculationCandidateCanStart(text, probability);
}

export function initializeLiveSpeculationEarlyTrigger(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as EarlyTriggerWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  const lastBySegment = new Map<string, LastDispatch>();
  const partialBySegment = new Map<string, CachedPartial>();
  let authoritativeKyutai = false;

  const handlePartial = (event: Event): void => {
    const detail = (event as CustomEvent<SpeculationPartialDetail>).detail;
    const segmentId = stringValue(detail?.segmentId ?? detail?.segment_id);
    const sourceSequence = numberValue(
      detail?.sourceSequence ?? detail?.source_sequence,
    );
    const text = stringValue(detail?.text);
    if (!segmentId || sourceSequence === null || !text) return;
    const chatSessionId = stringValue(
      detail?.chatSessionId ?? detail?.chat_session_id,
    ) || liveConversationStore.getState().sessionId || '';
    if (!chatSessionId) return;
    const key = `${segmentId}:${sourceSequence}`;
    partialBySegment.set(key, { chatSessionId, text });
    trimOldest(partialBySegment, 16);
  };

  const handlePerformance = (event: Event): void => {
    const detail = (event as CustomEvent<PerfDetail>).detail;
    const stage = stringValue(detail?.stage);
    if (stage === 'stt_authority_selected') {
      authoritativeKyutai = booleanValue(
        detail?.authorityEnabled ?? detail?.authority_enabled,
      ) && stringValue(
        detail?.selectedProvider ?? detail?.selected_provider,
      ).toLowerCase() === 'kyutai';
      lastBySegment.clear();
      partialBySegment.clear();
      return;
    }
    if (stage === 'stt_final_received') {
      const key = identityKey(detail);
      if (key) {
        lastBySegment.delete(key);
        partialBySegment.delete(key);
      }
      return;
    }
    if (stage !== 'stt_endpoint_score' || !authoritativeKyutai) return;
    if (stringValue(detail?.provider).toLowerCase() !== 'kyutai') return;

    const segmentId = stringValue(detail?.segmentId ?? detail?.segment_id);
    const sourceSequence = numberValue(
      detail?.sourceSequence ?? detail?.source_sequence,
    );
    const probability = numberValue(detail?.probability);
    if (!segmentId || sourceSequence === null || probability === null) return;

    const key = `${segmentId}:${sourceSequence}`;
    const cachedPartial = partialBySegment.get(key);
    const conversation = liveConversationStore.getState();
    const sessionId = cachedPartial?.chatSessionId || conversation.sessionId;
    const text = (cachedPartial?.text || conversation.transcript.partial).trim();
    if (!sessionId || !earlySpeculationCandidateEligible(probability, text)) return;

    const fingerprint = normalizedWords(text);
    const now = performance.now();
    const previous = lastBySegment.get(key);
    if (
      previous
      && previous.fingerprint === fingerprint
      && now - previous.atMs < DUPLICATE_SUPPRESSION_MS
    ) return;
    lastBySegment.set(key, { fingerprint, atMs: now });
    trimOldest(lastBySegment, 16);

    const candidate = {
      chatSessionId: sessionId,
      segmentId,
      sourceSequence,
      text,
    };
    window.dispatchEvent(new CustomEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, {
      detail: candidate,
    }));
    window.dispatchEvent(new CustomEvent(LIVE_STT_SPECULATION_CANDIDATE_EVENT, {
      detail: {
        ...candidate,
        probability,
        modelTimeMs: numberValue(
          detail?.modelTimeMs ?? detail?.model_time_ms,
        ) ?? undefined,
        earlyTrigger: true,
      },
    }));
    window.dispatchEvent(new CustomEvent(PERF_EVENT, {
      detail: {
        stage: 'llm_speculation_early_candidate_dispatched',
        timestamp: new Date().toISOString(),
        segmentId,
        sourceSequence,
        probability,
        probabilityFloor: earlySpeculationProbabilityFloor(text),
        transcriptChars: text.length,
        transcriptWords: fingerprint ? fingerprint.split(' ').length : 0,
      },
    }));
  };

  window.addEventListener(LIVE_STT_SPECULATION_PARTIAL_EVENT, handlePartial);
  window.addEventListener(PERF_EVENT, handlePerformance);
  return () => {
    window.removeEventListener(LIVE_STT_SPECULATION_PARTIAL_EVENT, handlePartial);
    window.removeEventListener(PERF_EVENT, handlePerformance);
    lastBySegment.clear();
    partialBySegment.clear();
    authoritativeKyutai = false;
    liveWindow[INSTALLED_KEY] = false;
  };
}

function normalizedWords(text: string): string {
  return [...text.matchAll(WORD_PATTERN)]
    .map((match) => match[0].toLocaleLowerCase().replaceAll('’', "'"))
    .join(' ');
}

function identityKey(detail: PerfDetail | undefined): string | null {
  const segmentId = stringValue(detail?.segmentId ?? detail?.segment_id);
  const sourceSequence = numberValue(
    detail?.sourceSequence ?? detail?.source_sequence,
  );
  return segmentId && sourceSequence !== null
    ? `${segmentId}:${sourceSequence}`
    : null;
}

function trimOldest<T>(map: Map<string, T>, maxSize: number): void {
  while (map.size > maxSize) {
    const oldest = map.keys().next().value;
    if (typeof oldest !== 'string') break;
    map.delete(oldest);
  }
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function numberValue(value: unknown): number | null {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function booleanValue(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  return String(value).trim().toLowerCase() === 'true';
}
