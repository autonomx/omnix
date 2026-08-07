import { describe, expect, it } from 'vitest';

import {
  SPECULATIVE_TTS_ACCEPTED_REQUEST_CONTRACT,
  normalizeSpeculativeTtsRequest,
} from './live-speculative-tts-request-contract';

describe('live speculative TTS request contract', () => {
  it('aligns speculative prefetch cache-key fields with accepted live TTS', async () => {
    const original = {
      generation_id: 'spec-client-test',
      request: {
        text: 'Hello there.',
        speaker: 'Sofia',
        language: 'English',
        chunk_size: 8,
        temperature: 0.6,
        top_k: 20,
        top_p: 0.85,
        repetition_penalty: 1.0,
        append_silence: false,
        non_streaming_mode: false,
        parity_mode: true,
        max_new_tokens: 48,
        delivery_plan: { schema_version: 1 },
      },
    };

    const normalized = await normalizeSpeculativeTtsRequest(
      '/api/live/speculation/tts-prefetch',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(original),
      },
    );

    const body = JSON.parse(String(normalized.init?.body ?? '{}')) as typeof original;
    expect(body.generation_id).toBe(original.generation_id);
    expect(body.request.text).toBe(original.request.text);
    expect(body.request.speaker).toBe(original.request.speaker);
    expect(body.request.max_new_tokens).toBe(original.request.max_new_tokens);
    expect(body.request.delivery_plan).toEqual(original.request.delivery_plan);
    expect(body.request).toMatchObject(SPECULATIVE_TTS_ACCEPTED_REQUEST_CONTRACT);
    expect(normalized.init).toMatchObject({ method: 'POST', priority: 'high' });
  });

  it('does not rewrite unrelated requests', async () => {
    const init: RequestInit = {
      method: 'POST',
      body: JSON.stringify({ request: { chunk_size: 8 } }),
    };
    const normalized = await normalizeSpeculativeTtsRequest(
      '/api/chat/sessions/session-test/messages/stream',
      init,
    );

    expect(normalized.input).toBe('/api/chat/sessions/session-test/messages/stream');
    expect(normalized.init).toBe(init);
  });
});
