/**
 * What the portrait canvas shows on each animation frame (roadmap Phase 3, "Gaps, underruns and cues").
 *
 * While a phrase is heard, its frame for the heard position. Through a gap (a clause silence, a wait for the next
 * phrase, a cue, a late frame) the last speaking frame is held; once the gap passes 250 ms it crossfades (80 ms)
 * into the idle loop, and the next speech crossfades back from it. During an underrun the frame freezes until
 * playback resumes. Before the first speech the idle loop plays. A cancelled or interrupted turn cuts to the idle
 * loop: its frames are already released, so there is nothing to fade from.
 */

export const GAP_TO_IDLE_MS = 250;
export const CROSSFADE_MS = 80;
export const IDLE_FRAME_MS = 40;

/** Draw `under`, then `over` (when set) at `alpha` on top of it. */
export type PortraitPicture<T> = { under: T | null; over: T | null; alpha: number };

export class PortraitCompositor<T> {
  private idle: T[] = [];
  private mode: 'speech' | 'idle' = 'idle';
  private lastSpeech: T | null = null;
  private gapSince: number | null = null;
  private fadeSince: number | null = null;
  private idleSince = 0;
  private idleFrameMs = IDLE_FRAME_MS;

  /** The idle loop, complete, with its frame period; it starts from its first frame. */
  setIdleLoop(frames: T[], now: number, frameMs = IDLE_FRAME_MS): void {
    this.idle = frames;
    this.idleSince = now;
    this.idleFrameMs = frameMs > 0 ? frameMs : IDLE_FRAME_MS;
  }

  /** A turn was cancelled or interrupted: its frames are gone, so cut to the idle loop. */
  interrupt(now: number): void {
    this.lastSpeech = null;
    this.mode = 'idle';
    this.gapSince = null;
    this.fadeSince = null;
    this.idleSince = now;
  }

  reset(): void {
    this.idle = [];
    this.interrupt(0);
  }

  /** The picture at `now` (ms), given the speech frame for what is heard (or null) and whether playback stalled. */
  picture(now: number, speech: T | null, stalled: boolean): PortraitPicture<T> {
    if (speech) {
      this.gapSince = null;
      if (this.mode === 'idle') {
        this.mode = 'speech';
        this.fadeSince = this.idle.length ? now : null;
      }
      this.lastSpeech = speech;
      const alpha = this.fade(now);
      return alpha < 1 ? { under: this.idleFrame(now), over: speech, alpha } : { under: speech, over: null, alpha: 0 };
    }
    if (this.mode === 'speech') {
      this.gapSince ??= now;
      if (stalled || now - this.gapSince < GAP_TO_IDLE_MS || !this.idle.length) {
        return { under: this.lastSpeech, over: null, alpha: 0 };
      }
      this.mode = 'idle';
      this.fadeSince = now;
      this.idleSince = now;
    }
    const idleFrame = this.idleFrame(now);
    const alpha = this.fade(now);
    if (alpha < 1 && this.lastSpeech) return { under: this.lastSpeech, over: idleFrame, alpha };
    return { under: idleFrame ?? this.lastSpeech, over: null, alpha: 0 };
  }

  private fade(now: number): number {
    if (this.fadeSince === null) return 1;
    const alpha = (now - this.fadeSince) / CROSSFADE_MS;
    if (alpha >= 1) this.fadeSince = null;
    return Math.min(1, Math.max(0, alpha));
  }

  private idleFrame(now: number): T | null {
    if (!this.idle.length) return null;
    const index = Math.floor(Math.max(0, now - this.idleSince) / this.idleFrameMs) % this.idle.length;
    return this.idle[index];
  }
}
