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

describe('live chat submission gateway', () => {
  it('resolves when the registered stream completes without a failure diagnostic', async () => {
    const gateway = new LiveChatSubmissionGateway();
    const handler = vi.fn(async () => undefined);
    gateway.register(handler);

    await expect(gateway.submit(input)).resolves.toBeUndefined();
    expect(handler).toHaveBeenCalledWith(input);
  });

  it('turns a caught chat stream failure into a rejected coordination result', async () => {
    const gateway = new LiveChatSubmissionGateway();
    gateway.register(async () => {
      window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
        detail: {
          event: 'chat_stream_failed',
          details: { error_code: 'chat_stream_terminal_error' },
        },
      }));
    });

    await expect(gateway.submit(input)).rejects.toThrow('chat_stream_terminal_error');
  });

  it('removes the diagnostic listener after the submission settles', async () => {
    const gateway = new LiveChatSubmissionGateway();
    gateway.register(async () => undefined);

    await gateway.submit(input);
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { event: 'chat_stream_failed', details: {} },
    }));

    await expect(gateway.submit(input)).resolves.toBeUndefined();
  });
});
