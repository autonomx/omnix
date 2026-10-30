import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { loadWorkletProcessor } from '../../../test/audioWorklet';
import { liveVoiceAvatarMouthFrameForRms } from './live-voice-pcm-worklet';

type WorkletMessage = Record<string, unknown> & { type?: string };
type WorkletPort = {
  onmessage: ((event: MessageEvent<WorkletMessage>) => void) | null;
  postMessage: ReturnType<typeof vi.fn>;
};
type ProcessorInstance = {
  port: WorkletPort;
  process: (inputs: unknown[], outputs: Float32Array[][]) => boolean;
};
type ProcessorConstructor = new (options: { processorOptions?: Record<string, number> }) => ProcessorInstance;

class FakeAudioWorkletProcessor {
  readonly port: WorkletPort = {
    onmessage: null,
    postMessage: vi.fn(),
  };
}

let Processor: ProcessorConstructor;

beforeEach(async () => {
  Processor = await loadWorkletProcessor<ProcessorConstructor>(
    () => import('./worklets/live-voice-pcm-stream.worklet'),
    FakeAudioWorkletProcessor,
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function createProcessor(overrides: Record<string, number> = {}): ProcessorInstance {
  return new Processor({
    processorOptions: {
      startBufferSamples: 4,
      minimumBufferedSpeechSamples: 4,
      notBeforeRenderSample: 0,
      rebufferSamples: 8,
      maxRebufferSamples: 16,
      transitionFadeSamples: 1,
      ...overrides,
    },
  });
}

function send(processor: ProcessorInstance, data: WorkletMessage): void {
  processor.port.onmessage?.({ data } as MessageEvent<WorkletMessage>);
}

function render(processor: ProcessorInstance, frames = 128): Float32Array {
  const output = new Float32Array(frames);
  processor.process([], [[output]]);
  return output;
}

function events(processor: ProcessorInstance, type?: string): WorkletMessage[] {
  const emitted = processor.port.postMessage.mock.calls.map(([message]) => message as WorkletMessage);
  return type ? emitted.filter((message) => message.type === type) : emitted;
}

describe('live voice PCM worklet state machine', () => {
  it('maps playback RMS to the same stable avatar mouth states as the character bridge', () => {
    expect(liveVoiceAvatarMouthFrameForRms(0)).toBe('closed');
    expect(liveVoiceAvatarMouthFrameForRms(0.02)).toBe('small');
    expect(liveVoiceAvatarMouthFrameForRms(0.05)).toBe('medium');
    expect(liveVoiceAvatarMouthFrameForRms(0.2)).toBe('wide');
  });

  it('does not let cue or intentional silence independently satisfy onset readiness', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'cue-0',
      segmentKind: 'cue',
      samples: new Float32Array([0.1, 0.1, 0.1, 0.1]),
    });
    send(processor, { type: 'segment_end', segmentId: 'cue-0' });
    send(processor, {
      type: 'push_segment_silence',
      segmentId: 'silence-0',
      durationSamples: 4,
      minimumFollowingSpeechSamples: 0,
      reason: 'clause',
    });

    render(processor);
    expect(events(processor, 'started')).toHaveLength(0);
    expect(events(processor, 'segment_started')).toHaveLength(0);

    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array([0.2, 0.2, 0.2, 0.2]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-0' });
    render(processor);

    expect(events(processor, 'started')).toHaveLength(1);
    expect(events(processor, 'segment_started').map((event) => event.segment_kind)).toEqual([
      'cue',
      'silence',
      'speech',
    ]);
  });

  it('drives avatar mouth frames from rendered speech and keeps cues silent', () => {
    const processor = createProcessor({ avatarEnvelopeIntervalSamples: 128 });
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'cue-0',
      segmentKind: 'cue',
      samples: new Float32Array(128).fill(0.4),
    });
    send(processor, { type: 'segment_end', segmentId: 'cue-0' });
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array(128).fill(0.2),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-0' });

    render(processor);
    expect(events(processor, 'avatar_frame')).toHaveLength(0);

    render(processor);
    expect(events(processor, 'avatar_frame')).toEqual([
      expect.objectContaining({ type: 'avatar_frame', frame: 'wide' }),
    ]);

    render(processor);
    expect(events(processor, 'avatar_frame')).toEqual([
      expect.objectContaining({ type: 'avatar_frame', frame: 'wide' }),
      expect.objectContaining({ type: 'avatar_frame', frame: 'closed' }),
    ]);
  });

  it('reports the active segment every 20 ms while the portrait clock is on', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array(2_048).fill(0.2),
    });
    render(processor);
    expect(events(processor, 'portrait_clock')).toHaveLength(0);

    send(processor, { type: 'set_portrait_clock', enabled: true });
    // 20 ms at 24 kHz is 480 samples: the fourth 128-sample quantum crosses it.
    for (let quantum = 0; quantum < 4; quantum += 1) render(processor);
    expect(events(processor, 'portrait_clock')).toEqual([
      expect.objectContaining({
        segment_id: 'speech-0',
        segment_played_samples: 640,
        sample_rate: 24_000,
        // The fifth quantum's end: 640 samples of render clock.
        audio_context_time_seconds: 640 / 24_000,
      }),
    ]);

    send(processor, { type: 'set_portrait_clock', enabled: false });
    for (let quantum = 0; quantum < 4; quantum += 1) render(processor);
    expect(events(processor, 'portrait_clock')).toHaveLength(1);

    // A browser's `currentTime` is the quantum's start: the count holds one quantum later.
    vi.stubGlobal('currentTime', 2);
    send(processor, { type: 'set_portrait_clock', enabled: true });
    for (let quantum = 0; quantum < 4; quantum += 1) render(processor);
    expect(events(processor, 'portrait_clock').at(-1)?.audio_context_time_seconds).toBeCloseTo(2 + 128 / 24_000, 9);
  });

  it('holds a turn start for its first portrait frames, at most the cap, and never mid-reply', () => {
    const processor = createProcessor();
    send(processor, { type: 'set_portrait_clock', enabled: true, startHoldSamples: 512 });
    const speech = (segmentId: string, generationEpoch: number) => {
      send(processor, {
        type: 'push_segment_samples', segmentId, segmentKind: 'speech', phraseIndex: 0, outputId: segmentId,
        generationEpoch, samples: new Float32Array(256).fill(0.2),
      });
      send(processor, { type: 'segment_end', segmentId });
    };
    speech('speech-0', 1);
    render(processor);
    render(processor);
    expect(events(processor, 'started')).toHaveLength(0);
    send(processor, { type: 'portrait_frames_ready', segmentId: 'speech-0' });
    expect(events(processor, 'started')).toHaveLength(1);
    expect(events(processor, 'start_hold')).toEqual([
      expect.objectContaining({ segment_id: 'speech-0', held_samples: 256, released_by: 'frames' }),
    ]);

    // Drained and idle, the same turn's next phrase starts at once: no hold mid-reply.
    for (let quantum = 0; quantum < 4; quantum += 1) render(processor);
    speech('speech-1', 1);
    expect(events(processor, 'started')).toHaveLength(2);

    // A new turn without frames waits only up to the cap.
    for (let quantum = 0; quantum < 4; quantum += 1) render(processor);
    speech('speech-2', 2);
    for (let quantum = 0; quantum < 5; quantum += 1) render(processor);
    expect(events(processor, 'start_hold').at(-1)).toEqual(
      expect.objectContaining({ segment_id: 'speech-2', held_samples: 512, released_by: 'cap' }));
    expect(events(processor, 'started')).toHaveLength(3);
  });

  it('waits before a planned pause until following canonical speech is buffered', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array([0.2, 0.2, 0.2, 0.2]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-0' });
    send(processor, {
      type: 'push_segment_silence',
      segmentId: 'silence-0',
      durationSamples: 4,
      minimumFollowingSpeechSamples: 4,
      reason: 'reflection',
    });

    render(processor);
    expect(events(processor, 'pause_waiting_for_following_speech')).toHaveLength(1);
    expect(events(processor, 'segment_started').map((event) => event.segment_id)).toEqual(['speech-0']);
    expect(events(processor, 'underrun')).toHaveLength(0);

    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-1',
      segmentKind: 'speech',
      phraseIndex: 1,
      samples: new Float32Array([0.3, 0.3, 0.3, 0.3]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-1' });
    render(processor);

    expect(events(processor, 'pause_following_speech_ready')).toHaveLength(1);
    expect(events(processor, 'segment_started').map((event) => event.segment_id)).toEqual([
      'speech-0',
      'silence-0',
      'speech-1',
    ]);
    const final = events(processor).at(-1);
    expect(final).toMatchObject({
      segment_timeline_samples: 12,
      semantic_speech_samples: 8,
    });
  });

  it('counts cues on the segment timeline without revealing canonical speech', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'cue-0',
      segmentKind: 'cue',
      samples: new Float32Array([0.1, 0.1, 0.1, 0.1]),
    });
    send(processor, { type: 'segment_end', segmentId: 'cue-0' });
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array([0.2, 0.2, 0.2, 0.2]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-0' });

    render(processor);

    const cueCompleted = events(processor, 'segment_completed').find(
      (event) => event.segment_id === 'cue-0',
    );
    expect(cueCompleted).toMatchObject({
      segment_kind: 'cue',
      segment_timeline_samples: 4,
      semantic_speech_samples: 0,
    });
    const speechCompleted = events(processor, 'segment_completed').find(
      (event) => event.segment_id === 'speech-0',
    );
    expect(speechCompleted).toMatchObject({
      segment_kind: 'speech',
      segment_timeline_samples: 8,
      semantic_speech_samples: 4,
    });
  });

  it('interrupts the active segment and cancels every distinct queued segment exactly once', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array(256).fill(0.2),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-0' });
    send(processor, {
      type: 'push_segment_silence',
      segmentId: 'silence-0',
      durationSamples: 4,
      minimumFollowingSpeechSamples: 4,
      reason: 'thought',
    });
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-1',
      segmentKind: 'speech',
      phraseIndex: 1,
      samples: new Float32Array([0.3, 0.3, 0.3, 0.3]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-1' });

    render(processor);
    send(processor, { type: 'stop', reason: 'barge_in' });
    send(processor, { type: 'stop', reason: 'barge_in' });

    expect(events(processor, 'segment_interrupted')).toEqual([
      expect.objectContaining({
        segment_id: 'speech-0',
        segment_kind: 'speech',
        phrase_index: 0,
        reason: 'barge_in',
      }),
    ]);
    expect(events(processor, 'segment_cancelled')).toEqual([
      expect.objectContaining({ segment_id: 'silence-0', segment_kind: 'silence', reason: 'barge_in' }),
      expect.objectContaining({ segment_id: 'speech-1', segment_kind: 'speech', reason: 'barge_in' }),
    ]);
    expect(events(processor, 'segment_completed')).toHaveLength(0);
  });

  it('selectively cancels one output, preserves following output, and rejects late frames', () => {
    const processor = createProcessor({ transitionFadeSamples: 4 });
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-a',
      segmentKind: 'speech',
      phraseIndex: 0,
      outputId: 'output-a',
      generationEpoch: 1,
      outputOrder: 0,
      samples: new Float32Array(256).fill(0.4),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-a' });
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-b',
      segmentKind: 'speech',
      phraseIndex: 1,
      outputId: 'output-b',
      generationEpoch: 1,
      outputOrder: 1,
      samples: new Float32Array([0.2, 0.2, 0.2, 0.2]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-b' });

    render(processor);
    send(processor, {
      type: 'cancel_output',
      outputId: 'output-a',
      generationEpoch: 1,
      reason: 'self_corrected',
    });
    const afterCancel = render(processor, 16);

    expect(events(processor, 'segment_interrupted')).toContainEqual(expect.objectContaining({
      segment_id: 'speech-a', output_id: 'output-a', generation_epoch: 1, reason: 'self_corrected',
    }));
    expect(events(processor, 'segment_completed')).toContainEqual(expect.objectContaining({
      segment_id: 'speech-b', output_id: 'output-b', generation_epoch: 1,
    }));
    expect(afterCancel.slice(0, 4).some((sample) => sample !== 0)).toBe(true);

    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-a-late',
      segmentKind: 'speech',
      outputId: 'output-a',
      generationEpoch: 1,
      outputOrder: 0,
      samples: new Float32Array([0.9, 0.9]),
    });
    expect(events(processor, 'late_segment_rejected')).toContainEqual(expect.objectContaining({
      output_id: 'output-a', generation_epoch: 1,
    }));
  });

  it('treats a completed persistent-session turn as idle instead of an underrun', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-0',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array([0.2, 0.2, 0.2, 0.2]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-0' });
    render(processor);

    expect(events(processor, 'started')).toHaveLength(1);
    expect(events(processor, 'idle')).toHaveLength(1);
    expect(events(processor, 'underrun')).toHaveLength(0);

    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-1',
      segmentKind: 'speech',
      phraseIndex: 1,
      samples: new Float32Array([0.3, 0.3]),
    });
    render(processor);
    expect(events(processor, 'started')).toHaveLength(1);

    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-1',
      segmentKind: 'speech',
      phraseIndex: 1,
      samples: new Float32Array([0.3, 0.3]),
    });
    send(processor, { type: 'segment_end', segmentId: 'speech-1' });
    render(processor);

    expect(events(processor, 'started')).toHaveLength(2);
    expect(events(processor, 'idle')).toHaveLength(2);
    expect(events(processor, 'underrun')).toHaveLength(0);
  });

  it('still counts starvation before an active segment ends as an underrun', () => {
    const processor = createProcessor();
    send(processor, {
      type: 'push_segment_samples',
      segmentId: 'speech-starved',
      segmentKind: 'speech',
      phraseIndex: 0,
      samples: new Float32Array([0.2, 0.2, 0.2, 0.2]),
    });
    render(processor);

    expect(events(processor, 'idle')).toHaveLength(0);
    expect(events(processor, 'underrun')).toEqual([
      expect.objectContaining({
        buffered_samples: 0,
        buffered_speech_samples: 0,
        underrun_count: 1,
      }),
    ]);
  });

});
