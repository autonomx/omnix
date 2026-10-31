/**
 * What the portrait canvas shows on each animation frame (roadmap Phase 3, "Gaps, underruns and cues";
 * transitions as rated 2026-10-30).
 *
 * While a phrase is heard, its frame for the heard position. A reply's motion starts from the idle loop's first
 * frame, so once the user stops speaking the loop is steered there (the shorter way, at its own pace) and then sways
 * slowly over its first few frames, which stay within about one step of speech motion of it (rated 2026-10-31: a
 * face held dead still while the reply was thought of looked frozen). The reply then cuts in with no blend, from
 * whichever of those frames is on screen. A pause inside a reply (a
 * clause silence, a late phrase, an underrun) holds the last frame. When the reply's audio has drained, the
 * service's transition frames take the face back to the loop's first frame, and the loop resumes from there. A
 * pixel crossfade, which shows two poses at once, is left only as the fallback: a reply that comes before the loop
 * has settled, or playback that drains without a transition. A cancelled or interrupted turn cuts to the idle
 * loop: its frames are already released, so there is nothing to fade from. The loop's last frame blends into its
 * first as it wraps (its seam moves about three times as much as a normal step).
 */

export const GAP_TO_IDLE_MS = 250;
export const HOLD_MAX_MS = 1_500;
export const CROSSFADE_MS = 80;
export const IDLE_FRAME_MS = 40;
export const SETTLE_HOLD_MS = 10_000;
// The sway while settled: out over the loop's first 240 ms of motion (three idle frames, about six rendered frames
// of idle motion at a quarter of a speech step each) and back, eased, every 2 s.
export const SWAY_LOOP_MS = 240;
export const SWAY_PERIOD_MS = 2_000;

/** Draw `under`, then `over` (when set) at `alpha` on top of it. */
export type PortraitPicture<T> = { under: T | null; over: T | null; alpha: number };

type Settle = { from: number; direction: 1 | -1; since: number; reachedAt: number | null };
type Transition<T> = { frames: T[]; frameMs: number; since: number };

export class PortraitCompositor<T> {
  private idle: T[] = [];
  private mode: 'speech' | 'transition' | 'idle' = 'idle';
  private lastSpeech: T | null = null;
  private gapSince: number | null = null;
  private fadeSince: number | null = null;
  private idleSince = 0;
  private idleFrameMs = IDLE_FRAME_MS;
  private settling: Settle | null = null;
  // The reply its transition belongs to (its epoch), and the reply whose speech was last shown: a transition plays
  // only as its own reply ends (it can arrive before that reply even starts playing).
  private transition: { frames: T[]; frameMs: number; epoch: number | null } | null = null;
  private playing: Transition<T> | null = null;
  private speechEpoch: number | null = null;

  /** The idle loop, complete, with its frame period; it starts from its first frame. */
  setIdleLoop(frames: T[], now: number, frameMs = IDLE_FRAME_MS): void {
    this.idle = frames;
    this.idleSince = now;
    this.idleFrameMs = frameMs > 0 ? frameMs : IDLE_FRAME_MS;
    this.settling = null;
  }

  /** The user stopped speaking: steer the idle loop to its first frame, the shorter way, and sway near it. */
  settle(now: number): void {
    if (this.mode !== 'idle' || this.idle.length < 2 || this.settling) return;
    const position = this.loopPosition(now);
    this.settling = {
      from: position,
      direction: this.idle.length - position <= position ? 1 : -1,
      since: now,
      reachedAt: null,
    };
  }

  /** A reply's frames back to the idle loop's first frame: played once that reply's audio has drained. */
  setTransition(frames: T[], frameMs = IDLE_FRAME_MS, epoch: number | null = null): void {
    this.transition = frames.length ? { frames, frameMs: frameMs > 0 ? frameMs : IDLE_FRAME_MS, epoch } : null;
  }

  /** A turn was cancelled or interrupted: its frames are gone, so cut to the idle loop. */
  interrupt(now: number): void {
    this.lastSpeech = null;
    this.mode = 'idle';
    this.gapSince = null;
    this.fadeSince = null;
    this.idleSince = now;
    this.settling = null;
    this.transition = null;
    this.playing = null;
  }

  reset(): void {
    this.idle = [];
    this.interrupt(0);
  }

