import { CHARACTER_AVATAR_RUNTIME_EVENT } from '../../../../events/bus';
import type { LiveVoicePcmSession, LiveVoicePortraitHooks } from '../../workspace/live-voice-pcm-session';
import { PortraitPlaybackClock } from './clock';
import { PortraitFrameBuffer } from './frameBuffer';
import { parsePortraitFrame } from './protocol';

/**
 * The live call's portrait (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 3).
 *
 * When the call's avatar pack is a portrait, the live audio session asks the TTS websocket for a hello; its
 * avatar token opens the avatar websocket, whose frames are decoded into a buffer and drawn by what the
 * worklet's clock says is heard. Every 250 ms the play position goes back (`frame_ack`) so the service can
 * commit a phrase's last frames in time. Anything that stops the portrait (no hello, a refusal, a lost
 * stream) leaves the status `unavailable` and the call shows the pack's fallback renderer.
 */

export type PortraitFallbackRenderer = 'sprite' | 'live2d' | 'orb';
export type LivePortraitStatus = 'off' | 'connecting' | 'ready' | 'unavailable';
export type LivePortraitSnapshot = {
  status: LivePortraitStatus;
  fallbackRenderer: PortraitFallbackRenderer;
  reason: string | null;
};

type RuntimePack = { renderer?: string; fallback_renderer?: PortraitFallbackRenderer } | null | undefined;
type ImageDecoder = (jpeg: Uint8Array<ArrayBuffer>) => Promise<ImageBitmap>;

const AVATAR_WEBSOCKET_PATH = '/api/tts/live-call/avatar-websocket';
const HELLO_TIMEOUT_MS = 1_000;
const FRAME_ACK_INTERVAL_MS = 250;
const OFF: LivePortraitSnapshot = { status: 'off', fallbackRenderer: 'orb', reason: null };

const decodeJpeg: ImageDecoder = (jpeg) => createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' }));

export class LivePortrait {
  private snapshot: LivePortraitSnapshot = OFF;
  private readonly listeners = new Set<() => void>();
  private pack: RuntimePack = null;
  private sessionId = '';
  private session: LiveVoicePcmSession | null = null;
  private socket: WebSocket | null = null;
  private clock: PortraitPlaybackClock | null = null;
  private buffer = new PortraitFrameBuffer<ImageBitmap>((image) => image.close());
  private helloTimer: ReturnType<typeof setTimeout> | null = null;
  private ackTimer: ReturnType<typeof setInterval> | null = null;
  private generation = 0;

  constructor(
    private readonly decode: ImageDecoder = decodeJpeg,
    private readonly openSocket: (url: string) => WebSocket = (url) => new WebSocket(url),
  ) {}

  /** The call's avatar pack, as the live-call runtime names it. */
  setPack(pack: RuntimePack): void {
    this.pack = pack;
  }

  /** Whether the call's avatar is a portrait (the audio session then asks for a hello). */
  wanted(): boolean {
    return this.pack?.renderer === 'portrait';
  }

  /** Start for a call: the hooks go to the live audio session it opens. */
  begin(sessionId: string): LiveVoicePortraitHooks {
    this.end();
    const generation = ++this.generation;
    this.sessionId = sessionId;
    this.buffer = new PortraitFrameBuffer<ImageBitmap>((image) => image.close());
    this.publish({ status: 'connecting', fallbackRenderer: this.pack?.fallback_renderer ?? 'orb', reason: null });
    this.helloTimer = setTimeout(() => this.unavailable('no_hello', generation), HELLO_TIMEOUT_MS);
    return {
      onHello: ({ avatarToken }) => {
        if (generation !== this.generation) return;
        this.clearHelloTimer();
        this.connect(avatarToken, generation);
      },
      onWorkletEvent: (event) => {
        if (generation !== this.generation) return;
        this.clock?.observe(event);
        if (event.type === 'segment_cancelled' && typeof event.generation_epoch === 'number') {
          this.buffer.cancelEpoch(event.generation_epoch);
        }
      },
      onSegmentRate: (segmentId, sampleRate) => {
        if (generation === this.generation) this.buffer.setSourceRate(segmentId, sampleRate);
      },
    };
  }

  /** The audio session the hooks belong to: its context is the clock's, and its worklet starts reporting. */
  attachSession(session: LiveVoicePcmSession): void {
    this.session = session;
    this.clock = new PortraitPlaybackClock(session.audioContext.sampleRate);
    session.setPortraitClock(true);
  }

