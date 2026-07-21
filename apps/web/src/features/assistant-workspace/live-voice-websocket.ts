export type StreamingSttMessage =
  | { type: 'ready'; protocol?: string; connectionId?: string; sampleRate?: number; maxSegmentAudioMs?: number }
  | { type: 'session_ready'; sessionId: string; results?: SegmentedSttResult[] }
  | { type: 'text'; text: string; segmentId?: string; sequence?: number }
  | { type: 'partial'; text: string; segmentId: string; sequence: number }
  | { type: 'done'; text: string }
  | { type: 'audio_buffered'; segmentId: string; sequence: number; acceptedThroughSample: number }
  | { type: 'finalize_queued'; segmentId: string; sequence: number; queuedSegments?: number }
  | SegmentedSttResult
  | { type: 'segment_error'; segmentId?: string; sequence?: number; retryable?: boolean; errorCode?: string; error?: string }
  | { type: 'error'; error?: string };

export type SegmentedSttResult = {
  type: 'result_available';
  sessionId?: string;
  segmentId: string;
  sequence: number;
  resultId: string;
  text: string;
  acceptedThroughSample?: number;
};

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
  hardSegmentMs?: number;
  overlapMs?: number;
  onPartialTranscript?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  onStatusChange?: (status: StreamingSttConnectionStatus) => void;
  onError?: (message: string) => void;
  onSegmentStateChange?: (state: StreamingSttSegmentState) => void;
};

export type StreamingSttConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

export type StreamingSttSegmentState = {
  protocol: 'legacy' | 'segmented-v1';
  sessionId: string;
  activeSequence: number;
  pendingSegments: number;
  queuedSegments: number;
  absoluteSample: number;
};

type PendingSegmentFrame = {
  sampleStart: number;
  sampleEnd: number;
  encodedAudio: string;
};

type PendingSegment = {
  segmentId: string;
  sequence: number;
  captureStartSample: number;
  primaryStartSample: number;
  frames: PendingSegmentFrame[];
  acceptedThroughSample: number;
  finalized: boolean;
  finalizeQueued: boolean;
};

const TARGET_STT_SAMPLE_RATE = 16_000;
const DEFAULT_CONNECT_TIMEOUT_MS = 5_000;
const DEFAULT_RECONNECT_DELAY_MS = 300;
const DEFAULT_MAX_PENDING_CHUNKS = 250;
const DEFAULT_STT_WEBSOCKET_PORT = '5201';
const DEFAULT_HARD_SEGMENT_MS = 10_000;
const DEFAULT_OVERLAP_MS = 300;
const SEGMENTED_PROTOCOL = 'segmented-v1';

export function getDefaultStreamingSttWebSocketUrl(
  locationLike: Pick<Location, 'protocol' | 'hostname'> = globalThis.location,
  sttServiceUrl?: string,
): string {
  if (sttServiceUrl?.trim()) {
    return toStreamingSttWebSocketUrl(sttServiceUrl, locationLike);
  }
  const wsProtocol = locationLike.protocol === 'https:' ? 'wss:' : 'ws:';
  const hostname = localServiceHostname(locationLike.hostname);
  return `${wsProtocol}//${hostname}:${DEFAULT_STT_WEBSOCKET_PORT}/ws/transcribe`;
}

function localServiceHostname(hostname: string): string {
  const normalized = hostname.trim().toLowerCase();
  return normalized === 'localhost' || normalized === '::1' || normalized === '[::1]' ? '127.0.0.1' : hostname;
}

