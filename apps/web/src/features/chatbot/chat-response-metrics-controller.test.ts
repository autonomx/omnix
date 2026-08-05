import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  captureChatSessionResponseMetrics,
  formatLmStudioStopReason,
  initializeChatResponseMetricsController,
  readChatResponseMetrics,
  renderChatResponseMetrics,
  resetChatResponseMetricsForTests,
} from './chat-response-metrics-controller';

afterEach(() => {
  resetChatResponseMetricsForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe('chat response metrics', () => {
  it('normalizes LM Studio persisted metrics', () => {
    expect(readChatResponseMetrics({
      usage: { completion_tokens: 37 },
      provider_metrics: {
        provider: 'lmstudio',
        tokens_per_second: 127.26,
        generation_time_seconds: 0.38,
        time_to_first_token_seconds: 0.11,
        stop_reason: 'eosFound',
      },
    })).toEqual({
      tokensPerSecond: 127.26,
      outputTokens: 37,
      generationTimeSeconds: 0.38,
      timeToFirstTokenSeconds: 0.11,
      stopReason: 'eosFound',
    });
  });

  it('renders compact metrics below the matching assistant response', () => {
    document.body.innerHTML = `
      <div class="assistant-chat-messages">
        <article class="assistant-chat-message assistant">
          <div class="assistant-chat-bubble">
            <p>Howdy right back at ya!</p>
            <div class="assistant-message-actions"></div>
          </div>
        </article>
      </div>
    `;
    captureChatSessionResponseMetrics({
      messages: [
        {
          id: 'assistant:1',
          role: 'assistant',
          metadata: {
            usage: { completion_tokens: 37 },
            provider_metrics: {
              provider: 'lmstudio',
              tokens_per_second: 127.26,
              generation_time_seconds: 0.38,
              time_to_first_token_seconds: 0.11,
              stop_reason: 'eosFound',
            },
          },
        },
      ],
    });

    renderChatResponseMetrics();

    const row = document.querySelector<HTMLElement>('.assistant-response-metrics');
    expect(row?.textContent).toContain('127.26 tok/sec');
    expect(row?.textContent).toContain('37 tokens');
    expect(row?.textContent).toContain('0.38s');
    expect(row?.textContent).toContain('Stop reason: EOS Token Found');
    expect(row?.dataset.timeToFirstTokenSeconds).toBe('0.11');
    expect(row?.nextElementSibling).toHaveClass('assistant-message-actions');
  });

  it('does not render a row for messages without provider metrics', () => {
    document.body.innerHTML = `
      <div class="assistant-chat-messages">
        <article class="assistant-chat-message assistant">
          <div class="assistant-chat-bubble"><p>No metrics</p></div>
        </article>
      </div>
    `;
    captureChatSessionResponseMetrics({
      messages: [{ id: 'assistant:1', role: 'assistant', metadata: {} }],
    });

    renderChatResponseMetrics();

    expect(document.querySelector('.assistant-response-metrics')).toBeNull();
  });

  it('formats LM Studio stop reason identifiers for display', () => {
    expect(formatLmStudioStopReason('maxPredictedTokensReached')).toBe('Max Tokens Reached');
    expect(formatLmStudioStopReason('stopStringFound')).toBe('Stop String Found');
  });

  it('does not clone or consume live chat stream responses', async () => {
    const cloneSpy = vi.spyOn(Response.prototype, 'clone');
    const fetchMock = vi.fn(async () => new Response('data: {"type":"done"}\n\n', {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    })) as unknown as typeof fetch;
    vi.stubGlobal('fetch', fetchMock);
    initializeChatResponseMetricsController();

    const response = await window.fetch('/api/chat/sessions/session-1/messages/stream', {
      method: 'POST',
    });

    expect(response.status).toBe(200);
    expect(cloneSpy).not.toHaveBeenCalled();
  });
});
