import { describe, expect, it, vi } from 'vitest';
import {
  StreamingSttWebSocketClient,
  calculateRms,
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
}
