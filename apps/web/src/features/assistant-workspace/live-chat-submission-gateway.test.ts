import { describe, expect, it, vi } from 'vitest';

import { LiveChatSubmissionGateway } from './live-chat-submission-gateway';

const input = {
  sessionId: 'chat:test',
  text: 'Hello',
  source: 'live_coordination' as const,
  interrupted: false,
  segmentId: 'segment-1',
  sourceSequence: 1,
};

function dispatchDiagnostic(event: string, details: Record<string, unknown> = {}): void {
  window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
    detail: { event, details },
  }));
}

describe('live chat submission gateway', () => {
  it('resolves when the registered stream completes without a diagnostic', async () => {
    const gateway = new LiveChatSubmissionGateway();
    const handler = vi.fn(async () => undefined);
    gateway.register(handler);

    await expect(gateway.submit(input)).resolves.toBeUndefined();
    expect(handler).toHaveBeenCalledWith(input);
  });

  it('releases coordination when the chat response opens instead of waiting for stream completion', async () => {
    const gateway = new LiveChatSubmissionGateway();
    let completeStream!: () => void;
    const streamCompletion = new Promise<void>((resolve) => {
      completeStream = resolve;
    });
    const handler = vi.fn(() => streamCompletion);
    gateway.register(handler);

    const submission = gateway.submit(input);
    await vi.waitFor(() => expect(handler).toHaveBeenCalledWith(input));
    dispatchDiagnostic('chat_response_opened', { status: 200 });

    await expect(submission).resolves.toBeUndefined();
    completeStream();
    await streamCompletion;
  });

  it('turns a chat stream failure before acceptance into a rejected coordination result', async () => {
    const gateway = new LiveChatSubmissionGateway();
    gateway.register(async () => {
      dispatchDiagnostic('chat_stream_failed', {
        error_code: 'chat_stream_terminal_error',
      });
    });

    await expect(gateway.submit(input)).rejects.toThrow('chat_stream_terminal_error');
  });

  it('does not let a later stream failure reopen an already accepted submission', async () => {
    const gateway = new LiveChatSubmissionGateway();
    let completeStream!: () => void;
    const streamCompletion = new Promise<void>((resolve) => {
      completeStream = resolve;
    });
    gateway.register(() => streamCompletion);

    const submission = gateway.submit(input);
    dispatchDiagnostic('chat_response_opened', { status: 200 });
    await expect(submission).resolves.toBeUndefined();

    dispatchDiagnostic('chat_stream_failed', { error_code: 'late_stream_failure' });
    completeStream();
    await streamCompletion;
  });

  it('removes the diagnostic listener after the submission is accepted', async () => {
    const gateway = new LiveChatSubmissionGateway();
    gateway.register(async () => undefined);

    await gateway.submit(input);
    dispatchDiagnostic('chat_stream_failed');

    await expect(gateway.submit(input)).resolves.toBeUndefined();
  });
});
