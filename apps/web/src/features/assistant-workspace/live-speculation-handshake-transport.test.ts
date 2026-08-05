import { describe, expect, it, vi } from 'vitest';

import { bridgeLiveSpeculationHandshakeRequest } from './live-speculation-handshake-transport';


describe('live speculation handshake transport', () => {
  it('returns the generation id before the provider stream resolves', async () => {
    let resolveGeneration: ((response: Response) => void) | undefined;
    const generationResponse = new Promise<Response>((resolve) => {
      resolveGeneration = resolve;
    });
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.endsWith('/start')) {
        return new Response(JSON.stringify({
          ok: true,
          generation_id: 'spec-test',
          segment_id: 'segment-test',
          source_sequence: 4,
          provider_id: 'fake-provider',
          model_id: 'fake-model',
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/spec-test/stream')) return generationResponse;
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    const bridged = await bridgeLiveSpeculationHandshakeRequest(
      fetchImpl,
      '/api/live/speculation/sessions/session-test/stream',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: 'Tell me a story',
          segment_id: 'segment-test',
          source_sequence: 4,
        }),
      },
    );

    expect(bridged).not.toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    const reader = bridged!.body!.getReader();
    const decoder = new TextDecoder();
    const first = await reader.read();
    const firstText = decoder.decode(first.value);
    expect(first.done).toBe(false);
    expect(firstText).toContain('"type":"speculation_started"');
    expect(firstText).toContain('"generation_id":"spec-test"');

    resolveGeneration?.(new Response(
      'data: {"type":"text_chunk","text":"Hello"}\n\n'
      + 'data: {"type":"done","generation_id":"spec-test"}\n\n',
      {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      },
    ));

    let remainder = '';
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      remainder += decoder.decode(next.value, { stream: true });
    }
    remainder += decoder.decode();
    expect(remainder).toContain('"type":"text_chunk"');
    expect(remainder).toContain('"text":"Hello"');
  });

  it('cancels eager server generation when the source request is aborted', async () => {
    const sourceAbort = new AbortController();
    let generationController: ReadableStreamDefaultController<Uint8Array> | undefined;
    const neverEndingStream = new ReadableStream<Uint8Array>({
      start(controller) {
        generationController = controller;
      },
    });
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.endsWith('/start')) {
        return new Response(JSON.stringify({
          ok: true,
          generation_id: 'spec-cancel',
          segment_id: 'segment-cancel',
          source_sequence: 5,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/spec-cancel/stream')) {
        return new Response(neverEndingStream, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }
      if (url.endsWith('/spec-cancel/cancel')) {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }) as unknown as typeof fetch;

    const bridged = await bridgeLiveSpeculationHandshakeRequest(
      fetchImpl,
      '/api/live/speculation/sessions/session-test/stream',
      {
        method: 'POST',
        body: JSON.stringify({
          content: 'Tell me a story',
          segment_id: 'segment-cancel',
          source_sequence: 5,
        }),
        signal: sourceAbort.signal,
      },
    );

    expect(bridged).not.toBeNull();
    const reader = bridged!.body!.getReader();
    await reader.read();
    sourceAbort.abort('transcript corrected');

    await vi.waitFor(() => {
      expect(fetchImpl).toHaveBeenCalledWith(
        '/api/live/speculation/sessions/session-test/spec-cancel/cancel',
        expect.objectContaining({ method: 'POST', keepalive: true }),
      );
    });
    generationController?.close();
    await reader.cancel();
  });

  it('leaves unrelated fetch requests untouched', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch;
    const bridged = await bridgeLiveSpeculationHandshakeRequest(
      fetchImpl,
      '/api/chat/sessions/session-test/messages/stream',
      { method: 'POST', body: '{}' },
    );

    expect(bridged).toBeNull();
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
