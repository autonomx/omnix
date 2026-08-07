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

type LiveCallDiagnosticDetail = {
  event?: string;
  details?: Record<string, unknown>;
};

const LIVE_CALL_DIAGNOSTIC_EVENT = 'omnix:live-call-diagnostic';
const CHAT_RESPONSE_OPENED_EVENT = 'chat_response_opened';
const CHAT_STREAM_FAILED_EVENT = 'chat_stream_failed';

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
    let streamFailureCode: string | null = null;
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
    const observeDiagnostic = (event: Event): void => {
      const detail = (event as CustomEvent<LiveCallDiagnosticDetail>).detail;
      if (detail?.event === CHAT_RESPONSE_OPENED_EVENT) {
        accept();
        return;
      }
      if (detail?.event !== CHAT_STREAM_FAILED_EVENT) return;
      const errorCode = detail.details?.error_code;
      streamFailureCode = typeof errorCode === 'string' && errorCode.trim()
        ? errorCode
        : 'live_chat_stream_failed';
      reject(new Error(streamFailureCode));
    };

    window.addEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, observeDiagnostic);
    let completion: Promise<void>;
    try {
      completion = this.invokeHandler(input, handler);
    } catch (error) {
      completion = Promise.reject(error);
    }

    void completion.then(
      () => {
        if (streamFailureCode) reject(new Error(streamFailureCode));
        else accept();
      },
      (error) => reject(error),
    );

    try {
      await acceptance;
    } finally {
      window.removeEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, observeDiagnostic);
    }
  }

  private invokeHandler(
    input: LiveChatSubmissionInput,
    handler: LiveChatSubmissionHandler,
  ): Promise<void> {
    const interceptor = this.fetchInterceptor;
    if (!interceptor || typeof window.fetch !== 'function') {
      return Promise.resolve(handler(input));
    }

    // The workspace handler starts its chat fetch synchronously before its first
    // await. Scope interception to that call only, instead of replacing
    // window.fetch for the lifetime of the application.
    const originalFetch = window.fetch;
    const next: LiveChatSubmissionFetchNext = originalFetch.bind(window);
    window.fetch = ((request: RequestInfo | URL, init?: RequestInit) => (
      interceptor(input, request, init, next)
    )) as typeof window.fetch;
    try {
      return Promise.resolve(handler(input));
    } finally {
      window.fetch = originalFetch;
    }
  }
}

export const liveChatSubmissionGateway = new LiveChatSubmissionGateway();
