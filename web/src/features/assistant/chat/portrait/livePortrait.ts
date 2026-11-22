import { CHARACTER_AVATAR_RUNTIME_EVENT, LIVE_VOICE_TURN_TIMELINE_EVENT } from '../../../../events/bus';
import {
  recordLiveVoiceReleaseCounter,
  recordLiveVoiceReleaseSamples,
  setLiveVoiceReleasePortrait,
} from '../../workspace/live-voice-release-observer';
import type { LiveVoicePcmSession, LiveVoicePortraitHooks, PortraitStartRule } from '../../workspace/live-voice-pcm-session';
import { PortraitPlaybackClock } from './clock';
import { PortraitCompositor, type PortraitPicture } from './compositor';
import { startTicker } from '../../../../shared/timers';
import { PortraitFrameBuffer } from './frameBuffer';
import { packRevision, rememberMemberLoop, resetMemberLoops } from './memberIdleLoops';
import {
  BLINK_OUTPUT_ID,
  IDLE_OUTPUT_ID,
  parsePortraitFrame,
  TRANSITION_OUTPUT_ID,
  type PortraitFrameHeader,
} from './protocol';

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
 * gateway says `loading`, the call shows the fallback and its audio never waits for frames. With too little memory
 * to load, `loading` carries the reason and lasts until memory frees or the call ends. `portraitNotice` says why
 * the portrait is not showing.
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
  /** The group call's member whose face this is (companion 5.5); absent for the chat's own character. */
  speakerId?: string;
};

type RuntimePack = {
  character_id?: string; renderer?: string; fallback_renderer?: PortraitFallbackRenderer;
  version?: number | null; base_asset_id?: string | null;
} | null | undefined;
/** The group call's member a session speaks as, and that member's avatar pack. */
export type LivePortraitSpeaker = { id: string; pack: RuntimePack };
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
const EMPTY_LOOP_BYTES = () => ({ idle: [] as Uint8Array<ArrayBuffer>[], blink: [] as Uint8Array<ArrayBuffer>[], idleCount: 0, blinkCount: 0, frameMs: 0 });

const decodeJpeg: ImageDecoder = (jpeg) => createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' }));

export class LivePortrait {
  private snapshot: LivePortraitSnapshot = OFF;
  private readonly listeners = new Set<() => void>();
  private pack: RuntimePack = null;
  private speaker: LivePortraitSpeaker | null = null;
  private sessionId = '';
  // The idle loop's and blink twins' JPEGs as they arrive: the member's tile plays them once another member speaks.
  private loopBytes: { idle: Uint8Array<ArrayBuffer>[]; blink: Uint8Array<ArrayBuffer>[]; idleCount: number; blinkCount: number; frameMs: number } = EMPTY_LOOP_BYTES();
  private liveCallKey: string | null = null;
  private session: LiveVoicePcmSession | null = null;
  private socket: WebSocket | null = null;
  private lastPicture: { now: number; picture: PortraitPicture<ImageBitmap> } | null = null;
  private clock: PortraitPlaybackClock | null = null;
  private buffer = new PortraitFrameBuffer<ImageBitmap>((image) => image.close());
  private readonly compositor = new PortraitCompositor<ImageBitmap>();
  private idleFrames: ImageBitmap[] = [];
  private idleReceived = 0;
  private blinkFrames: ImageBitmap[] = [];
  private blinkReceived = 0;
  // The latest reply's transition back to the idle loop, by epoch, as its frames arrive; the one before it is
  // kept until this one is complete (the compositor may still be drawing it).
  private transition: { epoch: number; frames: ImageBitmap[]; received: number } | null = null;
  private previousTransition: ImageBitmap[] = [];
  // Replaced transitions the compositor may still be playing: closed once it no longer shows them.
  private retiredTransitions: ImageBitmap[][] = [];
  // How much of each segment its frames cover (ms), as last told to the session's start hold.
  private coverage = new Map<string, number>();
  // The call's engine's start hold, from the gateway's `ready` (none yet: the session's default, D-5's 250 ms).
  private startRule: PortraitStartRule | undefined;
  private level = 0;
  private received = 0;
  private late = 0;
  private decodeMs = 0;
  private decoded = 0;
  private degradedEpoch: number | null = null;
  // The epoch of the speech frame last drawn: the turn on screen, also through its clause silences.
  private shownEpoch: number | null = null;
  private avOffsets: number[] = [];
  private lastMeasured: ImageBitmap | null = null;
  private acks = 0;
  private helloTimer: ReturnType<typeof setTimeout> | null = null;
  private stopAcks: (() => void) | null = null;
  private generation = 0;

