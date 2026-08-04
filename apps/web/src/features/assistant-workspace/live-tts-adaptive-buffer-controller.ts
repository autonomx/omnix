import type { LiveVoicePcmSession } from './live-voice-pcm-session';

const STORAGE_KEY = 'omnix.liveTts.adaptiveBuffer.v1';

export type AdaptiveBufferSnapshot = {
  startBufferMs: number;
  rebufferMs: number;
  maxRebufferMs: number;
  stableTurns: number;
  underrunTurns: number;
};

export class AdaptiveTtsBufferPolicy {
  private snapshotValue: AdaptiveBufferSnapshot;
  private turnUnderruns = 0;

  constructor(initial?: Partial<AdaptiveBufferSnapshot>) {
    this.snapshotValue = {
      startBufferMs: clamp(initial?.startBufferMs ?? 260, 160, 650),
      rebufferMs: clamp(initial?.rebufferMs ?? 520, 300, 1_200),
      maxRebufferMs: clamp(initial?.maxRebufferMs ?? 1_400, 800, 2_000),
      stableTurns: Math.max(0, initial?.stableTurns ?? 0),
      underrunTurns: Math.max(0, initial?.underrunTurns ?? 0),
    };
  }

  snapshot(): AdaptiveBufferSnapshot {
    return { ...this.snapshotValue };
  }

  observeWorkletEvent(type: string): AdaptiveBufferSnapshot {
    if (type === 'underrun') {
      this.turnUnderruns += 1;
      this.snapshotValue.startBufferMs = clamp(
        this.snapshotValue.startBufferMs + 70,
        160,
        650,
      );
      this.snapshotValue.rebufferMs = clamp(
        this.snapshotValue.rebufferMs + 110,
        300,
        1_200,
      );
    }
    if (type === 'drained') {
      if (this.turnUnderruns > 0) {
        this.snapshotValue.underrunTurns += 1;
        this.snapshotValue.stableTurns = 0;
      } else {
        this.snapshotValue.stableTurns += 1;
        if (this.snapshotValue.stableTurns >= 3) {
          this.snapshotValue.startBufferMs = clamp(
            this.snapshotValue.startBufferMs - 20,
            160,
            650,
          );
          this.snapshotValue.rebufferMs = clamp(
            this.snapshotValue.rebufferMs - 30,
            300,
            1_200,
          );
          this.snapshotValue.stableTurns = 0;
        }
      }
      this.turnUnderruns = 0;
    }
    return this.snapshot();
  }
}

export function adaptiveBufferWorkletMessage(
  snapshot: AdaptiveBufferSnapshot,
  sampleRate: number,
): Record<string, number | string> {
  return {
    type: 'set_buffer_policy',
    startBufferSamples: millisecondsToSamples(
      snapshot.startBufferMs,
      sampleRate,
    ),
    minimumBufferedSpeechSamples: millisecondsToSamples(
      snapshot.startBufferMs,
      sampleRate,
    ),
    rebufferSamples: millisecondsToSamples(
      snapshot.rebufferMs,
      sampleRate,
    ),
    maxRebufferSamples: millisecondsToSamples(
      snapshot.maxRebufferMs,
      sampleRate,
    ),
  };
}

/**
 * Adaptive playback is opt-in. The PCM session owns its worklet and receives
 * policy updates through its public API; this module never patches browser
 * constructors or MessagePort methods.
 */
export function adaptiveBufferEnabled(): boolean {
  const env = (
    import.meta as unknown as {
      env?: Record<string, string | undefined>;
    }
  ).env;
  return env?.VITE_LIVE_TTS_ADAPTIVE_BUFFER
    ?.trim()
    .toLowerCase() === 'true';
}

export function loadAdaptiveBufferSnapshot(): Partial<AdaptiveBufferSnapshot> | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) ?? 'null',
    ) as unknown;
    return parsed && typeof parsed === 'object'
      ? parsed as Partial<AdaptiveBufferSnapshot>
      : undefined;
  } catch {
    return undefined;
  }
}

export function saveAdaptiveBufferSnapshot(
  snapshot: AdaptiveBufferSnapshot,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(snapshot),
    );
  } catch {
    // Best-effort local tuning only.
  }
}

export function applyAdaptiveBufferSnapshot(
  session: Pick<LiveVoicePcmSession, 'setStartPolicy'>,
  snapshot: AdaptiveBufferSnapshot,
): void {
  session.setStartPolicy({
    minimumBufferedSpeechMs: snapshot.startBufferMs,
  });
}

function millisecondsToSamples(
  milliseconds: number,
  sampleRate: number,
): number {
  return Math.max(1, Math.round(milliseconds * sampleRate / 1_000));
}

function clamp(
  value: number,
  minimum: number,
  maximum: number,
): number {
  return Math.max(minimum, Math.min(maximum, value));
}
