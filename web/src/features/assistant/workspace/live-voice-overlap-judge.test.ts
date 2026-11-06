import { describe, expect, it, vi } from 'vitest';

import { judgeOverlap } from './live-voice-overlap-judge';

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
});

/** The fake fetch may be handed a Request, or a URL and its options. */
function partsOf(input: RequestInfo | URL, init?: RequestInit) {
  const request = input instanceof Request ? input : null;
  return {
    url: request ? request.url : input.toString(),
    headers: new Headers(request ? request.headers : init?.headers),
    signal: request ? request.signal : init?.signal,
    body: async () => JSON.parse(request ? await request.clone().text() : String(init?.body)) as { transcript: string; assistant_text: string },
  };
}

describe('asking the model about speech over the assistant', () => {
  it('goes to the call\'s replica with the remark and the end of what is being said', async () => {
    let sent: ReturnType<typeof partsOf> | null = null;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      sent = partsOf(input, init);
      return answer({ decision: 'stop', source: 'model', reason: null, elapsed_ms: 560 });
    }) as unknown as typeof fetch;

    const verdict = await judgeOverlap('chat:one', ' Hang on. ', `${'x'.repeat(2_000)} the end`, fetchImpl);

    expect(verdict).toEqual({ decision: 'stop', source: 'model', reason: null });
    const request = sent as unknown as ReturnType<typeof partsOf>;
    expect(request.url).toContain('/api/live-call/sessions/chat%3Aone/overlap-judgement');
    expect(request.headers.get('X-Omnix-Call-Id')).toBe('chat%3Aone');
    const body = await request.body();
    expect(body.transcript).toBe('Hang on.');
    expect(body.assistant_text).toHaveLength(600);
    expect(body.assistant_text.endsWith('the end')).toBe(true);
  });

  it('keeps the reply playing when the request is refused or fails', async () => {
    const refused = vi.fn(async () => answer({ detail: 'session_not_found' }, 404)) as unknown as typeof fetch;
    await expect(judgeOverlap('chat:one', 'Cool.', '', refused)).resolves.toMatchObject({ decision: 'continue', source: 'fallback' });

    const broken = vi.fn(async () => { throw new Error('offline'); }) as unknown as typeof fetch;
    await expect(judgeOverlap('chat:one', 'Cool.', '', broken)).resolves.toMatchObject({ decision: 'continue', source: 'fallback' });
  });

  it('gives up on a request stuck on its way', async () => {
    vi.useFakeTimers();
    try {
      const stuck = vi.fn((input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        partsOf(input, init).signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      })) as unknown as typeof fetch;
      const verdict = judgeOverlap('chat:one', 'Cool.', '', stuck);
      await vi.advanceTimersByTimeAsync(1_500);
      await expect(verdict).resolves.toEqual({ decision: 'continue', source: 'fallback', reason: 'request_deadline' });
    } finally {
      vi.useRealTimers();
    }
  });
});