  /**
   * The picture at `now` (ms), given the speech frame for what is heard (or null) and its reply's epoch, whether
   * playback stalled, and whether it has drained (nothing queued: the reply's audio is over, or a phrase is late).
   */
  picture(now: number, speech: T | null, stalled: boolean, drained = false, epoch: number | null = null): PortraitPicture<T> {
    if (speech) {
      this.gapSince = null;
      if (this.mode !== 'speech') {
        const continuous = this.mode === 'idle' && this.settledAt(now);
        this.fadeSince = this.mode === 'idle' && this.idle.length && !continuous ? now : null;
        this.mode = 'speech';
        this.settling = null;
        this.playing = null;
      }
      this.lastSpeech = speech;
      this.speechEpoch = epoch;
      const alpha = this.fade(now);
      return alpha < 1 ? { under: this.idleFrame(now), over: speech, alpha } : { under: speech, over: null, alpha: 0 };
    }
    if (this.mode === 'speech') {
      this.gapSince ??= now;
      const gap = now - this.gapSince;
      const own = this.transition !== null
        && (this.transition.epoch === null || this.speechEpoch === null || this.transition.epoch === this.speechEpoch);
      if (this.transition && own && drained && !stalled) {
        this.mode = 'transition';
        this.playing = { ...this.transition, since: now };
        this.transition = null;
      } else if (stalled || !this.idle.length || gap < (drained ? GAP_TO_IDLE_MS : HOLD_MAX_MS)) {
        return { under: this.lastSpeech, over: null, alpha: 0 };
      } else {
        this.mode = 'idle';
        this.fadeSince = now;
        this.idleSince = now;
      }
    }
    if (this.mode === 'transition' && this.playing) {
      const index = Math.floor((now - this.playing.since) / this.playing.frameMs);
      if (index < this.playing.frames.length) return { under: this.playing.frames[index], over: null, alpha: 0 };
      // Its last frame leads into the loop's first: the loop resumes there, without a blend.
      this.playing = null;
      this.mode = 'idle';
      this.lastSpeech = null;
      this.idleSince = now;
      this.fadeSince = null;
    }
    const idleFrame = this.idleFrame(now);
    const alpha = this.fade(now);
    if (alpha < 1 && this.lastSpeech) return { under: this.lastSpeech, over: idleFrame, alpha };
    if (idleFrame === null) return { under: this.lastSpeech, over: null, alpha: 0 };
    if (this.settling) return this.swaying(now) ?? { under: idleFrame, over: null, alpha: 0 };
    return this.wrapping(now) ?? { under: idleFrame, over: null, alpha: 0 };
  }

  /** Whether the idle loop has reached its first frame and sways near it (where a reply's motion starts). */
  private settledAt(now: number): boolean {
    if (!this.settling) return false;
    this.idleIndex(now);
    return this.settling !== null && this.settling.reachedAt !== null;
  }

  /** On the loop's last frame: the first one over it, more of it as the wrap nears. */
  private wrapping(now: number): PortraitPicture<T> | null {
    if (this.idle.length < 2) return null;
    const position = Math.max(0, now - this.idleSince) / this.idleFrameMs;
    const index = Math.floor(position) % this.idle.length;
    if (index !== this.idle.length - 1) return null;
    return { under: this.idle[index], over: this.idle[0], alpha: position - Math.floor(position) };
  }

  /** Settled: between the two loop frames either side of the sway's position, blended by how far it is between them. */
  private swaying(now: number): PortraitPicture<T> | null {
    const reachedAt = this.settling?.reachedAt;
    if (reachedAt === null || reachedAt === undefined) return null;
    const position = this.swayPosition(now, reachedAt);
    const index = Math.floor(position);
    const alpha = position - index;
    return alpha > 0 && index + 1 < this.idle.length
      ? { under: this.idle[index], over: this.idle[index + 1], alpha }
      : { under: this.idle[index], over: null, alpha: 0 };
  }

  /** Where the sway is, in loop frames from the first (fractional): out and back, eased, from `reachedAt`. */
  private swayPosition(now: number, reachedAt: number): number {
    const span = Math.min(this.idle.length - 1, Math.max(1, Math.round(SWAY_LOOP_MS / this.idleFrameMs)));
    const phase = (2 * Math.PI * Math.max(0, now - reachedAt)) / SWAY_PERIOD_MS;
    return (span * (1 - Math.cos(phase))) / 2;
  }

  private fade(now: number): number {
    if (this.fadeSince === null) return 1;
    const alpha = (now - this.fadeSince) / CROSSFADE_MS;
    if (alpha >= 1) this.fadeSince = null;
    return Math.min(1, Math.max(0, alpha));
  }

  /** Where the free-running loop is, in frames (fractional). */
  private loopPosition(now: number): number {
    return (Math.max(0, now - this.idleSince) / this.idleFrameMs) % this.idle.length;
  }

  private idleIndex(now: number): number {
    const settling = this.settling;
    if (!settling) return Math.floor(this.loopPosition(now));
    const position = settling.from + settling.direction * ((now - settling.since) / this.idleFrameMs);
    if (settling.direction > 0 ? position < this.idle.length : position > 0) return Math.floor(position);
    settling.reachedAt ??= now;
    const sway = Math.floor(this.swayPosition(now, settling.reachedAt));
    if (now - settling.reachedAt > SETTLE_HOLD_MS) {
      // No reply came: the loop runs on from the frame the sway is on.
      this.settling = null;
      this.idleSince = now - sway * this.idleFrameMs;
    }
    return sway;
  }

  private idleFrame(now: number): T | null {
    if (!this.idle.length) return null;
    return this.idle[this.idleIndex(now)];
  }
}
