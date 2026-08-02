const PERF_EVENT = 'omnix:assistant-voice-perf';
const INSTALLED_KEY = '__omnixLiveTtsCapabilityControllerInstalled';

export type LiveTtsCapabilities = {
  ok: boolean;
  protocol: string;
  persistent_websocket: boolean;
  incremental_text_ingest: boolean;
  text_commit_deadline_ms: number;
  text_commit_minimum_characters: number;
  streaming_audio_chunks: boolean;
  native_decoder_text_append: boolean;
  stateful_text_append: boolean;
  prosody_continuous_decoder: boolean;
  cancellation_generations: boolean;
  adaptive_playback_buffer: boolean;
  fallback_mode: string;
  provider_available: boolean;
  provider_name?: string | null;
};

type CapabilityWindow = Window & typeof globalThis & {
  __omnixLiveTtsCapabilityControllerInstalled?: boolean;
  __omnixLiveTtsCapabilities?: LiveTtsCapabilities;
};

export function initializeLiveTtsCapabilityController(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as CapabilityWindow;
  if (liveWindow[INSTALLED_KEY]) return () => undefined;
  liveWindow[INSTALLED_KEY] = true;
  const abortController = new AbortController();
  void fetch('/api/tts/live-call/capabilities', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal: abortController.signal,
  }).then(async (response) => {
    if (!response.ok) throw new Error(`Live TTS capability request failed with status ${response.status}.`);
    const capabilities = await response.json() as LiveTtsCapabilities;
    liveWindow.__omnixLiveTtsCapabilities = capabilities;
    window.dispatchEvent(new CustomEvent(PERF_EVENT, {
      detail: {
        stage: 'tts_capabilities_negotiated',
        timestamp: new Date().toISOString(),
        ...capabilities,
      },
    }));
  }).catch((error: unknown) => {
    if (abortController.signal.aborted) return;
    window.dispatchEvent(new CustomEvent(PERF_EVENT, {
      detail: {
        stage: 'tts_capabilities_unavailable',
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : String(error),
      },
    }));
  });

  return () => {
    abortController.abort('controller-uninstalled');
    delete liveWindow.__omnixLiveTtsCapabilities;
    liveWindow[INSTALLED_KEY] = false;
  };
}

export function readLiveTtsCapabilities(): LiveTtsCapabilities | null {
  if (typeof window === 'undefined') return null;
  return (window as CapabilityWindow).__omnixLiveTtsCapabilities ?? null;
}
