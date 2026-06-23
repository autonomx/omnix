export type StreamingSttMessage =
  | { type: 'ready' }
  | { type: 'text'; text: string }
  | { type: 'done'; text: string }
  | { type: 'error'; error?: string };

export type StreamingSttSocketLike = {
  readyState: number;
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onclose: (() => void) | null;
  send(data: string): void;
  close(): void;
};

export type StreamingSttWebSocketCtor = {
  readonly OPEN: number;
  new (url: string): StreamingSttSocketLike;
};

export type StreamingSttWebSocketClientOptions = {
  url: string;
  webSocketCtor: StreamingSttWebSocketCtor;
  connectTimeoutMs?: number;
  reconnectDelayMs?: number;
  maxPendingChunks?: number;
  onPartialTranscript?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  onStatusChange?: (status: StreamingSttConnectionStatus) => void;
  onError?: (message: string) => void;
};

export type StreamingSttConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

const TARGET_STT_SAMPLE_RATE = 16_000;
const DEFAULT_CONNECT_TIMEOUT_MS = 5_000;
const DEFAULT_RECONNECT_DELAY_MS = 300;
const DEFAULT_MAX_PENDING_CHUNKS = 250;

export function getDefaultStreamingSttWebSocketUrl(locationLike: Pick<Location, 'protocol' | 'hostname'> = globalThis.location): string {
  const wsProtocol = locationLike.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${locationLike.hostname}:8000/ws/transcribe`;
}

export function downsampleFloat32To16Khz(
  audio: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number = TARGET_STT_SAMPLE_RATE,
): Float32Array {
  if (sourceSampleRate <= 0 || targetSampleRate <= 0) {
    throw new Error('Audio sample rates must be positive.');
  }

  if (sourceSampleRate === targetSampleRate) {
    return new Float32Array(audio);
  }

  const ratio = sourceSampleRate / targetSampleRate;
  const outputLength = Math.max(1, Math.round(audio.length / ratio));
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i += 1) {
    const sourceIndex = i * ratio;
    const index0 = Math.floor(sourceIndex);
    const index1 = Math.min(index0 + 1, audio.length - 1);
    const fraction = sourceIndex - index0;
    output[i] = audio[index0] * (1 - fraction) + audio[index1] * fraction;
  }

  return output;
}

export function encodePcm16Base64(audio: Float32Array): string {
  const int16 = new Int16Array(audio.length);

  for (let i = 0; i < audio.length; i += 1) {
    int16[i] = Math.max(-1, Math.min(1, audio[i])) * 32767;
  }

  const bytes = new Uint8Array(int16.buffer);
  let binary = '';
  const chunkSize = 8192;

  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }

  return globalThis.btoa(binary);
}

export function calculateRms(audio: Float32Array): number {
  if (!audio.length) return 0;

  let sum = 0;
  for (const sample of audio) {
    sum += sample * sample;
  }

  return Math.sqrt(sum / audio.length);
}

export class StreamingSttWebSocketClient {
  private socket: StreamingSttSocketLike | null = null;
  private connecting = false;
  private autoReconnect = false;
  private pendingAudio: Float32Array[] = [];
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly options: StreamingSttWebSocketClientOptions) {}

  async connect(): Promise<void> {
    if (this.socket?.readyState === this.options.webSocketCtor.OPEN) {
      return;
    }

    if (this.connecting) {
      await this.waitForExistingConnection();
      return;
    }

    this.connecting = true;
    this.setStatus('connecting');
    this.clearReconnectTimer();

    await new Promise<void>((resolve, reject) => {
      const socket = new this.options.webSocketCtor(this.options.url);
      this.socket = socket;
      const timeout = setTimeout(() => {
        this.connecting = false;
        this.setStatus('error');
        socket.close();
        reject(new Error('WebSocket connection timeout'));
      }, this.options.connectTimeoutMs ?? DEFAULT_CONNECT_TIMEOUT_MS);

      socket.onopen = () => {
        clearTimeout(timeout);
        this.connecting = false;
        this.autoReconnect = true;
        this.setStatus('connected');
        this.flushPendingAudio();
        resolve();
      };

      socket.onerror = () => {
        clearTimeout(timeout);
        this.connecting = false;
        this.setStatus('error');
        this.options.onError?.('Live voice WebSocket failed.');
      };

      socket.onclose = () => {
        clearTimeout(timeout);
        this.connecting = false;
        this.socket = null;
        this.setStatus('disconnected');
        this.scheduleReconnect();
      };

      socket.onmessage = (event) => this.handleMessage(event.data);
    });
  }

  sendAudio(audio: Float32Array, sampleRate: number): void {
    const audio16k = downsampleFloat32To16Khz(audio, sampleRate);
    const encodedAudio = encodePcm16Base64(audio16k);

    if (!this.socket || this.socket.readyState !== this.options.webSocketCtor.OPEN) {
      this.bufferAudio(audio16k);
      return;
    }

    this.socket.send(JSON.stringify({ type: 'audio', data: encodedAudio }));
  }

  sendFinal(): void {
    this.pendingAudio = [];

    if (this.socket?.readyState === this.options.webSocketCtor.OPEN) {
      this.socket.send(JSON.stringify({ type: 'final' }));
      return;
    }

    this.options.onFinalTranscript?.('');
  }

  disconnect(): void {
    this.autoReconnect = false;
    this.clearReconnectTimer();
    this.pendingAudio = [];

    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }

    this.setStatus('idle');
  }

  private async waitForExistingConnection(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const poll = setInterval(() => {
        if (this.socket?.readyState === this.options.webSocketCtor.OPEN) {
          clearInterval(poll);
          resolve();
        } else if (!this.connecting) {
          clearInterval(poll);
          reject(new Error('WebSocket connection failed'));
        }
      }, 100);
    });
  }

  private handleMessage(rawData: string): void {
    let message: StreamingSttMessage;

    try {
      message = JSON.parse(rawData) as StreamingSttMessage;
    } catch {
      this.options.onError?.('Could not parse live voice transcript message.');
      return;
    }

    switch (message.type) {
      case 'ready':
        return;
      case 'text':
        this.options.onPartialTranscript?.(message.text);
        return;
      case 'done':
        this.options.onFinalTranscript?.(message.text);
        return;
      case 'error':
        this.options.onError?.(message.error ?? 'Live voice transcription failed.');
        this.options.onFinalTranscript?.('');
        return;
      default:
        this.options.onError?.('Unknown live voice transcript message.');
    }
  }

  private bufferAudio(audio: Float32Array): void {
    if (!this.connecting && !this.autoReconnect) return;

    this.pendingAudio.push(audio);
    const maxPendingChunks = this.options.maxPendingChunks ?? DEFAULT_MAX_PENDING_CHUNKS;

    while (this.pendingAudio.length > maxPendingChunks) {
      this.pendingAudio.shift();
    }
  }

  private flushPendingAudio(): void {
    if (!this.socket || this.socket.readyState !== this.options.webSocketCtor.OPEN) return;

    for (const audio of this.pendingAudio) {
      this.socket.send(JSON.stringify({ type: 'audio', data: encodePcm16Base64(audio) }));
    }

    this.pendingAudio = [];
  }

  private scheduleReconnect(): void {
    if (!this.autoReconnect) return;

    this.clearReconnectTimer();
    this.reconnectTimer = setTimeout(() => {
      void this.connect().catch((error) => {
        this.options.onError?.(error instanceof Error ? error.message : 'Live voice reconnect failed.');
      });
    }, this.options.reconnectDelayMs ?? DEFAULT_RECONNECT_DELAY_MS);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setStatus(status: StreamingSttConnectionStatus): void {
    this.options.onStatusChange?.(status);
  }
}
