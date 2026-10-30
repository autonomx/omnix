import { describe, expect, it } from 'vitest';
import { PortraitPlaybackClock } from './clock';
import { PortraitFrameBuffer } from './frameBuffer';
import { parsePortraitFrame, type PortraitFrameHeader } from './protocol';

const CONTEXT_RATE = 48_000;

function frameMessage(header: Record<string, unknown>, jpeg = [0xff, 0xd8, 0xff]): ArrayBuffer {
  const json = new TextEncoder().encode(JSON.stringify(header));
  const buffer = new ArrayBuffer(4 + json.length + jpeg.length);
  new DataView(buffer).setUint32(0, json.length, false);
  new Uint8Array(buffer, 4).set(json);
  new Uint8Array(buffer, 4 + json.length).set(jpeg);
  return buffer;
}

function header(segment: string, offset: number, epoch = 1): PortraitFrameHeader {
  return { output_id: `turn-${epoch}`, epoch, segment_id: segment, offset };
}

describe('portrait frames on the wire', () => {
  it('reads the header and the JPEG behind it', () => {
    const parsed = parsePortraitFrame(frameMessage({ output_id: 'turn-3', epoch: 3, segment_id: 'seg', offset: 960 }));
    expect(parsed?.header).toEqual({ output_id: 'turn-3', epoch: 3, segment_id: 'seg', offset: 960 });
    expect(Array.from(parsed?.jpeg ?? [])).toEqual([0xff, 0xd8, 0xff]);
  });

  it('refuses short, oversized or malformed messages', () => {
    expect(parsePortraitFrame(new ArrayBuffer(2))).toBeNull();
    const huge = new ArrayBuffer(8);
    new DataView(huge).setUint32(0, 5000, false);
    expect(parsePortraitFrame(huge)).toBeNull();
    expect(parsePortraitFrame(frameMessage({ output_id: 'x', epoch: 1, segment_id: 's' }))).toBeNull();
  });
});

describe('the portrait playback clock', () => {
  it('runs on between reports, but no more than 20 ms past the last one', () => {
    const clock = new PortraitPlaybackClock(CONTEXT_RATE);
    clock.observe({ type: 'segment_started', segment_id: 'a', audio_context_time_seconds: 10 });
    clock.observe({ type: 'portrait_clock', segment_id: 'a', segment_played_samples: 4800, audio_context_time_seconds: 10.1 });
    expect(clock.heardPosition(10.11, 0)?.playedSamples).toBeCloseTo(4800 + 0.01 * CONTEXT_RATE);
    expect(clock.heardPosition(10.5, 0)?.playedSamples).toBeCloseTo(4800 + 0.02 * CONTEXT_RATE);
  });

  it('looks up the segment heard after the output latency, not the one rendering now', () => {
    const clock = new PortraitPlaybackClock(CONTEXT_RATE);
    clock.observe({ type: 'segment_started', segment_id: 'a', audio_context_time_seconds: 10 });
    clock.observe({ type: 'portrait_clock', segment_id: 'a', segment_played_samples: 47_040, audio_context_time_seconds: 10.98 });
    clock.observe({ type: 'segment_completed', segment_id: 'a', segment_played_samples: 48_000, audio_context_time_seconds: 11 });
    clock.observe({ type: 'segment_started', segment_id: 'b', audio_context_time_seconds: 11 });
    // Rendering is 10 ms into b, but with 50 ms of output latency the ear is 0.96 s into a.
    const heard = clock.heardPosition(11.01, 0.05);
    expect(heard?.segmentId).toBe('a');
    expect(heard?.playedSamples).toBeCloseTo(0.96 * CONTEXT_RATE);
    expect(clock.heardPosition(11.06, 0.05)?.segmentId).toBe('b');
    // After a segment ends, its last count holds (its final frames stay up).
    expect(clock.heardPosition(11.04, 0.0)?.segmentId).toBe('b');
  });

  it('holds still during an underrun and resumes in the same segment', () => {
    const clock = new PortraitPlaybackClock(CONTEXT_RATE);
    clock.observe({ type: 'segment_started', segment_id: 'a', audio_context_time_seconds: 0 });
    clock.observe({ type: 'portrait_clock', segment_id: 'a', segment_played_samples: 9600, audio_context_time_seconds: 0.2 });
    clock.observe({ type: 'underrun', audio_context_time_seconds: 0.205 });
    expect(clock.heardPosition(0.3, 0)).toBeNull();
    clock.observe({ type: 'resumed', audio_context_time_seconds: 0.4 });
    expect(clock.heardPosition(0.41, 0)).toEqual({ segmentId: 'a', playedSamples: 9600 });
  });

  it('knows nothing before the first segment, and nothing in a gap between segments', () => {
    const clock = new PortraitPlaybackClock(CONTEXT_RATE);
    expect(clock.heardPosition(5, 0)).toBeNull();
    clock.observe({ type: 'segment_started', segment_id: 'a', audio_context_time_seconds: 1 });
    clock.observe({ type: 'segment_completed', segment_id: 'a', segment_played_samples: 100, audio_context_time_seconds: 2 });
    expect(clock.heardPosition(2.5, 0)).toBeNull();
  });
});

describe('the portrait frame buffer', () => {
  it('draws the newest frame at or before what is heard, converting to the phrase rate', () => {
    const released: string[] = [];
    const buffer = new PortraitFrameBuffer<string>((image) => released.push(image));
    buffer.setSourceRate('seg', 24_000);
    for (let index = 0; index < 4; index += 1) buffer.add(header('seg', index * 960), `f${index}`);
    // 0.09 s heard = 4320 context samples at 48 kHz = 2160 source samples: frame 2 (offset 1920).
    expect(buffer.frameAt({ segmentId: 'seg', playedSamples: 4320 }, CONTEXT_RATE)).toBe('f2');
    expect(released).toEqual(['f0', 'f1']);
    expect(buffer.frameAt({ segmentId: 'other', playedSamples: 0 }, CONTEXT_RATE)).toBeNull();
  });

  it('keeps frames in offset order whatever order they arrive in', () => {
    const buffer = new PortraitFrameBuffer<string>();
    buffer.add(header('seg', 1920), 'f2');
    buffer.add(header('seg', 0), 'f0');
    buffer.add(header('seg', 960), 'f1');
    expect(buffer.frameAt({ segmentId: 'seg', playedSamples: 2000 }, CONTEXT_RATE)).toBe('f1');
  });

  it('drops a cancelled turn, including frames that arrive after the cancel', () => {
    const released: string[] = [];
    const buffer = new PortraitFrameBuffer<string>((image) => released.push(image));
    buffer.add(header('seg', 0, 4), 'old');
    buffer.add(header('seg-next', 0, 5), 'new');
    buffer.cancelEpoch(4);
    expect(buffer.add(header('seg', 960, 4), 'late')).toBe(false);
    expect(released).toEqual(['old', 'late']);
    expect(buffer.frameCount).toBe(1);
  });
});