  constructor(
    private readonly decode: ImageDecoder = decodeJpeg,
    private readonly openSocket: (url: string) => WebSocket = (url) => new WebSocket(url),
  ) {}

  /** The call's avatar pack, as the live-call runtime names it. */
  setPack(pack: RuntimePack): void {
    this.pack = pack;
  }

  /**
   * Whether the speaking member's avatar is a portrait (the audio session then asks for a hello), unless switched off
   * or not asked for in this chat (`requestLiveVideo`): a guest's own pack when a guest speaks, else the call's.
   */
  wanted(chatSessionId: string | null, speaker: LivePortraitSpeaker | null = null): boolean {
    return (speaker ? speaker.pack : this.pack)?.renderer === 'portrait' && portraitEnabled()
      && liveVideoRequested(chatSessionId);
  }

  /**
   * Start for a call's audio session: the hooks go to the session it opens. A group call's guest speaking opens its
   * own session, and the face shown is that guest's.
   */
  begin(sessionId: string, speaker: LivePortraitSpeaker | null = null): LiveVoicePortraitHooks {
    this.end();
    const generation = ++this.generation;
    this.sessionId = sessionId;
    this.speaker = speaker;
    setLiveVoiceReleasePortrait(true);
    this.buffer = new PortraitFrameBuffer<ImageBitmap>((image) => image.close());
    const pack = speaker ? speaker.pack : this.pack;
    this.publish({ status: 'connecting', fallbackRenderer: pack?.fallback_renderer ?? 'orb', reason: null });
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
    // A session that finished opening after its call ended (hung up while it opened): nothing to attach to.
    if (this.snapshot.status === 'off') return;
    this.session = session;
    this.clock = new PortraitPlaybackClock(session.audioContext.sampleRate);
    // The clock, and with it the start hold, only once frames can come: connecting or loading, none can, and a
    // hold would only delay the audio (``ready`` turns it on).
    session.setPortraitClock(this.snapshot.status === 'ready' || this.snapshot.status === 'degraded', this.startRule);
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
    // Asked once a frame per canvas (the call panel stays mounted under fullscreen); one frame's canvases share a time.
    if (this.lastPicture?.now === now) return this.lastPicture.picture;
    const picture = this.computePicture(now);
    this.lastPicture = { now, picture };
    return picture;
  }

  private computePicture(now: number): PortraitPicture<ImageBitmap> {
    const position = this.heard();
    const speech = position && this.clock ? this.buffer.frameAt(position, this.clock.rate) : null;
    if (speech && speech !== this.lastMeasured) this.measureOffset(speech);
    const context = this.session?.audioContext;
    const stalled = Boolean(context && this.clock?.underrunAt(context.currentTime, outputLatency(context)));
    const drained = Boolean(context && this.clock?.drainedAt(context.currentTime, outputLatency(context)));
    const epoch = speech && position ? this.buffer.epochAt(position) : null;
    if (epoch !== null) this.shownEpoch = epoch;
    this.closeRetiredTransitions();
    return this.compositor.picture(now, speech, stalled, drained, epoch);
  }

  /** The user stopped speaking: a reply is coming, and its motion starts from the idle loop's first frame. */
  settle(): void {
    if (this.snapshot.status === 'ready') this.compositor.settle(performance.now());
  }

