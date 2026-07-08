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
  readonly options: AudioWorkletNodeOptions;
  connect = vi.fn();
  disconnect = vi.fn();

  constructor(
    _context?: BaseAudioContext,
    _name?: string,
    options: AudioWorkletNodeOptions = {},
  ) {
    this.options = options;
    FakeAudioWorkletNode.instances.push(this);
  }
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state: AudioContextState = 'running';
  sampleRate = 24_000;
  destination = {} as AudioDestinationNode;
  audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
  resume = vi.fn(async () => {
    this.state = 'running';
  });
  close = vi.fn().mockResolvedValue(undefined);

  constructor() {
    FakeAudioContext.instances.push(this);
  }
}

type Listener = (event: Event | MessageEvent) => void;

type SentMessage = {
  type?: string;
  text?: string;
  phrase_index?: number;
  diagnostics_stream_id?: string;
  non_streaming_mode?: boolean;
  parity_mode?: boolean;
};

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  binaryType: BinaryType = 'blob';
  readyState = 0;
  sent: string[] = [];
  close = vi.fn((code = 1000, reason = '') => {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.emit('close', { code, reason, wasClean: true } as CloseEvent);
  });
  private listeners = new Map<string, Listener[]>();

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
    let message: SentMessage = {};
    try { message = JSON.parse(text) as SentMessage; } catch { /* no-op */ }
    if (message.type !== 'synthesize') return;
    const streamId = message.diagnostics_stream_id;
    const phraseIndex = message.phrase_index;
    queueMicrotask(() => {
      this.emit('message', {
        data: JSON.stringify({
          type: 'start',
          stream_id: streamId,
          phrase_index: phraseIndex,
          sample_rate: 24_000,
        }),
      } as MessageEvent);
      this.emit('message', { data: new Int16Array([1_000, -1_000]).buffer } as MessageEvent);
      this.emit('message', {
        data: JSON.stringify({
          type: 'done',
          stream_id: streamId,
          phrase_index: phraseIndex,
          partial: false,
        }),
      } as MessageEvent);
    });
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
  it('keeps one AudioContext, worklet, and websocket while buffering multiple phrases', async () => {
    const session = await createLiveVoicePcmSession('live-call:s1:test', 'Jinx', reporter);
    const first = session.enqueuePhrase('First phrase.', 0);
    const second = session.enqueuePhrase('Second phrase.', 1);

    await Promise.all([first, second]);
    await session.finish();

    expect(FakeAudioContext.instances).toHaveLength(1);
    expect(FakeAudioWorkletNode.instances).toHaveLength(1);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('/api/tts/live-call/websocket');
    const sent = FakeWebSocket.instances[0].sent.map((message) => JSON.parse(message) as SentMessage);
    const requests = sent.filter((message) => message.type === 'synthesize');
    expect(requests).toHaveLength(2);
    expect(requests.map((request) => request.text)).toEqual(['First phrase.', 'Second phrase.']);
    expect(requests[0].non_streaming_mode).toBe(false);
    expect(requests[0].parity_mode).toBe(true);
    expect(requests[0].diagnostics_stream_id).toContain('chat-live-');
    expect(sent.filter((message) => message.type === 'diagnostic')).toHaveLength(2);
    expect(sent.at(-1)?.type).toBe('close');

    const messages = FakeAudioWorkletNode.instances[0].port.messages;
    expect(messages.filter((message) => (message as { type?: string }).type === 'push')).toHaveLength(2);
    expect(messages.filter((message) => (message as { type?: string }).type === 'end')).toHaveLength(1);
    expect(FakeAudioWorkletNode.instances[0].options.processorOptions).toMatchObject({
      startBufferSamples: 9_600,
      rebufferSamples: 18_000,
      maxRebufferSamples: 36_000,
      transitionFadeSamples: 192,
    });
    expect(reporter.record).toHaveBeenCalledWith(
      'session_websocket_opened',
      expect.objectContaining({ websocket_path: '/api/tts/live-call/websocket' }),
      'pcm_session',
    );
    expect(reporter.record).toHaveBeenCalledWith(
      'phrase_request_sent',
      expect.objectContaining({ phrase_index: 1, websocket_reused: true }),
      'pcm_session',
    );
    expect(reporter.record).toHaveBeenCalledWith(
      'turn_playback_drained',
      expect.objectContaining({ total_frames: 2, underruns: 0 }),
      'pcm_session',
    );
    expect(FakeWebSocket.instances[0].close).toHaveBeenCalledTimes(1);
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it('closes the turn websocket and worklet on stop', async () => {
    const session = await createLiveVoicePcmSession('live-call:s1:test', 'Jinx', reporter);
    const phrase = session.enqueuePhrase('Interrupt this phrase.', 0);
    await phrase;
    await session.stop('barge-in');

    expect(session.isClosed()).toBe(true);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].close).toHaveBeenCalledWith(1000, 'barge-in');
    expect(FakeAudioWorkletNode.instances[0].port.messages).toContainEqual({ type: 'stop' });
    expect(FakeAudioWorkletNode.instances[0].disconnect).toHaveBeenCalledTimes(1);
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it('resumes playback audio after page visibility or focus changes', async () => {
    const session = await createLiveVoicePcmSession('live-call:s1:test', 'Jinx', reporter);
    const context = FakeAudioContext.instances[0];
    context.state = 'suspended';

    document.dispatchEvent(new Event('visibilitychange'));
    await vi.waitFor(() => expect(context.resume).toHaveBeenCalledTimes(1));

    await vi.waitFor(() => expect(reporter.record).toHaveBeenCalledWith(
      'audio_context_resume_checked',
      expect.objectContaining({
        reason: 'visibilitychange',
        audio_context_state_before: 'suspended',
        audio_context_state_after: 'running',
      }),
      'pcm_session',
    ));

    await session.stop('test-cleanup');
    context.state = 'suspended';
    window.dispatchEvent(new Event('focus'));
    await Promise.resolve();
    expect(context.resume).toHaveBeenCalledTimes(1);
  });
});
