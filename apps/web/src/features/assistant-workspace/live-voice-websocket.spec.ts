import { describe, expect, it, vi } from 'vitest';
import {
  StreamingSttWebSocketClient,
  calculateRms,
  deduplicateSegmentBoundary,
  downsampleFloat32To16Khz,
  encodePcm16Base64,
  getDefaultStreamingSttWebSocketUrl,
  type StreamingSttSocketLike,
} from './live-voice-websocket';

describe('live voice websocket helpers', () => {
  it('builds the local transcription websocket URL from the browser location', () => {
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'http:', hostname: 'localhost' })).toBe('ws://127.0.0.1:5201/ws/transcribe');
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'http:', hostname: '::1' })).toBe('ws://127.0.0.1:5201/ws/transcribe');
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'https:', hostname: 'omnix.local' })).toBe('wss://omnix.local:5201/ws/transcribe');
  });

  it('builds the transcription websocket URL from the configured STT service', () => {
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'http:', hostname: 'localhost' }, 'http://localhost:5201/transcribe')).toBe('ws://localhost:5201/ws/transcribe');
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'http:', hostname: 'localhost' }, 'http://127.0.0.1:5201')).toBe('ws://127.0.0.1:5201/ws/transcribe');
    expect(getDefaultStreamingSttWebSocketUrl({ protocol: 'https:', hostname: 'omnix.local' }, 'https://stt.local/ws/transcribe')).toBe('wss://stt.local/ws/transcribe');
  });

  it('downsamples audio frames to 16khz deterministically', () => {
    const input = new Float32Array([0, 0.25, 0.5, 0.75, 1, 0.75]);
    const output = downsampleFloat32To16Khz(input, 48_000, 16_000);
    expect(Array.from(output)).toEqual([0, 0.75]);
  });

  it('encodes clipped pcm16 audio as base64 payloads for the STT websocket', () => {
    expect(encodePcm16Base64(new Float32Array([-2, 0, 2]))).toBe('AYAAAP9/');
  });

  it('calculates rms for voice activity detection', () => {
    expect(calculateRms(new Float32Array([0, 0, 0]))).toBe(0);
    expect(calculateRms(new Float32Array([1, -1]))).toBe(1);
  });

  it('deduplicates bounded transcript overlap', () => {
    expect(deduplicateSegmentBoundary('the quick brown fox', 'brown fox jumps now')).toBe('jumps now');
    expect(deduplicateSegmentBoundary('alpha beta', 'gamma delta')).toBe('gamma delta');
  });

  it('rejects an initial websocket failure instead of leaving a half-open session', async () => {
    const sockets: TestStreamingSocket[] = [];
    const statuses: string[] = [];
    const onError = vi.fn();
    class TestWebSocket extends TestStreamingSocket {
      static readonly OPEN = 1;

      constructor(url: string) {
        super(url);
        sockets.push(this);
      }
    }

    const client = new StreamingSttWebSocketClient({
      url: 'ws://127.0.0.1:5201/ws/transcribe',
      webSocketCtor: TestWebSocket,
      onStatusChange: (status) => statuses.push(status),
      onError,
    });

    const connection = client.connect();
    sockets[0].onerror?.({});

    await expect(connection).rejects.toThrow('Live voice WebSocket failed.');
    expect(onError).toHaveBeenCalledWith('Live voice WebSocket failed.');
    expect(statuses).toEqual(['connecting', 'error']);
    expect(sockets[0].close).toHaveBeenCalledOnce();
  });

  it('rotates to a new segment immediately after finalize', async () => {
    const sockets: TestStreamingSocket[] = [];
    class TestWebSocket extends TestStreamingSocket {
      static readonly OPEN = 1;

      constructor(url: string) {
        super(url);
        sockets.push(this);
      }
    }
    const client = new StreamingSttWebSocketClient({
      url: 'ws://127.0.0.1:5201/ws/transcribe',
      webSocketCtor: TestWebSocket,
      overlapMs: 0,
    });
    const connected = client.connect();
    sockets[0].readyState = TestWebSocket.OPEN;
    sockets[0].onopen?.();
    await connected;
    sockets[0].receive({ type: 'ready', protocol: 'segmented-v1' });

    client.sendAudio(new Float32Array([0.1, 0.2]), 16_000);
    client.sendFinal();
    client.sendAudio(new Float32Array([0.3, 0.4]), 16_000);

    const sent = sockets[0].sentJson();
    const audio = sent.filter((message) => message.type === 'audio');
    const finalize = sent.find((message) => message.type === 'finalize');
    expect(audio).toHaveLength(2);
    expect(audio[0].segmentId).not.toBe(audio[1].segmentId);
    expect(finalize?.segmentId).toBe(audio[0].segmentId);
    expect(audio[1].sequence).toBe(1);
  });

  it('commits out-of-order results in sequence order and suppresses overlap', async () => {
    const sockets: TestStreamingSocket[] = [];
    const finals: string[] = [];
    class TestWebSocket extends TestStreamingSocket {
      static readonly OPEN = 1;

      constructor(url: string) {
        super(url);
        sockets.push(this);
      }
    }
    const client = new StreamingSttWebSocketClient({
      url: 'ws://127.0.0.1:5201/ws/transcribe',
      webSocketCtor: TestWebSocket,
      onAcceptedFinal: async (final) => { finals.push(final.text); return { outcome: 'ignored', segmentId: final.segmentId, sourceSequence: final.sourceSequence, taskContractId: 'test', taskContractVersion: 1 }; },
    });
    const connected = client.connect();
    sockets[0].readyState = TestWebSocket.OPEN;
    sockets[0].onopen?.();
    await connected;
    sockets[0].receive({ type: 'ready', protocol: 'segmented-v1' });

    sockets[0].receive({
      type: 'result_available', sessionId: 'stt-session', captureEpoch: client.segmentState.captureEpoch, segmentId: 's1', sequence: 1, resultId: 'r1', finalizeRequestId: 'f1', startSample: 2, endSample: 4, text: 'brown fox jumps',
    });
    expect(finals).toEqual([]);
    sockets[0].receive({
      type: 'result_available', sessionId: 'stt-session', captureEpoch: client.segmentState.captureEpoch, segmentId: 's0', sequence: 0, resultId: 'r0', finalizeRequestId: 'f0', startSample: 0, endSample: 2, text: 'the brown fox',
    });
    await vi.waitFor(() => expect(finals).toEqual(['the brown fox', 'jumps']));
  });
});

class TestStreamingSocket implements StreamingSttSocketLike {
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => {
    this.onclose?.();
  });

  constructor(readonly url: string) {}

  receive(payload: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  sentJson(): Array<Record<string, unknown>> {
    return this.send.mock.calls.map((call) => JSON.parse(String(call[0])) as Record<string, unknown>);
  }
}