  end(): void {
    this.lastPicture = null; // its frames are released below
    this.generation += 1;
    this.flushOffsets();
    this.lastMeasured = null;
    setLiveVoiceReleasePortrait(false);
    this.clearHelloTimer();
    this.stopAcks?.();
    this.stopAcks = null;
    this.socket?.close(1000, 'call-ended');
    this.socket = null;
    this.session?.setPortraitClock(false);
    this.session = null;
    this.clock = null;
    this.buffer.clear();
    this.compositor.reset();
    for (const image of [...this.idleFrames, ...this.blinkFrames]) image?.close();
    this.idleFrames = [];
    this.idleReceived = 0;
    this.blinkFrames = [];
    this.blinkReceived = 0;
    this.loopBytes = EMPTY_LOOP_BYTES();
    this.speaker = null;
    this.closeTransitions();
    this.coverage.clear();
    this.startRule = undefined;
    this.liveCallKey = null;
    this.level = 0;
    this.received = this.late = this.decoded = this.decodeMs = 0;
    this.degradedEpoch = null;
    this.shownEpoch = null;
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
    const speaker = this.speaker ? `&speaker_id=${encodeURIComponent(this.speaker.id)}` : '';
    const query = `token=${encodeURIComponent(token)}&session_id=${encodeURIComponent(this.sessionId)}${speaker}`;
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
      this.keepLoopBytes(frame.header, frame.jpeg);
      const began = performance.now();
      void this.decode(frame.jpeg).then((image) => {
        if (generation !== this.generation) image.close();
        else if (frame.header.output_id === IDLE_OUTPUT_ID) this.addIdleFrame(frame.header, image);
        else if (frame.header.output_id === BLINK_OUTPUT_ID) this.addBlinkFrame(frame.header, image);
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
    let message: {
      type?: string; code?: string; level?: number; fallback_renderer?: PortraitFallbackRenderer;
      start_hold_ms?: number; start_lead_ms?: number;
    };
    try {
      message = JSON.parse(raw) as typeof message;
    } catch {
      return;
    }
    if (message.type === 'ready') {
      this.level = message.level ?? 0;
      if (typeof message.start_hold_ms === 'number') {
        this.startRule = { holdMs: message.start_hold_ms, leadMs: Math.max(0, message.start_lead_ms ?? 0) };
      }
      // A late hello may have come after the portrait was given up on: the worklet's clock is needed again.
      this.session?.setPortraitClock(true, this.startRule);
      this.publish({ status: 'ready', fallbackRenderer: message.fallback_renderer ?? this.snapshot.fallbackRenderer, reason: null });
      this.stopAcks = startTicker(() => this.acknowledge(), FRAME_ACK_INTERVAL_MS);
    } else if (message.type === 'loading') {
      this.session?.setPortraitClock(false); // no frames for a minute: the replies' audio never waits for them
      this.publish({ status: 'loading', fallbackRenderer: this.snapshot.fallbackRenderer, reason: message.code ?? null });
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
    this.framesReady(header);
    // A new turn whose frames keep up gets the portrait back.
    if (this.snapshot.status === 'degraded' && !late && header.epoch !== this.degradedEpoch) {
      this.degradedEpoch = null;
      this.publish({ ...this.snapshot, status: 'ready', reason: null });
    }
  }

  /** How much of its segment a frame's arrival covers, for a turn's start held for it: the first frame, then (when
   * the engine's start waits for video ahead) each further frame until the lead is covered. */
  private framesReady(header: PortraitFrameHeader): void {
    const segmentId = header.segment_id;
    const rate = this.buffer.sourceRate(segmentId);
    const coveredMs = ((header.offset + rate / 25) / rate) * 1000;
    const told = this.coverage.get(segmentId);
    if (told !== undefined && (told >= (this.startRule?.leadMs ?? 0) || coveredMs <= told)) return;
    this.coverage.delete(segmentId); // the newest last, so the oldest goes first
    this.coverage.set(segmentId, coveredMs);
    if (this.coverage.size > 64) this.coverage.delete(this.coverage.keys().next().value as string);
    this.session?.portraitFramesReady(segmentId, coveredMs);
  }

  /** The member's idle loop, kept as JPEGs once whole, for its tile while another member speaks. */
  private keepLoopBytes(header: PortraitFrameHeader, jpeg: Uint8Array<ArrayBuffer>): void {
    const blink = header.output_id === BLINK_OUTPUT_ID;
    if (!blink && header.output_id !== IDLE_OUTPUT_ID) return;
    const count = header.count ?? 0;
    const frames = blink ? this.loopBytes.blink : this.loopBytes.idle;
    if (count <= 0 || header.offset >= count || frames[header.offset]) return;
    frames[header.offset] = jpeg.slice();
    if (blink) this.loopBytes.blinkCount = count;
    else {
      this.loopBytes.idleCount = count;
      this.loopBytes.frameMs = header.frame_ms ?? this.loopBytes.frameMs; // the loop's pace; a blink's own is shorter
    }
    const { idle, idleCount, blinkCount, frameMs } = this.loopBytes;
    const whole = (list: readonly Uint8Array[], total: number) => total > 0 && list.filter(Boolean).length === total;
    const memberId = this.speaker?.id ?? this.pack?.character_id;
    if (memberId && whole(idle, idleCount) && whole(this.loopBytes.blink, blinkCount) && frameMs > 0) {
      const revision = packRevision(this.speaker ? this.speaker.pack : this.pack);
      rememberMemberLoop(this.sessionId, memberId,
        { frameMs, idle: idle.slice(0, idleCount), blink: this.loopBytes.blink.slice(0, blinkCount) }, revision);
    }
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

  private addBlinkFrame(header: PortraitFrameHeader, image: ImageBitmap): void {
    const count = header.count ?? 0;
    if (count <= 0 || header.offset >= count || this.blinkFrames[header.offset]) {
      image.close();
      return;
    }
    this.blinkFrames[header.offset] = image;
    this.blinkReceived += 1;
    if (this.blinkReceived === count) this.compositor.setBlink(this.blinkFrames.slice(0, count));
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
    // The one it replaces may still be playing (a reply's transition while the next reply's arrives).
    if (this.previousTransition.length) this.retiredTransitions.push(this.previousTransition);
    this.previousTransition = this.transition.frames.slice(0, count);
    this.compositor.setTransition(this.previousTransition, header.frame_ms, header.epoch);
    this.closeRetiredTransitions();
    this.transition = null;
  }

  private closeRetiredTransitions(): void {
    this.retiredTransitions = this.retiredTransitions.filter((frames) => {
      if (this.compositor.shows(frames)) return true;
      for (const frame of frames) frame.close();
      return false;
    });
  }

  private closeTransitions(): void {
    for (const frame of this.transition?.frames ?? []) frame?.close();
    for (const frame of this.previousTransition) frame.close();
    for (const frames of this.retiredTransitions) for (const frame of frames) frame.close();
    this.retiredTransitions = [];
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
      // A clause silence or a cue has no frames: the turn degraded is the one on screen.
      this.degradedEpoch = this.buffer.epochAt(position) ?? this.shownEpoch;
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
    this.snapshot = { ...snapshot, speakerId: snapshot.status === 'off' ? undefined : this.speaker?.id };
    for (const listener of this.listeners) listener();
  }
}

const MEMORY_SHORT = 'model_busy';
const NOT_ENOUGH_MEMORY = 'Live portrait unavailable: not enough memory. It starts on its own once you free some.';
const UNAVAILABLE_NOTICES: Record<string, string> = {
  [MEMORY_SHORT]: 'Live portrait unavailable: not enough memory. Free some and try again.',
  model_missing: 'Live portrait unavailable: its models are not installed. Download them in Settings, Models.',
  model_failed: 'Live portrait unavailable: its model failed to load.',
  warming: 'Live portrait unavailable: its model took too long to load.',
  portrait_not_configured: 'Live portrait unavailable: the portrait service is not set up.',
  service_unreachable: 'Live portrait unavailable: the portrait service is not answering.',
  portrait_busy: 'Live portrait unavailable: another live call is using it.',
  no_face: 'Live portrait unavailable: no face was found in the portrait image.',
  image_too_large: 'Live portrait unavailable: the portrait image is too large.',
  image_unreadable: 'Live portrait unavailable: the portrait image could not be read.',
  portrait_lost: 'Live portrait stopped during this call.',
};

/** Why a call is not showing its portrait, for the person on the call; null while it shows or is about to. */
export function portraitNotice({ status, reason }: LivePortraitSnapshot): string | null {
  if (status === 'loading') return reason === MEMORY_SHORT ? NOT_ENOUGH_MEMORY : 'Live portrait is loading…';
  if (status === 'degraded') return 'Live portrait paused for this reply: its frames are arriving late.';
  if (status !== 'unavailable') return null;
  return UNAVAILABLE_NOTICES[reason ?? ''] ?? 'Live portrait unavailable for this call.';
}

/** `omnix.livePortrait.enabled` = '0' shows the pack's fallback instead (the release gate's portrait-off run). */
export function portraitEnabled(): boolean {
  try {
    return window.localStorage.getItem(PORTRAIT_ENABLED_KEY) !== '0';
  } catch {
    return true;
  }
}

/*
 * Live video is asked for per chat (owner, 2026-11-22): starting a call does not bring the portrait up; "Load live
 * video" does, for that chat until the page reloads, so a call can be voice only. Asked for during a call, it starts
 * with the next reply's audio session.
 */
const videoChats = new Set<string>();
const videoListeners = new Set<() => void>();

export function requestLiveVideo(chatSessionId: string): void {
  if (videoChats.has(chatSessionId)) return;
  videoChats.add(chatSessionId);
  videoListeners.forEach((listener) => listener());
}

/** Turns live video back off for a chat: its next call is voice only until asked again. */
export function cancelLiveVideo(chatSessionId: string): void {
  if (!videoChats.delete(chatSessionId)) return;
  videoListeners.forEach((listener) => listener());
}

export function liveVideoRequested(chatSessionId: string | null | undefined): boolean {
  return Boolean(chatSessionId) && videoChats.has(chatSessionId ?? '');
}

export function subscribeLiveVideo(listener: () => void): () => void {
  videoListeners.add(listener);
  return () => { videoListeners.delete(listener); };
}

/** Forget every chat's request (tests). */
export function resetLiveVideoRequests(): void {
  videoChats.clear();
  videoListeners.forEach((listener) => listener());
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
    resetMemberLoops();
  };
}
