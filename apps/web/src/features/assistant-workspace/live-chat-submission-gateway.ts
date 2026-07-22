export type LiveChatSubmissionInput = {
  sessionId: string;
  text: string;
  source: 'live_coordination';
  interrupted: boolean;
  segmentId: string;
  sourceSequence: number;
};

export type LiveChatSubmissionHandler = (input: LiveChatSubmissionInput) => Promise<void>;

type LiveCallDiagnosticDetail = {
  event?: string;
  details?: Record<string, unknown>;
};

const LIVE_CALL_DIAGNOSTIC_EVENT = 'omnix:live-call-diagnostic';

export class LiveChatSubmissionGateway {
  private handler: LiveChatSubmissionHandler | null = null;

  register(handler: LiveChatSubmissionHandler): () => void {
    this.handler = handler;
    return () => {
      if (this.handler === handler) this.handler = null;
    };
  }

  async submit(input: LiveChatSubmissionInput): Promise<void> {
    const handler = this.handler;
    if (!handler) throw new Error('live_chat_submission_gateway_unavailable');

    let streamFailureCode: string | null = null;
    const observeDiagnostic = (event: Event): void => {
      const detail = (event as CustomEvent<LiveCallDiagnosticDetail>).detail;
      if (detail?.event !== 'chat_stream_failed') return;
      const errorCode = detail.details?.error_code;
      streamFailureCode = typeof errorCode === 'string' && errorCode.trim()
        ? errorCode
        : 'live_chat_stream_failed';
    };

    window.addEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, observeDiagnostic);
    try {
      await handler(input);
      if (streamFailureCode) throw new Error(streamFailureCode);
    } finally {
      window.removeEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, observeDiagnostic);
    }
  }
}

export const liveChatSubmissionGateway = new LiveChatSubmissionGateway();
