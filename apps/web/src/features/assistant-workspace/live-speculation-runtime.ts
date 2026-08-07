import type { LiveChatSubmissionInput } from './live-chat-submission-gateway';
import { initializeLiveSpeculationController } from './live-speculation-controller';

const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages\/stream$/;

type SpeculationRuntimeWindow = Window & typeof globalThis & {
  __omnixLiveSpeculationRuntimeInstalled?: boolean;
};

export function liveSubmissionRequestMatches(
  submission: LiveChatSubmissionInput,
  input: RequestInfo | URL,
  init?: RequestInit,
): boolean {
  const method = (
    init?.method
    ?? (input instanceof Request ? input.method : 'GET')
  ).toUpperCase();
  if (method !== 'POST') return false;
  const rawUrl = typeof input === 'string' || input instanceof URL
    ? input.toString()
    : input.url;
  const url = new URL(rawUrl, window.location.origin);
  const match = CHAT_STREAM_PATH.exec(url.pathname);
  return Boolean(match && decodeURIComponent(match[1]) === submission.sessionId);
}

/**
 * Install speculation as the inner chat-stream transport.
 *
 * The unified live-audio controller is initialized later in main.tsx and wraps
 * this transport. That ordering is intentional: every normal or synthetic
 * speculative chat response must pass through unified audio before reaching the
 * application so its SSE text can be teed into the TTS phrase pipeline.
 *
 * A previous partial migration registered speculation as a scoped submission
 * interceptor while unified audio remained a window.fetch middleware. The
 * scoped interceptor then returned speculative/fallback responses before the
 * audio middleware could observe them, producing valid LLM text with zero TTS
 * phrases. Keep one composed chain until both middlewares are migrated together
 * to an explicit transport stack.
 */
export function initializeLiveSpeculationRuntime(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as SpeculationRuntimeWindow;
  if (liveWindow.__omnixLiveSpeculationRuntimeInstalled) return () => undefined;
  liveWindow.__omnixLiveSpeculationRuntimeInstalled = true;

  const cleanupController = initializeLiveSpeculationController();

  return () => {
    cleanupController();
    liveWindow.__omnixLiveSpeculationRuntimeInstalled = false;
  };
}
