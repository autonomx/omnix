import type { LiveVoicePcmSession } from './live-voice-pcm-session';

const STORAGE_PREFIX = 'omnix.liveTts.adaptiveOnset.v1';
const MINIMUM_START_BUFFER_MS = 160;
const MAXIMUM_START_BUFFER_MS = 650;
const DEFAULT_START_BUFFER_MS = 220;

export type AdaptiveOnsetSnapshot = {
  startBufferMs: number;
  stableTurns: number;
  underrunTurns: number;
};

export type AdaptiveOnsetController = {
  snapshot: () => AdaptiveOnsetSnapshot;
  observeWorkletEvent: (event: Record<string, unknown>) => AdaptiveOnsetSnapshot;
};

export class AdaptiveOnsetPolicy {
  private value: AdaptiveOnsetSnapshot;
  private turnHadUnderrun = false;

  constructor(initial?: Partial<AdaptiveOnsetSnapshot>) {
    this.value = {
      startBufferMs: clamp(
        initial?.startBufferMs ?? DEFAULT_START_BUFFER_MS,
        MINIMUM_START_BUFFER_MS,
        MAXIMUM_START_BUFFER_MS,
      ),
      stableTurns: nonnegativeInteger(initial?.stableTurns),
      underrunTurns: nonnegativeInteger(initial?.underrunTurns),
    };
  }

  snapshot(): AdaptiveOnsetSnapshot {
    return { ...this.value };
  }

  observe(type: string): AdaptiveOnsetSnapshot {
    if (type === 'underrun') {
      this.turnHadUnderrun = true;
      this.value.startBufferMs = clamp(
        this.value.startBufferMs + 70,
        MINIMUM_START_BUFFER_MS,
        MAXIMUM_START_BUFFER_MS,
      );
      this.value.stableTurns = 0;
      return this.snapshot();
    }
    if (type !== 'drained') return this.snapshot();

    if (this.turnHadUnderrun) {
      this.value.underrunTurns += 1;
      this.value.stableTurns = 0;
    } else {
      this.value.stableTurns += 1;
      if (this.value.stableTurns >= 3) {
        this.value.startBufferMs = clamp(
          this.value.startBufferMs - 20,
          MINIMUM_START_BUFFER_MS,
          MAXIMUM_START_BUFFER_MS,
        );
        this.value.stableTurns = 0;
      }
    }
    this.turnHadUnderrun = false;
    return this.snapshot();
  }
}

export function adaptiveOnsetEnabled(): boolean {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_LIVE_TTS_ADAPTIVE_BUFFER?.trim().toLowerCase() === 'true';
}

export function createAdaptiveOnsetController(
  session: Pick<LiveVoicePcmSession, 'setStartPolicy'>,
  profileKey: string,
): AdaptiveOnsetController {
  const storageKey = `${STORAGE_PREFIX}:${profileKey}`;
  const policy = new AdaptiveOnsetPolicy(loadSnapshot(storageKey));
  applySnapshot(session, policy.snapshot());
  return {
    snapshot: () => policy.snapshot(),
    observeWorkletEvent: (event) => {
      const type = typeof event.type === 'string' ? event.type : '';
      if (type !== 'underrun' && type !== 'drained') return policy.snapshot();
      const next = policy.observe(type);
      saveSnapshot(storageKey, next);
      applySnapshot(session, next);
      return next;
    },
  };
}

function applySnapshot(
  session: Pick<LiveVoicePcmSession, 'setStartPolicy'>,
  snapshot: AdaptiveOnsetSnapshot,
): void {
  session.setStartPolicy({ minimumBufferedSpeechMs: snapshot.startBufferMs });
}

function loadSnapshot(storageKey: string): Partial<AdaptiveOnsetSnapshot> | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(storageKey) ?? 'null') as unknown;
    return parsed && typeof parsed === 'object'
      ? parsed as Partial<AdaptiveOnsetSnapshot>
      : undefined;
  } catch {
    return undefined;
  }
}

function saveSnapshot(storageKey: string, snapshot: AdaptiveOnsetSnapshot): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(snapshot));
  } catch {
    // Best-effort local tuning only.
  }
}

function nonnegativeInteger(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.round(value)
    : 0;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
