/**
 * Which segment (phrase) is being heard now, and how far into it, from the live-voice worklet's events.
 *
 * The worklet counts each segment's played samples from zero at the AudioContext rate and reports them
 * (`portrait_clock`) with the AudioContext time of the count. What is heard is that time plus the output
 * latency, so the segment heard now is looked up in a history of transitions at `now - latency`; a raw
 * count of the active segment would leave the previous segment's last frames too early. Between reports
 * the position runs on with the clock, but never more than 20 ms past the last report, and not at all
 * while the worklet is waiting for audio (an underrun) or has finished the segment.
 */

export type HeardPosition = {
  segmentId: string;
  /** Samples of the segment heard, at the AudioContext rate. */
  playedSamples: number;
};

type Transition = { at: number; segmentId: string | null; underrun?: boolean };
type Count = { at: number; played: number };

const MAX_EXTRAPOLATION_SECONDS = 0.02;
const MAX_HISTORY = 64;

export class PortraitPlaybackClock {
  private readonly transitions: Transition[] = [];
  private readonly counts = new Map<string, Count>();
  private readonly finished = new Map<string, Count>();
  private active: string | null = null;
  private contextRate: number;

  constructor(contextRate: number) {
    this.contextRate = contextRate;
  }

  /** Feed a worklet event (as `onWorkletEvent` delivers it). */
  observe(event: Record<string, unknown>): void {
    const type = event.type;
    const at = numberField(event.audio_context_time_seconds);
    if (at === null) return;
    const rate = numberField(event.sample_rate);
    if (rate) this.contextRate = rate;
    const segmentId = typeof event.segment_id === 'string' ? event.segment_id : null;
    const played = numberField(event.segment_played_samples);
    if (type === 'segment_started' && segmentId) {
      this.active = segmentId;
      this.transition(at, segmentId);
      this.counts.set(segmentId, { at, played: 0 });
    } else if (type === 'portrait_clock' && segmentId && played !== null) {
      this.counts.set(segmentId, { at, played });
    } else if ((type === 'segment_completed' || type === 'segment_interrupted' || type === 'segment_cancelled')
      && segmentId) {
      if (played !== null) this.finished.set(segmentId, { at, played });
      if (this.active === segmentId) {
        this.active = null;
        this.transition(at, null);
      }
    } else if (type === 'underrun' || type === 'idle' || type === 'stopped') {
      this.transition(at, null, type === 'underrun');
    } else if (type === 'resumed' && this.active) {
      // Playback resumes in the segment the underrun interrupted.
      this.transition(at, this.active);
    }
  }

  /** What is heard at AudioContext time `now` with `outputLatency` seconds between render and ear. */
  heardPosition(now: number, outputLatency: number): HeardPosition | null {
    const heardAt = now - Math.max(0, outputLatency);
    const transition = this.transitionAt(heardAt);
    if (!transition || transition.segmentId === null) return null;
    const segmentId = transition.segmentId;
    const done = this.finished.get(segmentId);
    if (done && done.at <= heardAt) return { segmentId, playedSamples: done.played };
    const count = this.counts.get(segmentId);
    if (!count) return { segmentId, playedSamples: 0 };
    // The latest count is usually newer than what is heard (the latency): run back from it, or forward
    // a little when reports are late. An underrun since the count means nothing has played since.
    const stalled = this.transitions.some((item) => item.at > count.at && item.at <= heardAt && item.segmentId === null);
    const delta = stalled ? 0 : Math.min(heardAt - count.at, MAX_EXTRAPOLATION_SECONDS);
    return { segmentId, playedSamples: Math.max(0, count.played + delta * this.contextRate) };
  }

  /** Whether what is heard at `now` is an underrun (playback waiting for audio mid-segment). */
  underrunAt(now: number, outputLatency: number): boolean {
    return this.transitionAt(now - Math.max(0, outputLatency))?.underrun === true;
  }

  get rate(): number {
    return this.contextRate;
  }

  private transition(at: number, segmentId: string | null, underrun = false): void {
    this.transitions.push({ at, segmentId, underrun });
    if (this.transitions.length > MAX_HISTORY) this.transitions.splice(0, this.transitions.length - MAX_HISTORY);
  }

  private transitionAt(at: number): Transition | null {
    for (let index = this.transitions.length - 1; index >= 0; index -= 1) {
      if (this.transitions[index].at <= at) return this.transitions[index];
    }
    return null;
  }
}

function numberField(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
