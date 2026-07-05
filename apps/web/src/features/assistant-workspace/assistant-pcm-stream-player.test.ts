import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { initializeChatMessageStreamAudioController } from './chat-message-stream-audio-controller';

let cleanupController: (() => void) | null = null;

type SocketListener = (event: Event | MessageEvent) => void;

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

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static frames: ArrayBuffer[] = [];

  readonly url: string;
  binaryType: BinaryType = 'blob';
  sent: string[] = [];
  private listeners = new Map<string, SocketListener[]>();

  constructor(url: string | URL) {
    this.url = String(url);
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => this.emit('open', new Event('open')));
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject | null): void {
    if (!listener) return;
    const callback: SocketListener = typeof listener === 'function'
      ? listener as SocketListener
      : (event) => listener.handleEvent(event);
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), callback]);
  }

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
    this.sent.push(String(data));
    queueMicrotask(() => {
      this.emit('message', { data: JSON.stringify({ type: 'start', sample_rate: 24_000 }) } as MessageEvent);
      FakeWebSocket.frames.forEach((frame) => {
        this.emit('message', { data: frame } as MessageEvent);
      });
      this.emit('message', { data: JSON.stringify({ type: 'done' }) } as MessageEvent);
    });
  }

  close(): void {
    this.emit('close', new Event('close'));
  }

  private emit(type: string, event: Event | MessageEvent): void {
    (this.listeners.get(type) ?? []).forEach((listener) => listener(event));
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

function pcmFrame(samples: Int16Array): ArrayBuffer {
  return samples.buffer.slice(samples.byteOffset, samples.byteOffset + samples.byteLength) as ArrayBuffer;
}

function installAudioFakes(frames: ArrayBuffer[]): void {
  FakeWebSocket.frames = frames;
  vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode as unknown as typeof AudioWorkletNode);
  vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket);
}

afterEach(() => {
  cleanupController?.();
  cleanupController = null;
  document.body.innerHTML = '';
  FakeAudioContext.contexts = [];
  FakeAudioWorkletNode.nodes = [];
  FakeWebSocket.instances = [];
  FakeWebSocket.frames = [];
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('assistant PCM stream player', () => {
  it('uses binary websocket PCM without imposing a fixed audio-token cap', async () => {
    installAudioFakes([pcmFrame(new Int16Array([0, 0]))]);

    fireEvent.click(renderMessage());

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const [socket] = FakeWebSocket.instances;
    await waitFor(() => expect(socket.sent).toHaveLength(1));
    expect(new URL(socket.url).pathname).toBe('/api/tts/stream/websocket');
    expect(socket.binaryType).toBe('arraybuffer');
    const requestBody = JSON.parse(socket.sent[0]) as Record<string, unknown>;
    expect(requestBody).toMatchObject({
      text: 'Stream this reply.',
      speaker: 'ari-clone',
      chunk_size: 8,
      non_streaming_mode: false,
      parity_mode: true,
    });
    expect(requestBody).not.toHaveProperty('max_new_tokens');
    await waitFor(() => expect(document.body).toHaveTextContent('Streaming response audio finished.'));
  });

  it('keeps the adaptive AudioWorklet startup and recovery reserves', async () => {
    installAudioFakes(Array.from({ length: 8 }, () => pcmFrame(new Int16Array(2_400))));

    fireEvent.click(renderMessage());

    await waitFor(() => expect(FakeAudioWorkletNode.nodes).toHaveLength(1));
    const [node] = FakeAudioWorkletNode.nodes;
    expect(node.options.processorOptions).toMatchObject({
      startBufferSamples: 48_000,
      rebufferSamples: 36_000,
      maxRebufferSamples: 72_000,
      transitionFadeSamples: 192,
    });
    expect(node.connect).toHaveBeenCalledTimes(1);
    expect(FakeAudioContext.contexts[0].audioWorklet.addModule).toHaveBeenCalledTimes(1);
  });

  it('posts every binary PCM sample to the continuous queue in exact order', async () => {
    installAudioFakes([
      pcmFrame(new Int16Array([1_000, -1_000])),
      pcmFrame(new Int16Array([2_000, -2_000])),
    ]);

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
