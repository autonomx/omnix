export type LiveChatSubmissionInput = {
  sessionId: string;
  text: string;
  source: 'live_coordination';
  interrupted: boolean;
  segmentId: string;
  sourceSequence: number;
};

export type LiveChatSubmissionHandler = (input: LiveChatSubmissionInput) => Promise<void>;
export type LiveChatSubmissionFetchNext = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;
export type LiveChatSubmissionFetchInterceptor = (
  submission: LiveChatSubmissionInput,
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  next: LiveChatSubmissionFetchNext,
) => Promise<Response>;

type SubmissionFetchObserver = (
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  response: Promise<Response>,
) => void;

const CHAT_STREAM_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages\/stream$/;

export function liveSubmissionFetchMatches(
  submission: LiveChatSubmissionInput,
  input: RequestInfo | URL,
  init?: RequestInit,
): boolean {
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  if (method !== 'POST') return false;
  const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const url = new URL(rawUrl, window.location.origin);
  const match = CHAT_STREAM_PATH.exec(url.pathname);
  return Boolean(match && decodeURIComponent(match[1]) === submission.sessionId);
}

export class LiveChatSubmissionGateway {
  private handler: LiveChatSubmissionHandler | null = null;
  private fetchInterceptor: LiveChatSubmissionFetchInterceptor | null = null;

  register(handler: LiveChatSubmissionHandler): () => void {
    this.handler = handler;
    return () => {
      if (this.handler === handler) this.handler = null;
    };
  }

  registerFetchInterceptor(interceptor: LiveChatSubmissionFetchInterceptor): () => void {
    this.fetchInterceptor = interceptor;
    return () => {
      if (this.fetchInterceptor === interceptor) this.fetchInterceptor = null;
    };
  }

  async submit(input: LiveChatSubmissionInput): Promise<void> {
    const handler = this.handler;
    if (!handler) throw new Error('live_chat_submission_gateway_unavailable');

    let settled = false;
    let submissionFetchObserved = false;
    let resolveAcceptance!: () => void;
    let rejectAcceptance!: (error: Error) => void;
    const acceptance = new Promise<void>((resolve, reject) => {
      resolveAcceptance = resolve;
      rejectAcceptance = reject;
    });

    const accept = (): void => {
      if (settled) return;
      settled = true;
      resolveAcceptance();
    };
    const reject = (error: unknown): void => {
      if (settled) return;
      settled = true;
      rejectAcceptance(error instanceof Error ? error : new Error(String(error)));
    };
    const observeFetch: SubmissionFetchObserver = (request, init, response) => {
      if (!liveSubmissionFetchMatches(input, request, init)) return;
      submissionFetchObserved = true;
      void response.then(
        (opened) => {
          if (opened.ok) accept();
          else reject(new Error(`live_chat_stream_status_${opened.status}`));
        },
        (error) => reject(error),
      );
    };

    let completion: Promise<void>;
    try {
      completion = this.invokeHandler(input, handler, observeFetch);
    } catch (error) {
      completion = Promise.reject(error);
    }

    void completion.then(
      () => {
        // Handlers without a chat-stream fetch retain the original completion
        // semantics. Once the exact submission fetch has been observed, only
        // that fetch may accept or reject this coordination attempt; failures
        // from a superseded turn cannot poison the new submission.
        if (!submissionFetchObserved) accept();
      },
      (error) => reject(error),
    );

    await acceptance;
  }

  private invokeHandler(
    input: LiveChatSubmissionInput,
    handler: LiveChatSubmissionHandler,
    observeFetch: SubmissionFetchObserver,
  ): Promise<void> {
    if (typeof window.fetch !== 'function') return Promise.resolve(handler(input));

    // The workspace handler starts its chat fetch synchronously before its first
    // await. Scope interception to that call only, instead of replacing
    // window.fetch for the lifetime of the application. The exact response
    // promise is also the submission identity used for early acceptance.
    const interceptor = this.fetchInterceptor;
    const originalFetch = window.fetch;
    const next: LiveChatSubmissionFetchNext = originalFetch.bind(window);
    window.fetch = ((request: RequestInfo | URL, init?: RequestInit) => {
      const response = interceptor
        ? interceptor(input, request, init, next)
        : next(request, init);
      observeFetch(request, init, response);
      return response;
    }) as typeof window.fetch;
    try {
      return Promise.resolve(handler(input));
    } finally {
      window.fetch = originalFetch;
    }
  }
}

export const liveChatSubmissionGateway = new LiveChatSubmissionGateway();
