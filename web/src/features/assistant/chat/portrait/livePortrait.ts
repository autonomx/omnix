import { CHARACTER_AVATAR_RUNTIME_EVENT, LIVE_VOICE_TURN_TIMELINE_EVENT } from '../../../../events/bus';
import {
  recordLiveVoiceReleaseCounter,
  recordLiveVoiceReleaseSamples,
  setLiveVoiceReleasePortrait,
} from '../../workspace/live-voice-release-observer';
import type { LiveVoicePcmSession, LiveVoicePortraitHooks } from '../../workspace/live-voice-pcm-session';
import { PortraitPlaybackClock } from './clock';
import { PortraitCompositor, type PortraitPicture } from './compositor';
import { PortraitFrameBuffer } from './frameBuffer';
import { IDLE_OUTPUT_ID, parsePortraitFrame, TRANSITION_OUTPUT_ID, type PortraitFrameHeader } from './protocol';

/**
 * The live call's portrait (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 3).
 *
 * When the call's avatar pack is a portrait, the live audio session asks the TTS websocket for a hello; its
 * avatar token opens the avatar websocket, whose frames are decoded into a buffer and drawn by what the
 * worklet's clock says is heard. Every 250 ms the play position goes back (`frame_ack`) so the service can
 * commit a phrase's last frames in time. The service also sends the portrait's idle loop, which the compositor
 * shows between replies, and with each reply its transition back to the loop, played once the reply's audio has
 * drained. When the user stops speaking the loop settles on its first frame, where the reply's motion starts.
 * Anything that stops the portrait (no hello, a refusal, a lost stream) leaves the status `unavailable` and the
 * call shows the pack's fallback renderer. The model loads when a call first asks for it: until it is ready the
 * gateway says `loading`, the call shows the fallback and its audio never waits for frames.
 *
 * Each `frame_ack` also says how many speech frames have arrived, how many came too late to draw and how long
 * decoding took; the gateway steps the call's quality level from them (`quality` messages). When frames are still
 * late at the lowest level, the turn shows the fallback (`degraded`) and the next turn tries again.
 */

export type PortraitFallbackRenderer = 'sprite' | 'live2d' | 'orb';
// `degraded`: frames still come too late at the lowest quality level, so this turn shows the fallback.
// `loading`: the portrait model is loading on demand (about a minute); the call shows the fallback meanwhile.
export type LivePortraitStatus = 'off' | 'connecting' | 'loading' | 'ready' | 'degraded' | 'unavailable';
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
const LOWEST_LEVEL = 3;
const PORTRAIT_ENABLED_KEY = 'omnix.livePortrait.enabled';
// A/V offsets go to the release gate a couple of seconds at a time.
const AV_OFFSET_FLUSH_ACKS = 8;
const LATE_FRAMES_TO_DEGRADE = 3;
const OFF: LivePortraitSnapshot = { status: 'off', fallbackRenderer: 'orb', reason: null };

const decodeJpeg: ImageDecoder = (jpeg) => createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' }));

export class LivePortrait {
  private snapshot: LivePortraitSnapshot = OFF;
  private readonly listeners = new Set<() => void>();
  private pack: RuntimePack = null;
  private sessionId = '';
  private liveCallKey: string | null = null;
  private session: LiveVoicePcmSession | null = null;
  private socket: WebSocket | null = null;
  private clock: PortraitPlaybackClock | null = null;
  private buffer = new PortraitFrameBuffer<ImageBitmap>((image) => image.close());
  private readonly compositor = new PortraitCompositor<ImageBitmap>();
  private idleFrames: ImageBitmap[] = [];
  private idleReceived = 0;
  // The latest reply's transition back to the idle loop, by epoch, as its frames arrive; the one before it is
  // kept until this one is complete (the compositor may still be drawing it).
  private transition: { epoch: number; frames: ImageBitmap[]; received: number } | null = null;
  private previousTransition: ImageBitmap[] = [];
  private readySegments = new Set<string>();
  private level = 0;
  private received = 0;
  private late = 0;
  private decodeMs = 0;
  private decoded = 0;
  private degradedEpoch: number | null = null;
  private avOffsets: number[] = [];
  private lastMeasured: ImageBitmap | null = null;
  private acks = 0;
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

