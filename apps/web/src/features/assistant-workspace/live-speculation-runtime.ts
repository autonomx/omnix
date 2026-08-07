import {
  liveChatSubmissionGateway,
  type LiveChatSubmissionInput,
} from './live-chat-submission-gateway';
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
 * Install the existing speculation engine behind the explicit live submission
 * gateway. The legacy controller still owns hypothesis/cancellation semantics,
 * but its fetch interception is captured and immediately removed from the
 * application-wide window. It is invoked only for the synchronous chat request
 * started by a coordinated live-voice submission.
 */
export function initializeLiveSpeculationRuntime(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const liveWindow = window as SpeculationRuntimeWindow;
  if (liveWindow.__omnixLiveSpeculationRuntimeInstalled) return () => undefined;
  liveWindow.__omnixLiveSpeculationRuntimeInstalled = true;

  const applicationFetch = window.fetch;
  const cleanupController = initializeLiveSpeculationController();
  const speculationFetch = window.fetch.bind(window);
  window.fetch = applicationFetch;

  const unregisterInterceptor = liveChatSubmissionGateway.registerFetchInterceptor(
    (submission, input, init, next) => {
      if (!liveSubmissionRequestMatches(submission, input, init)) {
        return next(input, init);
      }
      return speculationFetch(input, init);
    },
  );

  return () => {
    unregisterInterceptor();
    cleanupController();
    window.fetch = applicationFetch;
    liveWindow.__omnixLiveSpeculationRuntimeInstalled = false;
  };
}
