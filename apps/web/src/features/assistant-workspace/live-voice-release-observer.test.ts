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

function perf(stage: string, turnId = 'voice-turn:1', extra = {}): void {
  window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
    detail: { stage, turnId, ...extra },
  }));
}

function diagnostic(
  event: string,
  traceId = 'live-call:voice-turn:1',
  source = 'controller',
): void {
  window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
    detail: { traceId, source, event, details: {} },
  }));
}

describe('live voice release observer', () => {
  let now = 0;

  beforeEach(() => {
    mocks.record.mockReset();
    resetLiveVoiceReleaseObserver();
    window.localStorage.clear();
    vi.spyOn(performance, 'now').mockImplementation(() => now);
  });

  it('separates stream-open, model, PCM, playback, and local-pause latency', () => {
    const observations: LiveVoiceReleaseObservation[] = [];
    const listener = (event: Event) => observations.push(
      (event as CustomEvent<LiveVoiceReleaseObservation>).detail,
    );
    window.addEventListener(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, listener);

    now = 50;
    perf('semantic_turn_assessed');
    now = 100;
    perf('stt_final_requested');
    now = 300;
    perf('stt_final_received', 'voice-turn:1', { sttFinalizeMs: 200 });
    diagnostic('turn_intercepted');
    now = 500;
    diagnostic('chat_response_opened', 'live-call:voice-turn:1', 'chatbot_workspace');
    now = 800;
    diagnostic('llm_text_chunk_received');
    now = 1_000;
    diagnostic(
      'phrase_first_frame_received',
      'live-call:chat:s1:audio-session:a1',
      'pcm_session',
    );
    now = 1_100;
    diagnostic(
      'worklet_segment_started',
      'live-call:chat:s1:audio-session:a1',
      'audio_worklet',
    );

    const latency = observations.filter(
      (item): item is Extract<LiveVoiceReleaseObservation, { kind: 'latency' }> => (
        item.kind === 'latency'
      ),
    );
    const values = Object.fromEntries(
      latency.map((item) => [item.metricName, item.valueMs]),
    );
    expect(values).toMatchObject({
      stt_finalize_ms: 200,
      final_to_response_open_ms: 200,
      response_open_to_first_token_ms: 300,
      final_to_first_token_ms: 500,
      first_token_to_first_audio_ms: 200,
      final_to_first_audio_ms: 700,
      first_pcm_to_first_playback_ms: 100,
      first_token_to_first_playback_ms: 300,
      final_to_first_playback_ms: 800,
      local_pause_to_first_playback_ms: 1_050,
    });
    window.removeEventListener(LIVE_VOICE_RELEASE_OBSERVATION_EVENT, listener);
  });

  it('rejects unrelated cross-trace playback diagnostics', () => {
    now = 100;
    perf('stt_final_received', 'voice-turn:2', { sttFinalizeMs: 100 });
    diagnostic('turn_intercepted', 'live-call:voice-turn:2');
    now = 200;
    diagnostic('llm_text_chunk_received', 'live-call:voice-turn:2');
    now = 300;
    diagnostic('worklet_segment_started', 'live-call:unrelated', 'controller');

    expect(mocks.record).not.toHaveBeenCalledWith(
      'release_metric',
      expect.objectContaining({ metric_name: 'final_to_first_playback_ms' }),
      'release_observer',
    );
  });

  it('records manually labelled quality trials', () => {
    recordLiveVoiceReleaseQuality('false_interruption', false, 'system-noise');
    expect(mocks.record).toHaveBeenCalledWith('release_quality', {
      quality_name: 'false_interruption',
      occurred: false,
      scenario: 'system-noise',
    }, 'release_observer');
  });
});