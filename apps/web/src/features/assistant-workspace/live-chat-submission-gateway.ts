export type LiveChatSubmissionInput = {
  sessionId: string;
  text: string;
  source: 'live_coordination';
  interrupted: boolean;
  segmentId: string;
  sourceSequence: number;
};

export type LiveChatSubmissionHandler = (input: LiveChatSubmissionInput) => Promise<void>;

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
    await handler(input);
  }
}

export const liveChatSubmissionGateway = new LiveChatSubmissionGateway();
