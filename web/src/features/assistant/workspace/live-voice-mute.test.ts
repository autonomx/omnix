import { afterEach, describe, expect, it, vi } from 'vitest';

const processAudioFrame = vi.hoisted(() => vi.fn());
vi.mock('./live-voice-finalization', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./live-voice-finalization')>()),
  processAudioFrame,
}));

import { liveCallPresentationStore } from './live-call-presentation-store';
import { deliverCaptureFrame, setLiveVoiceMuted } from './live-voice-controller';
import { controller, type LiveVoiceSession } from './live-voice-controller-state';
import { stopLiveVoice } from './live-voice-session-lifecycle';

function runningCall() {
  const session = {
    card: document.createElement('section'),
    finalizationBuffer: { clear: vi.fn() },
    preSpeechBuffer: { clear: vi.fn() },
    audioPipeline: { cleanup: vi.fn() },
    source: { disconnect: vi.fn() },
    stream: { getTracks: () => [] },
    client: { disconnect: vi.fn(), cancelPreview: vi.fn() },
    audioContext: { close: vi.fn(async () => undefined) },
    reporter: { record: vi.fn(), close: vi.fn(async () => undefined) },
    floorState: 'listening',
  };
  controller.activeSession = session as unknown as LiveVoiceSession;
  return session;
}

afterEach(() => {
  controller.activeSession = null;
  liveCallPresentationStore.resetForTests();
  processAudioFrame.mockClear();
});

describe('muting the call microphone', () => {
  it('hands the call silence while muted and the microphone again once unmuted', () => {
    const session = runningCall();
    const speech = new Float32Array([0.4, -0.3, 0.2]);

    setLiveVoiceMuted(true);
    deliverCaptureFrame(session.card, speech);
    setLiveVoiceMuted(false);
    deliverCaptureFrame(session.card, speech);

    const [muted, unmuted] = processAudioFrame.mock.calls.map(([, audio]) => Array.from(audio as Float32Array));
    expect(muted).toEqual([0, 0, 0]);
    expect(unmuted).toEqual(Array.from(speech));
    expect(session.reporter.record).toHaveBeenCalledWith('live_call_microphone', { muted: true }, 'live_voice_controller');
    expect(session.reporter.record).toHaveBeenCalledWith('live_call_microphone', { muted: false }, 'live_voice_controller');
  });

  it('stops showing the person as heard when they mute', () => {
    runningCall();
    liveCallPresentationStore.update({ hearing: true });

    setLiveVoiceMuted(true);

    expect(liveCallPresentationStore.getState()).toMatchObject({ micMuted: true, hearing: false });
  });

  it('starts the next call unmuted', () => {
    const session = runningCall();
    setLiveVoiceMuted(true);

    stopLiveVoice(session.card, 'idle');

    expect(liveCallPresentationStore.getState().micMuted).toBe(false);
  });
});
