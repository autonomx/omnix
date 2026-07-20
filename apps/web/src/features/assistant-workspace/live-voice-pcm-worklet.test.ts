import { beforeEach, describe, expect, it, vi } from 'vitest';

import { liveVoicePcmWorkletSource } from './live-voice-pcm-worklet';

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

beforeEach(() => {
  let registered: ProcessorConstructor | null = null;
  const registerProcessor = (_name: string, constructor: ProcessorConstructor): void => {
    registered = constructor;
  };
  const evaluate = new Function(
    'AudioWorkletProcessor',
    'registerProcessor',
    'sampleRate',
    liveVoicePcmWorkletSource(),
  );
  evaluate(FakeAudioWorkletProcessor, registerProcessor, 24_000);
  if (!registered) throw new Error('Live voice worklet processor did not register.');
  Processor = registered;
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
});
