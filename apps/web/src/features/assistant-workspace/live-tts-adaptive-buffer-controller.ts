import { LIVE_VOICE_PCM_WORKLET_NAME } from './live-voice-pcm-worklet';

const INSTALLED_KEY = '__omnixLiveTtsAdaptiveBufferInstalled';
const PERF_EVENT = 'omnix:assistant-voice-perf';
const STORAGE_KEY = 'omnix.liveTts.adaptiveBuffer.v1';

export type AdaptiveBufferSnapshot = {
  startBufferMs: number;
  rebufferMs: number;
  maxRebufferMs: number;
  stableTurns: number;
  underrunTurns: number;
};

type AdaptiveWindow = Window & typeof globalThis & {
  __omnixLiveTtsAdaptiveBufferInstalled?: boolean;
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

export function initializeLiveTtsAdaptiveBufferController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as AdaptiveWindow;
  if (liveWindow[INSTALLED_KEY] || !adaptiveBufferEnabled()) {
    return () => undefined;
  }
  const NativeAudioWorkletNode = liveWindow.AudioWorkletNode;
  if (!NativeAudioWorkletNode) return () => undefined;
  const originalDescriptor = Object.getOwnPropertyDescriptor(
    liveWindow,
    'AudioWorkletNode',
  );
  const policy = new AdaptiveTtsBufferPolicy(loadSnapshot());

  const WrappedAudioWorkletNode = new Proxy(NativeAudioWorkletNode, {
    construct(target, argumentsList, newTarget) {
      const [audioContext, name, options] = argumentsList as [
        AudioContext,
        string,
        AudioWorkletNodeOptions | undefined,
      ];
      if (name !== LIVE_VOICE_PCM_WORKLET_NAME) {
        return Reflect.construct(target, argumentsList, newTarget);
      }
      const snapshot = policy.snapshot();
      const sampleRate = audioContext.sampleRate;
      const policyMessage = adaptiveBufferWorkletMessage(
        snapshot,
        sampleRate,
      );
      const nextOptions: AudioWorkletNodeOptions = {
        ...(options ?? {}),
        processorOptions: {
          ...(
            (options?.processorOptions as
              | Record<string, unknown>
              | undefined) ?? {}
          ),
          startBufferSamples: policyMessage.startBufferSamples,
          minimumBufferedSpeechSamples:
            policyMessage.minimumBufferedSpeechSamples,
          rebufferSamples: policyMessage.rebufferSamples,
          maxRebufferSamples: policyMessage.maxRebufferSamples,
        },
      };
      const node = Reflect.construct(
        target,
        [audioContext, name, nextOptions],
        newTarget,
      ) as AudioWorkletNode;
      const originalPostMessage = node.port.postMessage.bind(node.port);
      try {
        node.port.postMessage = ((
          message: unknown,
          transfer?: Transferable[],
        ) => {
          if (isStartPolicyMessage(message)) {
            const current = policy.snapshot();
            originalPostMessage(
              {
                ...message,
                minimumBufferedSpeechSamples: millisecondsToSamples(
                  current.startBufferMs,
                  sampleRate,
                ),
              },
              transfer ?? [],
            );
            return;
          }
          originalPostMessage(message, transfer ?? []);
        }) as MessagePort['postMessage'];
      } catch {
        dispatchPerformance('tts_adaptive_post_message_unavailable', {});
      }
      node.port.addEventListener(
        'message',
        (event: MessageEvent<Record<string, unknown>>) => {
          const type = typeof event.data?.type === 'string'
            ? event.data.type
            : '';
          if (type !== 'underrun' && type !== 'drained') return;
          const next = policy.observeWorkletEvent(type);
          saveSnapshot(next);
          try {
            originalPostMessage(
              adaptiveBufferWorkletMessage(next, sampleRate),
            );
          } catch {
            dispatchPerformance(
              'tts_adaptive_runtime_update_failed',
              { trigger: type },
            );
          }
          dispatchPerformance('tts_adaptive_buffer_updated', {
            trigger: type,
            ...next,
          });
        },
      );
      node.port.start?.();
      dispatchPerformance('tts_adaptive_buffer_applied', snapshot);
      return node;
    },
  });

  try {
    Object.defineProperty(liveWindow, 'AudioWorkletNode', {
      configurable: true,
      writable: true,
      value: WrappedAudioWorkletNode,
    });
  } catch (error) {
    liveWindow[INSTALLED_KEY] = false;
    dispatchPerformance('tts_adaptive_install_failed', {
      error: error instanceof Error ? error.message : String(error),
    });
    return () => undefined;
  }
  liveWindow[INSTALLED_KEY] = true;

  return () => {
    try {
      if (originalDescriptor) {
        Object.defineProperty(
          liveWindow,
          'AudioWorkletNode',
          originalDescriptor,
        );
      } else {
        Object.defineProperty(liveWindow, 'AudioWorkletNode', {
          configurable: true,
          writable: true,
          value: NativeAudioWorkletNode,
        });
      }
    } finally {
      liveWindow[INSTALLED_KEY] = false;
    }
  };
}

function isStartPolicyMessage(
  value: unknown,
): value is Record<string, unknown> & { type: 'set_start_policy' } {
  return Boolean(
    value
    && typeof value === 'object'
    && (value as Record<string, unknown>).type === 'set_start_policy',
  );
}

function millisecondsToSamples(
  milliseconds: number,
  sampleRate: number,
): number {
  return Math.max(1, Math.round(milliseconds * sampleRate / 1_000));
}

function loadSnapshot(): Partial<AdaptiveBufferSnapshot> | undefined {
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

function saveSnapshot(snapshot: AdaptiveBufferSnapshot): void {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(snapshot),
    );
  } catch {
    // Best-effort local tuning only.
  }
}

function adaptiveBufferEnabled(): boolean {
  const env = (
    import.meta as unknown as {
      env?: Record<string, string | undefined>;
    }
  ).env;
  return env?.VITE_LIVE_TTS_ADAPTIVE_BUFFER
    ?.trim()
    .toLowerCase() !== 'false';
}

function dispatchPerformance(
  stage: string,
  detail: Record<string, unknown>,
): void {
  window.dispatchEvent(new CustomEvent(PERF_EVENT, {
    detail: {
      stage,
      timestamp: new Date().toISOString(),
      ...detail,
    },
  }));
}

function clamp(
  value: number,
  minimum: number,
  maximum: number,
): number {
  return Math.max(minimum, Math.min(maximum, value));
}
