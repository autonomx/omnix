import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  record: vi.fn(),
  flush: vi.fn(async () => undefined),
  close: vi.fn(async () => undefined),
}));

vi.mock('./live-call-diagnostics-client', () => ({
  createLiveCallDiagnosticsReporter: () => ({
    traceId: 'live-call:release-observer',
    record: mocks.record,
    flush: mocks.flush,
    close: mocks.close,
  }),
}));

import {
  LIVE_VOICE_RELEASE_OBSERVATION_EVENT,
  recordLiveVoiceReleaseQuality,
  resetLiveVoiceReleaseObserver,
  type LiveVoiceReleaseObservation,
} from './live-voice-release-observer';

describe('live voice release observer', () => {
  let now = 0;

  beforeEach(() => {
    mocks.record.mockReset();
    resetLiveVoiceReleaseObserver();
    window.localStorage.clear();
    vi.spyOn(performance, 'now').mockImplementation(() => now);
  });

  it('correlates STT, model, audio, and interruption latency without transcript content', () => {
    const observations: LiveVoiceReleaseObservation[] = [];
    const listener = (event: Event) => observations.push((event as CustomEvent<LiveVoiceReleaseObservation>).detail);
    window.addEventListener(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, listener);
    window.localStorage.setItem('omnix.liveCall.releaseScenario', 'character-normal');
    now = 100;
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: { stage: 'stt_final_requested', turnId: 'voice-turn:1' },
    }));
    now = 300;
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: { stage: 'stt_final_received', turnId: 'voice-turn:1', sttFinalizeMs: 200 },
    }));
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { traceId: 'live-call:s1:1', event: 'turn_intercepted', details: {} },
    }));
    now = 800;
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { traceId: 'live-call:s1:1', event: 'llm_text_chunk_received', details: { text_length: 5 } },
    }));
    now = 1_100;
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { traceId: 'live-call:s1:1', event: 'phrase_first_frame_received', details: {} },
    }));
    now = 1_200;
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-interrupt'));
    now = 1_450;
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { traceId: 'live-call:s1:1', event: 'turn_stopped', details: {} },
    }));

    expect(mocks.record).toHaveBeenCalledWith('release_metric', expect.objectContaining({
      metric_name: 'stt_finalize_ms', value_ms: 200, scenario: 'character-normal',
    }), 'release_observer');
    expect(mocks.record).toHaveBeenCalledWith('release_metric', expect.objectContaining({
      metric_name: 'final_to_first_token_ms', value_ms: 500,
    }), 'release_observer');
    expect(mocks.record).toHaveBeenCalledWith('release_metric', expect.objectContaining({
      metric_name: 'first_token_to_first_audio_ms', value_ms: 300,
    }), 'release_observer');
    expect(mocks.record).toHaveBeenCalledWith('release_metric', expect.objectContaining({
      metric_name: 'interruption_to_silence_ms', value_ms: 250,
    }), 'release_observer');
    expect(observations.map((observation) => observation.kind === 'latency' ? observation.metricName : observation.qualityName))
      .toEqual([
        'stt_finalize_ms',
        'final_to_first_token_ms',
        'first_token_to_first_audio_ms',
        'interruption_to_silence_ms',
      ]);
    window.removeEventListener(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, listener);
  });

  it('records manually labelled quality trials for durable aggregation', () => {
    const observations: LiveVoiceReleaseObservation[] = [];
    const listener = (event: Event) => observations.push((event as CustomEvent<LiveVoiceReleaseObservation>).detail);
    window.addEventListener(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, listener);
    recordLiveVoiceReleaseQuality('false_interruption', false, 'system-noise');
    recordLiveVoiceReleaseQuality('playback_echo_submission', false, 'pure-assistant-echo');

    expect(mocks.record).toHaveBeenCalledWith('release_quality', {
      quality_name: 'false_interruption',
      occurred: false,
      scenario: 'system-noise',
    }, 'release_observer');
    expect(observations).toEqual(expect.arrayContaining([
      { kind: 'quality', qualityName: 'false_interruption', occurred: false, scenario: 'system-noise' },
      { kind: 'quality', qualityName: 'playback_echo_submission', occurred: false, scenario: 'pure-assistant-echo' },
    ]));
    window.removeEventListener(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, listener);
  });
});