function toStreamingSttWebSocketUrl(value: string, locationLike: Pick<Location, 'protocol' | 'hostname'>): string {
  const baseUrl = `${locationLike.protocol}//${locationLike.hostname}`;
  const url = new URL(value.trim(), baseUrl);
  url.protocol = url.protocol === 'https:' || url.protocol === 'wss:' ? 'wss:' : 'ws:';
  const normalizedPath = url.pathname.replace(/\/+$/, '');
  if (normalizedPath.endsWith('/ws/transcribe')) {
    url.pathname = normalizedPath;
  } else if (normalizedPath.endsWith('/transcribe')) {
    url.pathname = `${normalizedPath.slice(0, -'/transcribe'.length)}/ws/transcribe`;
  } else {
    url.pathname = `${normalizedPath}/ws/transcribe`.replace(/\/{2,}/g, '/');
  }
  url.search = '';
  url.hash = '';
  return url.toString();
}

export function downsampleFloat32To16Khz(
  audio: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number = TARGET_STT_SAMPLE_RATE,
): Float32Array {
  if (sourceSampleRate <= 0 || targetSampleRate <= 0) {
    throw new Error('Audio sample rates must be positive.');
  }
  if (sourceSampleRate === targetSampleRate) return new Float32Array(audio);
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
  for (const sample of audio) sum += sample * sample;
  return Math.sqrt(sum / audio.length);
}

export function deduplicateSegmentBoundary(previous: string, current: string): string {
  const previousTokens = previous.trim().split(/\s+/).filter(Boolean);
  const currentTokens = current.trim().split(/\s+/).filter(Boolean);
  if (!currentTokens.length || !previousTokens.length) return current.trim();
  const maximum = Math.min(16, previousTokens.length, currentTokens.length);
  let overlap = 0;
  for (let count = maximum; count > 0; count -= 1) {
    const left = previousTokens.slice(-count).map(normalizeBoundaryToken);
    const right = currentTokens.slice(0, count).map(normalizeBoundaryToken);
    if (left.every((token, index) => token === right[index])) {
      overlap = count;
      break;
    }
  }
  return currentTokens.slice(overlap).join(' ');
}

function normalizeBoundaryToken(token: string): string {
  return token.toLocaleLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
}

