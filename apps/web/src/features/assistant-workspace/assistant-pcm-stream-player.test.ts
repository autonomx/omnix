import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { initializeChatMessageStreamAudioController } from './chat-message-stream-audio-controller';

type EndListener = () => void;

class FakeSource {
  buffer: AudioBuffer | null = null;
  private onEnded: EndListener | null = null;
  connect = vi.fn();
  disconnect = vi.fn();
  stop = vi.fn();
  start = vi.fn((_when?: number) => queueMicrotask(() => this.onEnded?.()));

  addEventListener(type: string, listener: EventListenerOrEventListenerObject): void {
    if (type !== 'ended') return;
    this.onEnded = typeof listener === 'function'
      ? () => listener(new Event('ended'))
      : () => listener.handleEvent(new Event('ended'));
  }
}

class FakeAudioContext {
  static sources: FakeSource[] = [];
  state: AudioContextState = 'running';
  currentTime = 0;
  destination = {} as AudioDestinationNode;
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);

  createBuffer(_channels: number, length: number, sampleRate: number): AudioBuffer {
    const channel = new Float32Array(length);
    return {
      duration: length / sampleRate,
      length,
      numberOfChannels: 1,
      sampleRate,
      getChannelData: () => channel,
    } as unknown as AudioBuffer;
  }

  createBufferSource(): AudioBufferSourceNode {
    const source = new FakeSource();
    FakeAudioContext.sources.push(source);
    return source as unknown as AudioBufferSourceNode;
  }
}

function renderMessage(): HTMLButtonElement {
  document.body.innerHTML = `
    <select aria-label="Cloned voice"><option value="ari-clone" selected>Ari</option></select>
    <article class="assistant-chat-message assistant">
      <div class="assistant-chat-bubble"><p>Stream this reply.</p>
        <div class="assistant-message-actions"><button aria-label="More response actions">⋮</button></div>
      </div>
    </article>
    <div class="assistant-inline-status"></div>`;
  initializeChatMessageStreamAudioController();
  return document.querySelector('button[aria-label="Stream response audio"]') as HTMLButtonElement;
}

function encodePcm(samples: Int16Array): string {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
  let binary = '';
  bytes.forEach((value) => { binary += String.fromCharCode(value); });
  return window.btoa(binary);
}

function chunk(samples: Int16Array): string {
  return `data: {"type":"chunk","audio_b64":"${encodePcm(samples)}","sample_rate":24000}`;
}

function streamResponse(events: string[]): Response {
  return new Response([...events, 'data: {"type":"done"}', ''].join('\n\n'), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

afterEach(() => {
  document.body.innerHTML = '';
  FakeAudioContext.sources = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('assistant PCM stream player', () => {
  it('uses the selected voice and incremental SSE contract', async () => {
    vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
    vi.stubGlobal('ReadableStream', ReadableStream);
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([chunk(new Int16Array([0, 0]))]));
    vi.stubGlobal('fetch', fetchMock);

    fireEvent.click(renderMessage());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/tts/stream/server-sent-events');
    expect(JSON.parse(String(init.body))).toMatchObject({
      text: 'Stream this reply.',
      speaker: 'ari-clone',
      non_streaming_mode: false,
      parity_mode: true,
    });
    await waitFor(() => expect(document.body).toHaveTextContent('Streaming response audio finished.'));
  });

  it('coalesces gateway blocks into one startup buffer', async () => {
    vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
    vi.stubGlobal('ReadableStream', ReadableStream);
    const block = new Int16Array(2_048);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(
      Array.from({ length: 8 }, () => chunk(block)),
    )));

    fireEvent.click(renderMessage());

    await waitFor(() => expect(FakeAudioContext.sources).toHaveLength(1));
    expect(FakeAudioContext.sources[0].buffer?.length).toBe(16_384);
    expect(FakeAudioContext.sources[0].start).toHaveBeenCalledWith(0.08);
  });

  it('preserves every sample in order without crossfade overlap', async () => {
    vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
    vi.stubGlobal('ReadableStream', ReadableStream);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      chunk(new Int16Array([1_000, -1_000])),
      chunk(new Int16Array([2_000, -2_000])),
    ])));

    fireEvent.click(renderMessage());

    await waitFor(() => expect(FakeAudioContext.sources).toHaveLength(1));
    expect(Array.from(FakeAudioContext.sources[0].buffer?.getChannelData(0) ?? [])).toEqual([
      1_000 / 32_768,
      -1_000 / 32_768,
      2_000 / 32_768,
      -2_000 / 32_768,
    ]);
  });
});
