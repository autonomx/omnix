import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { initializeChatMessageStreamAudioController } from './chat-message-stream-audio-controller';

let cleanupController: (() => void) | null = null;

class FakeMessagePort {
  onmessage: ((event: MessageEvent) => void) | null = null;
  messages: unknown[] = [];
  start = vi.fn();
  close = vi.fn();

  postMessage(message: unknown): void {
    this.messages.push(message);
    if ((message as { type?: string })?.type === 'end') {
      queueMicrotask(() => this.onmessage?.({ data: { type: 'drained' } } as MessageEvent));
    }
  }

  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  dispatchEvent = vi.fn().mockReturnValue(true);
}

class FakeAudioWorkletNode {
  static nodes: FakeAudioWorkletNode[] = [];
  readonly port = new FakeMessagePort();
  readonly options: AudioWorkletNodeOptions;
  connect = vi.fn();
  disconnect = vi.fn();

  constructor(
    _context: BaseAudioContext,
    _name: string,
    options: AudioWorkletNodeOptions = {},
  ) {
    this.options = options;
    FakeAudioWorkletNode.nodes.push(this);
  }
}

class FakeAudioContext {
  static contexts: FakeAudioContext[] = [];
  state: AudioContextState = 'running';
  sampleRate = 24_000;
  destination = {} as AudioDestinationNode;
  audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);

  constructor() {
    FakeAudioContext.contexts.push(this);
  }

  createBufferSource(): AudioBufferSourceNode {
    throw new Error('continuous AudioWorklet playback must not schedule AudioBufferSourceNode blocks');
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
  cleanupController = initializeChatMessageStreamAudioController();
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

function installAudioWorkletFakes(): void {
  vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode as unknown as typeof AudioWorkletNode);
  vi.stubGlobal('ReadableStream', ReadableStream);
}

afterEach(() => {
  cleanupController?.();
  cleanupController = null;
  document.body.innerHTML = '';
  FakeAudioContext.contexts = [];
  FakeAudioWorkletNode.nodes = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('assistant PCM stream player', () => {
  it('uses the selected voice and lower-latency Qwen streaming contract', async () => {
    installAudioWorkletFakes();
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([chunk(new Int16Array([0, 0]))]));
    vi.stubGlobal('fetch', fetchMock);

    fireEvent.click(renderMessage());

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/tts/stream/server-sent-events');
    expect(JSON.parse(String(init.body))).toMatchObject({
      text: 'Stream this reply.',
      speaker: 'ari-clone',
      chunk_size: 8,
      non_streaming_mode: false,
      parity_mode: true,
    });
    await waitFor(() => expect(document.body).toHaveTextContent('Streaming response audio finished.'));
  });

  it('uses one worklet with stable rebuffer and smoothed transition reserves', async () => {
    installAudioWorkletFakes();
    const block = new Int16Array(2_048);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse(
      Array.from({ length: 8 }, () => chunk(block)),
    )));

    fireEvent.click(renderMessage());

    await waitFor(() => expect(FakeAudioWorkletNode.nodes).toHaveLength(1));
    const [node] = FakeAudioWorkletNode.nodes;
    expect(node.options.processorOptions).toMatchObject({
      startBufferSamples: 36_000,
      rebufferSamples: 24_000,
      transitionFadeSamples: 192,
    });
    expect(node.connect).toHaveBeenCalledTimes(1);
    expect(FakeAudioContext.contexts[0].audioWorklet.addModule).toHaveBeenCalledTimes(1);
  });

  it('posts every PCM sample to the continuous queue in exact order', async () => {
    installAudioWorkletFakes();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([
      chunk(new Int16Array([1_000, -1_000])),
      chunk(new Int16Array([2_000, -2_000])),
    ])));

    fireEvent.click(renderMessage());

    await waitFor(() => expect(document.body).toHaveTextContent('Streaming response audio finished.'));
    const pushMessages = FakeAudioWorkletNode.nodes[0].port.messages
      .filter((message) => (message as { type?: string }).type === 'push') as Array<{
        type: string;
        samples: Float32Array;
      }>;
    expect(pushMessages).toHaveLength(2);
    expect(Array.from(pushMessages[0].samples)).toEqual([
      1_000 / 32_768,
      -1_000 / 32_768,
    ]);
    expect(Array.from(pushMessages[1].samples)).toEqual([
      2_000 / 32_768,
      -2_000 / 32_768,
    ]);
  });
});