  /** The frame for what is heard now, or null (keep the last one up, or show the idle portrait). */
  currentFrame(): ImageBitmap | null {
    const position = this.heard();
    return position && this.clock ? this.buffer.frameAt(position, this.clock.rate) : null;
  }

  end(): void {
    this.generation += 1;
    this.clearHelloTimer();
    if (this.ackTimer) clearInterval(this.ackTimer);
    this.ackTimer = null;
    this.socket?.close(1000, 'call-ended');
    this.socket = null;
    this.session?.setPortraitClock(false);
    this.session = null;
    this.clock = null;
    this.buffer.clear();
    if (this.snapshot.status !== 'off') this.publish(OFF);
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): LivePortraitSnapshot => this.snapshot;

  private connect(token: string, generation: number): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const query = `token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(this.sessionId)}`;
    const socket = this.openSocket(`${protocol}//${window.location.host}${AVATAR_WEBSOCKET_PATH}?${query}`);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;
    socket.addEventListener('message', (event: MessageEvent<string | ArrayBuffer>) => {
      if (generation !== this.generation) return;
      if (typeof event.data === 'string') {
        this.control(event.data, generation);
        return;
      }
      const frame = parsePortraitFrame(event.data);
      if (!frame) return;
      void this.decode(frame.jpeg).then((image) => {
        if (generation === this.generation) this.buffer.add(frame.header, image);
        else image.close();
      }).catch(() => undefined);
    });
    socket.addEventListener('close', () => {
      if (generation === this.generation && this.snapshot.status === 'ready') this.unavailable('portrait_lost', generation);
      else if (generation === this.generation && this.snapshot.status === 'connecting') {
        this.unavailable('avatar_socket_refused', generation);
      }
    });
  }

  private control(raw: string, generation: number): void {
    let message: { type?: string; code?: string; fallback_renderer?: PortraitFallbackRenderer };
    try {
      message = JSON.parse(raw) as typeof message;
    } catch {
      return;
    }
    if (message.type === 'ready') {
      this.publish({ status: 'ready', fallbackRenderer: message.fallback_renderer ?? this.snapshot.fallbackRenderer, reason: null });
      this.ackTimer = setInterval(() => this.acknowledge(), FRAME_ACK_INTERVAL_MS);
    } else if (message.type === 'unavailable') {
      this.unavailable(message.code ?? 'unavailable', generation);
    }
  }

  private acknowledge(): void {
    const position = this.heard();
    const socket = this.socket;
    if (!position || !this.clock || !socket || socket.readyState !== WebSocket.OPEN) return;
    // The service counts the phrase's own TTS samples.
    socket.send(JSON.stringify({ type: 'frame_ack', segment_id: position.segmentId,
      offset: Math.round(this.buffer.sourceOffset(position, this.clock.rate)) }));
  }

  private heard() {
    const context = this.session?.audioContext;
    if (!context || !this.clock) return null;
    const latency = (context as AudioContext & { outputLatency?: number }).outputLatency ?? context.baseLatency ?? 0;
    return this.clock.heardPosition(context.currentTime, latency);
  }

  private unavailable(reason: string, generation: number): void {
    if (generation !== this.generation) return;
    this.clearHelloTimer();
    this.publish({ status: 'unavailable', fallbackRenderer: this.snapshot.fallbackRenderer, reason });
  }

  private clearHelloTimer(): void {
    if (this.helloTimer) clearTimeout(this.helloTimer);
    this.helloTimer = null;
  }

  private publish(snapshot: LivePortraitSnapshot): void {
    this.snapshot = snapshot;
    for (const listener of this.listeners) listener();
  }
}

/** The page's one live portrait (a call at a time). */
export const livePortrait = new LivePortrait();

/** Follow the live-call runtime's avatar pack; undone (and any portrait ended) when chat is left. */
export function installLivePortrait(): () => void {
  const follow = (event: Event): void => {
    const runtime = (event as CustomEvent<{ avatar_pack?: RuntimePack } | null>).detail;
    livePortrait.setPack(runtime?.avatar_pack ?? null);
  };
  window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, follow);
  return () => {
    window.removeEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, follow);
    livePortrait.end();
    livePortrait.setPack(null);
  };
}
