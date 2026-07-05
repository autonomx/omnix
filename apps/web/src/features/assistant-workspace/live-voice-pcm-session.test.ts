import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createLiveVoicePcmSession } from './live-voice-pcm-session';

class FakePort {
  onmessage: ((event: MessageEvent) => void) | null = null;
  messages: unknown[] = [];

  postMessage(message: unknown): void {
    this.messages.push(message);
    const type = (message as { type?: string })?.type;
    if (type === 'push') {
      const samples = (message as { samples?: Float32Array }).samples;
      queueMicrotask(() => this.onmessage?.({
        data: {
          type: 'buffered',
          buffered_samples: samples?.length ?? 0,
          incoming_samples: samples?.length ?? 0,
        },
      } as MessageEvent));
    }
    if (type === 'end') {
      queueMicrotask(() => this.onmessage?.({ data: { type: 'drained', buffered_samples: 0 } } as MessageEvent));
    }
  }
}

class FakeAudioWorkletNode {
  static instances: FakeAudioWorkletNode[] = [];
  readonly port = new FakePort();
  connect = vi.fn();
  disconnect = vi.fn();

  constructor() {
    FakeAudioWorkletNode.instances.push(this);
  }
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state: AudioContextState = 'running';
  sampleRate = 24_000;
  destination = {} as AudioDestinationNode;
  audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);

  constructor() {
    FakeAudioContext.instances.push(this);
  }
}

type Listener = (event: Event | MessageEvent) => void;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  binaryType: BinaryType = 'blob';
  readyState = 0;
  sent: string[] = [];
  private listeners = new Map<string, Listener[]>();
  private requestStarted = false;

  constructor(url: string | URL) {
    this.url = String(url);
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = 1;
      this.emit('open', new Event('open'));
    });
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject | null): void {
    if (!listener) return;
    const callback: Listener = typeof listener === 'function'
      ? listener as Listener
      : (event) => listener.handleEvent(event);
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), callback]);
  }

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
    const text = String(data);
    this.sent.push(text);
    let message: { type?: string } = {};
    try { message = JSON.parse(text) as { type?: string }; } catch { /* no-op */ }
    if (message.type === 'diagnostic' || this.requestStarted) return;
    this.requestStarted = true;
    queueMicrotask(() => {
      this.emit('message', { data: JSON.stringify({ type: 'start', sample_rate: 24_000 }) } as MessageEvent);
      this.emit('message', { data: new Int16Array([1_000, -1_000]).buffer } as MessageEvent);
      this.emit('message', { data: JSON.stringify({ type: 'done', partial: false }) } as MessageEvent);
    });
  }

  close(code = 1000, reason = ''): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.emit('close', { code, reason, wasClean: true } as CloseEvent);
  }

  private emit(type: string, event: Event | MessageEvent): void {
    (this.listeners.get(type) ?? []).forEach((listener) => listener(event));
  }
}

const reporter = {
  traceId: 'live-call:s1:test',
  record: vi.fn(),
  flush: vi.fn(async () => undefined),
  close: vi.fn(async () => undefined),
};

beforeEach(() => {
  FakeAudioContext.instances = [];
  FakeAudioWorkletNode.instances = [];
  FakeWebSocket.instances = [];
  reporter.record.mockClear();
  vi.stubGlobal('AudioContext', FakeAudioContext as unknown as typeof AudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode as unknown as typeof AudioWorkletNode);
  vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('live voice PCM session', () => {
  it('keeps one AudioContext and worklet while buffering multiple phrase streams', async () => {
    const session = await createLiveVoicePcmSession('live-call:s1:test', 'Jinx', reporter);
    const first = session.enqueuePhrase('First phrase.', 0);
    const second = session.enqueuePhrase('Second phrase.', 1);

    await Promise.all([first, second]);
    await session.finish();

    expect(FakeAudioContext.instances).toHaveLength(1);
    expect(FakeAudioWorkletNode.instances).toHaveLength(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
    const messages = FakeAudioWorkletNode.instances[0].port.messages;
    expect(messages.filter((message) => (message as { type?: string }).type === 'push')).toHaveLength(2);
    expect(messages.filter((message) => (message as { type?: string }).type === 'end')).toHaveLength(1);
    expect(reporter.record).toHaveBeenCalledWith(
      'turn_playback_drained',
      expect.objectContaining({ total_frames: 2, underruns: 0 }),
      'pcm_session',
    );
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it('closes the active phrase socket and worklet on stop', async () => {
    const session = await createLiveVoicePcmSession('live-call:s1:test', 'Jinx', reporter);
    const phrase = session.enqueuePhrase('Interrupt this phrase.', 0);
    await phrase;
    await session.stop('barge-in');

    expect(session.isClosed()).toBe(true);
    expect(FakeAudioWorkletNode.instances[0].port.messages).toContainEqual({ type: 'stop' });
    expect(FakeAudioWorkletNode.instances[0].disconnect).toHaveBeenCalledTimes(1);
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledTimes(1);
  });
});