  /** Whether the call's avatar is a portrait (the audio session then asks for a hello), unless switched off. */
  wanted(): boolean {
    return this.pack?.renderer === 'portrait' && portraitEnabled();
  }

  /** Start for a call: the hooks go to the live audio session it opens. */
  begin(sessionId: string): LiveVoicePortraitHooks {
    this.end();
    const generation = ++this.generation;
    this.sessionId = sessionId;
    setLiveVoiceReleasePortrait(true);
    this.buffer = new PortraitFrameBuffer<ImageBitmap>((image) => image.close());
    this.publish({ status: 'connecting', fallbackRenderer: this.pack?.fallback_renderer ?? 'orb', reason: null });
    return {
      onHello: ({ callKey, avatarToken }) => {
        if (generation !== this.generation) return;
        this.liveCallKey = callKey;
        this.clearHelloTimer();
        this.connect(avatarToken, generation);
      },
      onWorkletEvent: (event) => {
        if (generation !== this.generation) return;
        this.clock?.observe(event);
        if ((event.type === 'segment_cancelled' || event.type === 'segment_interrupted')
          && typeof event.generation_epoch === 'number') {
          this.buffer.cancelEpoch(event.generation_epoch);
          this.compositor.interrupt(performance.now());
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
    if (this.snapshot.status !== 'unavailable') session.setPortraitClock(true);
    // The session is open: its hello is due now (opening it can wait on the browser's audio and the gateway).
    const generation = this.generation;
    if (this.liveCallKey === null && !this.socket) {
      this.helloTimer = setTimeout(() => this.unavailable('no_hello', generation), HELLO_TIMEOUT_MS);
    }
  }

  /** The frame for what is heard now, or null (keep the last one up, or show the idle portrait). */
  currentFrame(): ImageBitmap | null {
    const position = this.heard();
    return position && this.clock ? this.buffer.frameAt(position, this.clock.rate) : null;
  }

  /** What to draw at `now` (performance time, ms): speech, the held frame, or the idle loop, with crossfades. */
  picture(now: number): PortraitPicture<ImageBitmap> {
    const position = this.heard();
    const speech = position && this.clock ? this.buffer.frameAt(position, this.clock.rate) : null;
    if (speech && speech !== this.lastMeasured) this.measureOffset(speech);
    const context = this.session?.audioContext;
    const stalled = Boolean(context && this.clock?.underrunAt(context.currentTime, outputLatency(context)));
    const drained = Boolean(context && this.clock?.drainedAt(context.currentTime, outputLatency(context)));
    const epoch = speech && position ? this.buffer.epochAt(position) : null;
    return this.compositor.picture(now, speech, stalled, drained, epoch);
  }

  /** The user stopped speaking: a reply is coming, and its motion starts from the idle loop's first frame. */
  settle(): void {
    if (this.snapshot.status === 'ready') this.compositor.settle(performance.now());
  }

  end(): void {
    this.generation += 1;
    this.flushOffsets();
    this.lastMeasured = null;
    setLiveVoiceReleasePortrait(false);
    this.clearHelloTimer();
    if (this.ackTimer) clearInterval(this.ackTimer);
    this.ackTimer = null;
    this.socket?.close(1000, 'call-ended');
    this.socket = null;
    this.session?.setPortraitClock(false);
    this.session = null;
    this.clock = null;
    this.buffer.clear();
    this.compositor.reset();
    for (const image of this.idleFrames) image?.close();
    this.idleFrames = [];
    this.idleReceived = 0;
    this.closeTransitions();
    this.readySegments.clear();
    this.liveCallKey = null;
    this.level = 0;
    this.received = this.late = this.decoded = this.decodeMs = 0;
    this.degradedEpoch = null;
    if (this.snapshot.status !== 'off') this.publish(OFF);
  }

  /** The live call's key while a portrait call is open: speculative TTS for it carries the key. */
  callKey(): string | null {
    return this.snapshot.status === 'off' ? null : this.liveCallKey;
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
      const began = performance.now();
      void this.decode(frame.jpeg).then((image) => {
        if (generation !== this.generation) image.close();
        else if (frame.header.output_id === IDLE_OUTPUT_ID) this.addIdleFrame(frame.header, image);
        else if (frame.header.output_id === TRANSITION_OUTPUT_ID) this.addTransitionFrame(frame.header, image);
        else this.addSpeechFrame(frame.header, image, performance.now() - began);
      }).catch(() => undefined);
    });
    socket.addEventListener('close', () => {
      if (generation === this.generation && (this.snapshot.status === 'ready' || this.snapshot.status === 'loading')) {
        this.unavailable('portrait_lost', generation);
      } else if (generation === this.generation && this.snapshot.status === 'connecting') {
        this.unavailable('avatar_socket_refused', generation);
      }
    });
  }

  private control(raw: string, generation: number): void {
    let message: { type?: string; code?: string; level?: number; fallback_renderer?: PortraitFallbackRenderer };
    try {
      message = JSON.parse(raw) as typeof message;
    } catch {
      return;
    }
    if (message.type === 'ready') {
      this.level = message.level ?? 0;
      // A late hello may have come after the portrait was given up on: the worklet's clock is needed again.
      this.session?.setPortraitClock(true);
      this.publish({ status: 'ready', fallbackRenderer: message.fallback_renderer ?? this.snapshot.fallbackRenderer, reason: null });
      this.ackTimer = setInterval(() => this.acknowledge(), FRAME_ACK_INTERVAL_MS);
    } else if (message.type === 'loading') {
      this.session?.setPortraitClock(false); // no frames for a minute: the replies' audio never waits for them
      this.publish({ status: 'loading', fallbackRenderer: this.snapshot.fallbackRenderer, reason: null });
    } else if (message.type === 'quality' && typeof message.level === 'number') {
      this.level = message.level;
    } else if (message.type === 'unavailable') {
      this.unavailable(message.code ?? 'unavailable', generation);
    }
  }

  /**
   * The drawn frame against what is heard, once per frame: the heard position less the frame's middle, in ms
   * (0 is a frame centred on the sound; positive, a frame behind it).
   */
  private measureOffset(frame: ImageBitmap): void {
    this.lastMeasured = frame;
    const position = this.heard();
    const offset = this.buffer.lastOffset;
    if (!position || offset === null || !this.clock) return;
    const rate = this.buffer.sourceRate(position.segmentId);
    const heard = this.buffer.sourceOffset(position, this.clock.rate);
    this.avOffsets.push(((heard - offset) / rate) * 1000 - 20);
  }

  private flushOffsets(): void {
    recordLiveVoiceReleaseSamples('av_offset_ms', this.avOffsets);
    this.avOffsets = [];
  }

  private addSpeechFrame(header: PortraitFrameHeader, image: ImageBitmap, decodeMs: number): void {
    this.received += 1;
    this.decoded += 1;
    this.decodeMs += decodeMs;
    const late = Boolean(this.clock && this.buffer.isLate(header, this.heard(), this.clock.rate));
    if (late) this.late += 1;
    if (!this.buffer.add(header, image)) return;
    this.framesReady(header.segment_id);
    // A new turn whose frames keep up gets the portrait back.
    if (this.snapshot.status === 'degraded' && !late && header.epoch !== this.degradedEpoch) {
      this.degradedEpoch = null;
      this.publish({ ...this.snapshot, status: 'ready', reason: null });
    }
  }

  /** A segment's first frame is here: a turn's start held for it can play (sent once per segment). */
  private framesReady(segmentId: string): void {
    if (this.readySegments.has(segmentId)) return;
    this.readySegments.add(segmentId);
    if (this.readySegments.size > 64) this.readySegments.delete(this.readySegments.values().next().value as string);
    this.session?.portraitFramesReady(segmentId);
  }

  private addIdleFrame(header: PortraitFrameHeader, image: ImageBitmap): void {
    const count = header.count ?? 0;
    if (count <= 0 || header.offset >= count || this.idleFrames[header.offset]) {
      image.close();
      return;
    }
    this.idleFrames[header.offset] = image;
    this.idleReceived += 1;
    if (this.idleReceived === count) this.compositor.setIdleLoop(this.idleFrames.slice(0, count), performance.now(), header.frame_ms);
  }

  private addTransitionFrame(header: PortraitFrameHeader, image: ImageBitmap): void {
    const count = header.count ?? 0;
    if (count <= 0 || header.offset >= count) {
      image.close();
      return;
    }
    if (this.transition?.epoch !== header.epoch) {
      for (const frame of this.transition?.frames ?? []) frame?.close(); // an incomplete one is never drawn
      this.transition = { epoch: header.epoch, frames: [], received: 0 };
    }
    if (this.transition.frames[header.offset]) {
      image.close();
      return;
    }
    this.transition.frames[header.offset] = image;
    this.transition.received += 1;
    if (this.transition.received < count) return;
    for (const frame of this.previousTransition) frame.close();
    this.previousTransition = this.transition.frames.slice(0, count);
    this.compositor.setTransition(this.previousTransition, header.frame_ms, header.epoch);
    this.transition = null;
  }

  private closeTransitions(): void {
    for (const frame of this.transition?.frames ?? []) frame?.close();
    for (const frame of this.previousTransition) frame.close();
    this.transition = null;
    this.previousTransition = [];
  }

  private acknowledge(): void {
    const position = this.heard();
    const socket = this.socket;
    if (!position || !this.clock || !socket || socket.readyState !== WebSocket.OPEN) return;
    const late = this.late;
    // The service counts the phrase's own TTS samples.
    socket.send(JSON.stringify({ type: 'frame_ack', segment_id: position.segmentId,
      offset: Math.round(this.buffer.sourceOffset(position, this.clock.rate)), received: this.received, late,
      decode_ms: this.decoded ? Math.round(this.decodeMs / this.decoded * 10) / 10 : 0 }));
    this.late = 0;
    this.decodeMs = 0;
    this.decoded = 0;
    this.acks += 1;
    if (this.acks % AV_OFFSET_FLUSH_ACKS === 0) this.flushOffsets();
    if (this.snapshot.status === 'ready' && this.level >= LOWEST_LEVEL && late >= LATE_FRAMES_TO_DEGRADE) {
      this.degradedEpoch = this.buffer.epochAt(position);
      this.publish({ ...this.snapshot, status: 'degraded', reason: 'frames_late' });
      recordLiveVoiceReleaseCounter('portrait_degrade_count', { reason: 'frames_late' });
    }
  }

  private heard() {
    const context = this.session?.audioContext;
    if (!context || !this.clock) return null;
    return this.clock.heardPosition(context.currentTime, outputLatency(context));
  }

  private unavailable(reason: string, generation: number): void {
    if (generation !== this.generation) return;
    this.clearHelloTimer();
    this.session?.setPortraitClock(false); // no frames will come: never hold a start for them
    if (reason === 'portrait_busy') recordLiveVoiceReleaseCounter('portrait_admission_refused');
    else recordLiveVoiceReleaseCounter('portrait_degrade_count', { reason });
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

/** `omnix.livePortrait.enabled` = '0' shows the pack's fallback instead (the release gate's portrait-off run). */
export function portraitEnabled(): boolean {
  try {
    return window.localStorage.getItem(PORTRAIT_ENABLED_KEY) !== '0';
  } catch {
    return true;
  }
}

function outputLatency(context: AudioContext): number {
  return (context as AudioContext & { outputLatency?: number }).outputLatency ?? context.baseLatency ?? 0;
}

/** The page's one live portrait (a call at a time). */
export const livePortrait = new LivePortrait();

/** Follow the live-call runtime's avatar pack; undone (and any portrait ended) when chat is left. */
export function installLivePortrait(): () => void {
  const follow = (event: Event): void => {
    const runtime = (event as CustomEvent<{ avatar_pack?: RuntimePack } | null>).detail;
    livePortrait.setPack(runtime?.avatar_pack ?? null);
  };
  // The user's speech ended: the reply that follows starts from the idle loop's first frame.
  const settle = (event: Event): void => {
    if ((event as CustomEvent<{ event?: string } | null>).detail?.event === 'speech_ended') livePortrait.settle();
  };
  window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, follow);
  window.addEventListener(LIVE_VOICE_TURN_TIMELINE_EVENT, settle);
  return () => {
    window.removeEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, follow);
    window.removeEventListener(LIVE_VOICE_TURN_TIMELINE_EVENT, settle);
    livePortrait.end();
    livePortrait.setPack(null);
  };
}
