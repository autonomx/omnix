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

  it('does not clone live streams and persists the effective transport version', async () => {
    const cloneSpy = vi.spyOn(Response.prototype, 'clone');
    const observed: Array<Record<string, unknown>> = [];
    const listener = (event: Event): void => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail;
      if (detail?.stage === 'chat_sse_transport_response_observed') observed.push(detail);
    };
    window.addEventListener('omnix:assistant-voice-perf', listener);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const rawUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      if (rawUrl.includes('/api/tts/live-call/diagnostics')) {
        return new Response(null, { status: 204 });
      }
      return new Response('data: {"type":"done"}\n\n', {
        status: 200,
        headers: {
          'content-type': 'text/event-stream',
          'x-omnix-sse-transport': 'immediate-v2',
        },
      });
    });
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
    initializeChatResponseMetricsController();

    const response = await window.fetch('/api/chat/sessions/session-1/messages/stream', {
      method: 'POST',
      body: JSON.stringify({ live_voice_turn_id: 'voice-turn:test' }),
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    window.removeEventListener('omnix:assistant-voice-perf', listener);
    expect(response.status).toBe(200);
    expect(cloneSpy).not.toHaveBeenCalled();
    expect(observed).toEqual([
      expect.objectContaining({
        stage: 'chat_sse_transport_response_observed',
        turnId: 'voice-turn:test',
        transportVersion: 'immediate-v2',
        contentType: 'text/event-stream',
        responseCloned: false,
      }),
    ]);
    const diagnosticsRequest = fetchMock.mock.calls.find(
      (call) => String(call[0]).includes('/api/tts/live-call/diagnostics'),
    );
    expect(diagnosticsRequest).toBeDefined();
    const diagnosticsBody = JSON.parse(String(diagnosticsRequest?.[1]?.body));
    expect(diagnosticsBody.trace_id).toBe('live-call:voice-turn:test');
    expect(diagnosticsBody.events).toEqual(expect.arrayContaining([
      expect.objectContaining({
        source: 'chat_response_metrics',
        event: 'chat_sse_transport_response_observed',
        details: expect.objectContaining({
          transport_version: 'immediate-v2',
          content_type: 'text/event-stream',
          response_cloned: false,
        }),
      }),
    ]));
  });
});