function createRuntimeId(prefix: string): string {
  const cryptoWithUuid = globalThis.crypto as Crypto & { randomUUID?: () => string };
  const suffix = cryptoWithUuid?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function concatFloat32(frames: readonly Float32Array[]): Float32Array {
  const length = frames.reduce((total, frame) => total + frame.length, 0);
  const result = new Float32Array(length);
  let offset = 0;
  for (const frame of frames) {
    result.set(frame, offset);
    offset += frame.length;
  }
  return result;
}

export class StreamingSttWebSocketClient {
  private socket: StreamingSttSocketLike | null = null;
  private connecting = false;
  private autoReconnect = false;
  private serverReady = false;
  private protocol: 'legacy' | 'segmented-v1' = 'legacy';
  private pendingAudio: Float32Array[] = [];
  private pendingFinal = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly sessionId = createRuntimeId('stt-session');
  private readonly captureEpoch = createRuntimeId('capture');
  private absoluteSample = 0;
  private nextSequence = 0;
  private activeSegment: PendingSegment | null = null;
  private readonly pendingSegments = new Map<string, PendingSegment>();
  private readonly pendingResults = new Map<number, SegmentedSttResult>();
  private readonly committedResultIds = new Set<string>();
  private nextCommitSequence = 0;
  private previousCommittedText = '';
  private recentOverlapFrames: Float32Array[] = [];
  private recentOverlapSamples = 0;
  private queuedSegments = 0;

  constructor(private readonly options: StreamingSttWebSocketClientOptions) {}

  get segmentedProtocolActive(): boolean {
    return this.protocol === 'segmented-v1' && this.serverReady;
  }

  get segmentState(): StreamingSttSegmentState {
    return {
      protocol: this.protocol,
      sessionId: this.sessionId,
      activeSequence: this.activeSegment?.sequence ?? this.nextSequence,
      pendingSegments: this.pendingSegments.size,
      queuedSegments: this.queuedSegments,
      absoluteSample: this.absoluteSample,
    };
  }

  async connect(): Promise<void> {
    if (this.socket?.readyState === this.options.webSocketCtor.OPEN) return;
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
      let opened = false;
      let settled = false;
      const failInitialConnection = (message: string) => {
        if (settled) return;
        settled = true;
        this.connecting = false;
        this.autoReconnect = false;
        this.pendingAudio = [];
        this.setStatus('error');
        try { socket.close(); } catch { /* ignore cleanup failures */ }
        reject(new Error(message));
      };
      const timeout = setTimeout(() => failInitialConnection('WebSocket connection timeout'), this.options.connectTimeoutMs ?? DEFAULT_CONNECT_TIMEOUT_MS);
      socket.onopen = () => {
        if (settled) return;
        clearTimeout(timeout);
        opened = true;
        settled = true;
        this.connecting = false;
        this.autoReconnect = true;
        this.setStatus('connected');
        resolve();
      };
      socket.onerror = () => {
        clearTimeout(timeout);
        this.options.onError?.('Live voice WebSocket failed.');
        if (!opened) {
          failInitialConnection('Live voice WebSocket failed.');
          return;
        }
        this.connecting = false;
        this.setStatus('error');
      };
      socket.onclose = () => {
        clearTimeout(timeout);
        this.connecting = false;
        this.serverReady = false;
        this.socket = null;
        if (!opened) {
          failInitialConnection('Live voice WebSocket closed before connecting.');
          return;
        }
        this.setStatus('disconnected');
        this.scheduleReconnect();
      };
      socket.onmessage = (event) => this.handleMessage(event.data);
    });
  }

  sendAudio(audio: Float32Array, sampleRate: number): void {
    const audio16k = downsampleFloat32To16Khz(audio, sampleRate);
    if (!this.socket || this.socket.readyState !== this.options.webSocketCtor.OPEN || !this.serverReady) {
      this.bufferAudio(audio16k);
      return;
    }
    if (this.protocol === 'segmented-v1') this.sendSegmentAudio(audio16k);
    else this.sendLegacyAudio(audio16k);
  }

  sendFinal(): void {
    if (!this.socket || this.socket.readyState !== this.options.webSocketCtor.OPEN || !this.serverReady) {
      this.pendingFinal = true;
      return;
    }
    if (this.protocol === 'segmented-v1') {
      this.finalizeActiveSegment();
      return;
    }
    this.pendingAudio = [];
    this.socket.send(JSON.stringify({ type: 'final' }));
  }

  disconnect(): void {
    this.autoReconnect = false;
    this.clearReconnectTimer();
    this.pendingAudio = [];
    this.pendingFinal = false;
    this.pendingSegments.clear();
    this.pendingResults.clear();
    this.activeSegment = null;
    this.serverReady = false;
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.setStatus('idle');
  }

  private sendLegacyAudio(audio: Float32Array): void {
    this.socket?.send(JSON.stringify({ type: 'audio', data: encodePcm16Base64(audio) }));
  }

  private ensureActiveSegment(): PendingSegment {
    if (this.activeSegment) return this.activeSegment;
    const overlap = concatFloat32(this.recentOverlapFrames);
    const primaryStartSample = this.absoluteSample;
    const captureStartSample = Math.max(0, primaryStartSample - overlap.length);
    const segment: PendingSegment = {
      segmentId: createRuntimeId(`segment-${this.nextSequence}`),
      sequence: this.nextSequence,
      captureStartSample,
      primaryStartSample,
      frames: [],
      acceptedThroughSample: captureStartSample,
      finalized: false,
      finalizeQueued: false,
    };
    this.nextSequence += 1;
    this.activeSegment = segment;
    this.pendingSegments.set(segment.segmentId, segment);
    if (overlap.length) this.sendSegmentFrame(segment, overlap, captureStartSample);
    this.emitSegmentState();
    return segment;
  }

  private sendSegmentAudio(audio: Float32Array): void {
    const segment = this.ensureActiveSegment();
    const sampleStart = this.absoluteSample;
    this.sendSegmentFrame(segment, audio, sampleStart);
    this.absoluteSample += audio.length;
    this.rememberOverlap(audio);
    const hardSegmentSamples = Math.round(TARGET_STT_SAMPLE_RATE * (this.options.hardSegmentMs ?? DEFAULT_HARD_SEGMENT_MS) / 1_000);
    if (this.absoluteSample - segment.primaryStartSample >= hardSegmentSamples) this.finalizeActiveSegment();
    this.emitSegmentState();
  }

  private sendSegmentFrame(segment: PendingSegment, audio: Float32Array, sampleStart: number): void {
    const frame: PendingSegmentFrame = {
      sampleStart,
      sampleEnd: sampleStart + audio.length,
      encodedAudio: encodePcm16Base64(audio),
    };
    segment.frames.push(frame);
    this.sendFrame(segment, frame);
  }

  private sendFrame(segment: PendingSegment, frame: PendingSegmentFrame): void {
    if (!this.socket || this.socket.readyState !== this.options.webSocketCtor.OPEN || !this.serverReady) return;
    this.socket.send(JSON.stringify({
      type: 'audio',
      protocol: SEGMENTED_PROTOCOL,
      sessionId: this.sessionId,
      captureEpoch: this.captureEpoch,
      segmentId: segment.segmentId,
      sequence: segment.sequence,
      captureStartSample: segment.captureStartSample,
      primaryStartSample: segment.primaryStartSample,
      sampleStart: frame.sampleStart,
      sampleEnd: frame.sampleEnd,
      sampleRate: TARGET_STT_SAMPLE_RATE,
      data: frame.encodedAudio,
    }));
  }

  private finalizeActiveSegment(): void {
    const segment = this.activeSegment;
    if (!segment || segment.finalized || this.absoluteSample <= segment.primaryStartSample) return;
    segment.finalized = true;
    this.socket?.send(JSON.stringify({
      type: 'finalize',
      protocol: SEGMENTED_PROTOCOL,
      sessionId: this.sessionId,
      captureEpoch: this.captureEpoch,
      segmentId: segment.segmentId,
      sequence: segment.sequence,
      captureStartSample: segment.captureStartSample,
      primaryStartSample: segment.primaryStartSample,
      endSample: this.absoluteSample,
    }));
    this.activeSegment = null;
    this.emitSegmentState();
  }

  private rememberOverlap(audio: Float32Array): void {
    this.recentOverlapFrames.push(new Float32Array(audio));
    this.recentOverlapSamples += audio.length;
    const maximum = Math.round(TARGET_STT_SAMPLE_RATE * (this.options.overlapMs ?? DEFAULT_OVERLAP_MS) / 1_000);
    while (this.recentOverlapSamples > maximum && this.recentOverlapFrames.length) {
      const first = this.recentOverlapFrames[0];
      const excess = this.recentOverlapSamples - maximum;
      if (first.length <= excess) {
        this.recentOverlapFrames.shift();
        this.recentOverlapSamples -= first.length;
      } else {
        this.recentOverlapFrames[0] = first.slice(excess);
        this.recentOverlapSamples -= excess;
      }
    }
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
        this.protocol = message.protocol === SEGMENTED_PROTOCOL ? 'segmented-v1' : 'legacy';
        this.serverReady = true;
        if (this.protocol === 'segmented-v1') {
          this.socket?.send(JSON.stringify({ type: 'hello', protocol: SEGMENTED_PROTOCOL, sessionId: this.sessionId, captureEpoch: this.captureEpoch }));
          this.replayPendingSegments();
        }
        this.flushPendingAudio();
        if (this.pendingFinal) {
          this.pendingFinal = false;
          this.sendFinal();
        }
        this.emitSegmentState();
        return;
      case 'session_ready':
        message.results?.forEach((result) => this.acceptResult(result));
        return;
      case 'text':
      case 'partial':
        this.options.onPartialTranscript?.(message.text);
        return;
      case 'done':
        this.options.onFinalTranscript?.(message.text);
        return;
      case 'audio_buffered': {
        const segment = this.pendingSegments.get(message.segmentId);
        if (!segment) return;
        segment.acceptedThroughSample = Math.max(segment.acceptedThroughSample, message.acceptedThroughSample);
        segment.frames = segment.frames.filter((frame) => frame.sampleEnd > segment.acceptedThroughSample);
        this.emitSegmentState();
        return;
      }
      case 'finalize_queued': {
        const segment = this.pendingSegments.get(message.segmentId);
        if (segment) segment.finalizeQueued = true;
        this.queuedSegments = message.queuedSegments ?? this.queuedSegments;
        this.emitSegmentState();
        return;
      }
      case 'result_available':
        this.acceptResult(message);
        return;
      case 'segment_error':
        this.options.onError?.(message.error ?? message.errorCode ?? 'Live voice segment failed.');
        if (!message.retryable) this.options.onFinalTranscript?.('');
        return;
      case 'error':
        this.options.onError?.(message.error ?? 'Live voice transcription failed.');
        this.options.onFinalTranscript?.('');
        return;
      default:
        this.options.onError?.('Unknown live voice transcript message.');
    }
  }

  private acceptResult(result: SegmentedSttResult): void {
    if (this.committedResultIds.has(result.resultId) || result.sequence < this.nextCommitSequence) return;
    this.pendingResults.set(result.sequence, result);
    this.commitOrderedResults();
  }

  private commitOrderedResults(): void {
    while (this.pendingResults.has(this.nextCommitSequence)) {
      const result = this.pendingResults.get(this.nextCommitSequence)!;
      this.pendingResults.delete(this.nextCommitSequence);
      this.committedResultIds.add(result.resultId);
      const deduplicated = deduplicateSegmentBoundary(this.previousCommittedText, result.text);
      if (result.text.trim()) this.previousCommittedText = result.text.trim();
      this.pendingSegments.delete(result.segmentId);
      this.nextCommitSequence += 1;
      this.options.onFinalTranscript?.(deduplicated);
    }
    this.emitSegmentState();
  }

  private bufferAudio(audio: Float32Array): void {
    if (!this.connecting && !this.autoReconnect && !this.socket) return;
    this.pendingAudio.push(audio);
    const maxPendingChunks = this.options.maxPendingChunks ?? DEFAULT_MAX_PENDING_CHUNKS;
    while (this.pendingAudio.length > maxPendingChunks) this.pendingAudio.shift();
  }

  private flushPendingAudio(): void {
    if (!this.socket || this.socket.readyState !== this.options.webSocketCtor.OPEN || !this.serverReady) return;
    const pending = this.pendingAudio;
    this.pendingAudio = [];
    for (const audio of pending) {
      if (this.protocol === 'segmented-v1') this.sendSegmentAudio(audio);
      else this.sendLegacyAudio(audio);
    }
  }

  private replayPendingSegments(): void {
    if (!this.segmentedProtocolActive) return;
    for (const segment of [...this.pendingSegments.values()].sort((left, right) => left.sequence - right.sequence)) {
      for (const frame of segment.frames) this.sendFrame(segment, frame);
      if (segment.finalized) {
        this.socket?.send(JSON.stringify({
          type: 'finalize',
          protocol: SEGMENTED_PROTOCOL,
          sessionId: this.sessionId,
          captureEpoch: this.captureEpoch,
          segmentId: segment.segmentId,
          sequence: segment.sequence,
          captureStartSample: segment.captureStartSample,
          primaryStartSample: segment.primaryStartSample,
          endSample: segment.frames.at(-1)?.sampleEnd ?? segment.acceptedThroughSample,
        }));
      }
    }
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

  private emitSegmentState(): void {
    this.options.onSegmentStateChange?.(this.segmentState);
  }
}
