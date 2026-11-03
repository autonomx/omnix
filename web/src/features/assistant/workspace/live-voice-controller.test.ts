/* eslint-disable no-restricted-syntax -- baseline WP-9.x */
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  dispatchAssistantTurnSummary,
  resetAssistantDiagnosticSummaries,
} from './live-conversation-assistant-summary';
import { liveConversationStore } from './live-conversation-store';
import {
  noteLiveSttNegotiation,
  resetLiveSttCapabilityState,
} from './live-stt-capability-state';
import {
  initializeLiveVoiceController,
  LiveSttSegmentTelemetryGate,
  liveVoiceAssistantOwnsFloor,
  liveVoiceSpeechThreshold,
  semanticFinalizationRemainingMs,
  waitForLiveConversationSessionId,
} from './live-voice-controller';
import { controller, type LiveVoiceSession } from './live-voice-controller-state';

const SETTINGS_KEY = 'omnix.chatbot.assistantSettings';

afterEach(() => {
  window.localStorage.clear();
  document.body.innerHTML = '';
  liveConversationStore.reset();
  resetAssistantDiagnosticSummaries();
  resetLiveSttCapabilityState();
});

describe('live voice controller sensitivity', () => {
  it('maps lower sensitivity to a stricter speech threshold', () => {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify({ liveVoiceSensitivity: 25 }));
    const lowSensitivityThreshold = liveVoiceSpeechThreshold();

    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify({ liveVoiceSensitivity: 85 }));
    const highSensitivityThreshold = liveVoiceSpeechThreshold();

    expect(lowSensitivityThreshold).toBeGreaterThan(highSensitivityThreshold);
    expect(lowSensitivityThreshold).toBeGreaterThan(0.03);
    expect(highSensitivityThreshold).toBeLessThan(0.03);
  });
});

describe('live voice semantic finalization deadline', () => {
  it('keeps an insufficient-text timer conservative from the original pause boundary', () => {
    expect(semanticFinalizationRemainingMs('', 'balanced', 120)).toBe(1_580);
    expect(semanticFinalizationRemainingMs('Where are we?', 'balanced', 120)).toBe(100);
    expect(semanticFinalizationRemainingMs('Where are we?', 'balanced', 260)).toBe(0);
  });

  it('uses the final-only acoustic deadline after Parakeet negotiation', () => {
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'parakeet',
        capabilities: ['segmented_audio', 'authoritative_final', 'result_replay'],
      },
    }));

    expect(semanticFinalizationRemainingMs('', 'balanced', 120)).toBe(230);
    expect(semanticFinalizationRemainingMs('', 'balanced', 349)).toBe(1);
    expect(semanticFinalizationRemainingMs('', 'balanced', 350)).toBe(0);
  });

  it('clears the final-only deadline before a new provider negotiates', () => {
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'parakeet',
        capabilities: ['segmented_audio', 'authoritative_final', 'result_replay'],
      },
    }));
    expect(semanticFinalizationRemainingMs('', 'balanced', 120)).toBe(230);

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_authority_selected',
        selectedProvider: 'configured_stt',
      },
    }));
    expect(semanticFinalizationRemainingMs('', 'balanced', 120)).toBe(1_580);

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'streaming-test-provider',
        capabilities: [
          'segmented_audio',
          'authoritative_final',
          'continuous_words',
          'semantic_endpointing',
          'delayed_flush',
        ],
      },
    }));
    expect(semanticFinalizationRemainingMs('', 'balanced', 120)).toBe(1_580);
  });

  it('can lengthen the remaining wait again when the transcript becomes incomplete', () => {
    expect(semanticFinalizationRemainingMs('Where are we?', 'balanced', 150)).toBe(70);
    expect(semanticFinalizationRemainingMs('Where are we going to', 'balanced', 150)).toBe(850);
  });

  it('does not let an old pause prepay the completion window for newly arrived words', () => {
    expect(semanticFinalizationRemainingMs('You should lie', 'balanced', 900, 21)).toBe(339);
    expect(semanticFinalizationRemainingMs('You should lie', 'balanced', 900, 359)).toBe(1);
    expect(semanticFinalizationRemainingMs('You should lie', 'balanced', 900, 360)).toBe(0);
    expect(semanticFinalizationRemainingMs('Where are we?', 'balanced', 500, 40)).toBe(180);
  });

  it('does not let late Nemotron partials restart the authoritative EOU watchdog', () => {
    noteLiveSttNegotiation('nemotron_parakeet_eou', [
      'segmented_audio',
      'authoritative_final',
      'result_replay',
      'partial_transcripts',
      'authoritative_eou',
    ]);

    expect(semanticFinalizationRemainingMs('That should still be one turn', 'balanced', 494, 0)).toBe(6);
    expect(semanticFinalizationRemainingMs('That should still be one turn', 'balanced', 499, 0)).toBe(1);
    expect(semanticFinalizationRemainingMs('That should still be one turn', 'balanced', 500, 0)).toBe(0);
  });

  it('uses recent assistant-question context to finalize a one-word answer quickly', () => {
    dispatchAssistantTurnSummary({
      turnId: 'assistant-question',
      turnKind: 'response',
      wordCount: 5,
      questionCount: 1,
      topicFingerprint: null,
      createsObligation: true,
    });

    expect(semanticFinalizationRemainingMs('Vancouver', 'balanced', 120)).toBe(100);
    expect(semanticFinalizationRemainingMs('yes', 'balanced', 120)).toBe(100);
    expect(semanticFinalizationRemainingMs('because', 'balanced', 120)).toBe(1_580);
  });
});

