import type { HeardPosition } from './clock';
import type { PortraitFrameHeader } from './protocol';

/**
 * Decoded portrait frames by segment (phrase), chosen by what is heard.
 *
 * A frame's offset counts its phrase's own TTS samples; the clock counts AudioContext samples, so each
 * segment's source rate converts between them (the TTS websocket's `start`/`format` give it). The frame
 * drawn is the newest one at or before the heard position; older frames of that segment are released.
 */

const DEFAULT_SOURCE_RATE = 24_000;
const FRAMES_PER_SECOND = 25;
const MAX_SEGMENTS = 12;

type Stored<T> = { offset: number; epoch: number; image: T };
type Segment<T> = { frames: Stored<T>[] };

export class PortraitFrameBuffer<T> {
  private readonly segments = new Map<string, Segment<T>>();
  private readonly sourceRates = new Map<string, number>();
  private readonly cancelledEpochs = new Set<number>();
  private readonly release: (image: T) => void;
  /** The offset of the frame ``frameAt`` last returned (the A/V offset is measured against it). */
  lastOffset: number | null = null;

  constructor(release: (image: T) => void = () => undefined) {
    this.release = release;
  }

  setSourceRate(segmentId: string, sampleRate: number): void {
    if (sampleRate > 0) this.sourceRates.set(segmentId, sampleRate);
  }

  /** Store a frame; false (and released) when its turn was cancelled. */
  add(header: PortraitFrameHeader, image: T): boolean {
    if (this.cancelledEpochs.has(header.epoch)) {
      this.release(image);
      return false;
    }
    let segment = this.segments.get(header.segment_id);
    if (!segment) {
      segment = { frames: [] };
      this.segments.set(header.segment_id, segment);
      this.pruneSegments();
    }
    const frames = segment.frames;
    let index = frames.length;
    while (index > 0 && frames[index - 1].offset > header.offset) index -= 1;
    frames.splice(index, 0, { offset: header.offset, epoch: header.epoch, image });
    return true;
  }

  /** Drop a cancelled turn's frames, and any that arrive for it later. */
  cancelEpoch(epoch: number): void {
    this.cancelledEpochs.add(epoch);
    for (const segment of this.segments.values()) {
      segment.frames = segment.frames.filter((frame) => {
        if (frame.epoch !== epoch) return true;
        this.release(frame.image);
        return false;
      });
    }
  }

  /** What is heard, in the segment's own TTS samples (what frame offsets count). */
  sourceOffset(position: HeardPosition, contextRate: number): number {
    const rate = this.sourceRates.get(position.segmentId) ?? DEFAULT_SOURCE_RATE;
    return position.playedSamples * rate / contextRate;
  }

  sourceRate(segmentId: string): number {
    return this.sourceRates.get(segmentId) ?? DEFAULT_SOURCE_RATE;
  }

  /** Whether a frame arrived after its time: its segment is heard more than a frame-time past it. */
  isLate(header: PortraitFrameHeader, position: HeardPosition | null, contextRate: number): boolean {
    if (!position || position.segmentId !== header.segment_id) return false;
    const rate = this.sourceRates.get(header.segment_id) ?? DEFAULT_SOURCE_RATE;
    return this.sourceOffset(position, contextRate) > header.offset + rate / FRAMES_PER_SECOND;
  }

  /** The frame for what is heard, or null when its segment has none yet (a silence, a cue, a late frame). */
  frameAt(position: HeardPosition, contextRate: number): T | null {
    const segment = this.segments.get(position.segmentId);
    if (!segment || !segment.frames.length) return null;
    const sourceOffset = this.sourceOffset(position, contextRate);
    let chosen = -1;
    for (let index = 0; index < segment.frames.length && segment.frames[index].offset <= sourceOffset; index += 1) {
      chosen = index;
    }
    if (chosen < 0) return null;
    for (const stale of segment.frames.splice(0, chosen)) this.release(stale.image);
    this.lastOffset = segment.frames[0].offset;
    return segment.frames[0].image;
  }

  /** The turn (epoch) of the segment heard, from its frames; null when it has none. */
  epochAt(position: HeardPosition): number | null {
    return this.segments.get(position.segmentId)?.frames[0]?.epoch ?? null;
  }

  clear(): void {
    for (const segment of this.segments.values()) for (const frame of segment.frames) this.release(frame.image);
    this.segments.clear();
  }

  get frameCount(): number {
    let count = 0;
    for (const segment of this.segments.values()) count += segment.frames.length;
    return count;
  }

  private pruneSegments(): void {
    while (this.segments.size > MAX_SEGMENTS) {
      const oldest = this.segments.keys().next().value as string;
      for (const frame of this.segments.get(oldest)?.frames ?? []) this.release(frame.image);
      this.segments.delete(oldest);
    }
  }
}