describe('live STT segment telemetry', () => {
  it('reports structural changes immediately and throttles unchanged audio progress', () => {
    const gate = new LiveSttSegmentTelemetryGate();
    const state = {
      protocol: 'segmented-v1' as const,
      sessionId: 'stt-session:test',
      captureEpoch: 'capture:test',
      activeSequence: 2,
      pendingSegments: 1,
      queuedSegments: 0,
      absoluteSample: 16_000,
      negotiation: null,
    };

    expect(gate.shouldReport(state, 1_000)).toBe(true);
    expect(gate.shouldReport({ ...state, absoluteSample: 16_320 }, 1_020)).toBe(false);
    expect(gate.shouldReport({ ...state, absoluteSample: 20_000 }, 1_250)).toBe(true);
    expect(gate.shouldReport({ ...state, pendingSegments: 2 }, 1_260)).toBe(true);
  });
});

describe('live voice session selection', () => {
  it('waits for the React-selected session during call startup', async () => {
    const selected = waitForLiveConversationSessionId(100);

    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:just-created' });

    await expect(selected).resolves.toBe('chat:just-created');
  });
});

describe('a call and the selected chat', () => {
  function runningCall(chatSessionId: string) {
    const session = {
      card: document.createElement('section'),
      chatSessionId,
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

  it('ends the call when another chat is selected, so it cannot refuse every sentence', () => {
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:call' });
    const dispose = initializeLiveVoiceController();
    const session = runningCall('chat:call');
    const stopped = vi.fn();
    window.addEventListener('omnix:assistant-live-voice-stop', stopped);

    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:other' });

    expect(stopped).toHaveBeenCalledOnce();
    expect(controller.activeSession).toBeNull();
    expect(session.client.disconnect).toHaveBeenCalled();
    expect(session.reporter.record).toHaveBeenCalledWith('live_call_chat_changed', { call_session_id: 'chat:call', selected_session_id: 'chat:other' }, 'live_voice_controller');
    window.removeEventListener('omnix:assistant-live-voice-stop', stopped);
    dispose();
  });

  it('keeps the call through anything else that changes in the store', () => {
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:call' });
    const dispose = initializeLiveVoiceController();
    const session = runningCall('chat:call');

    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });

    expect(controller.activeSession).toBe(session);
    controller.activeSession = null;
    dispose();
  });
});

describe('live voice floor ownership', () => {
  it('gives immediate user speech priority when the authoritative floor is unclaimed', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-output-kind="response">
        <div class="assistant-voice-orb" data-voice-mode="speaking"></div>
      </section>`;
    liveConversationStore.dispatch({
      type: 'conversation',
      event: { type: 'assistant_turn', value: 'speaking' },
    });
    liveConversationStore.dispatch({
      type: 'conversation',
      event: { type: 'floor_owner', value: 'unclaimed' },
    });

    expect(liveVoiceAssistantOwnsFloor()).toBe(false);
  });

  it('keeps overlap classification for an authoritative assistant-owned response', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-output-kind="greeting">
        <div class="assistant-voice-orb" data-voice-mode="listening"></div>
      </section>`;
    liveConversationStore.dispatch({
      type: 'conversation',
      event: { type: 'assistant_turn', value: 'speaking' },
    });
    liveConversationStore.dispatch({
      type: 'conversation',
      event: { type: 'floor_owner', value: 'assistant' },
    });

    expect(liveVoiceAssistantOwnsFloor()).toBe(true);
  });
});
