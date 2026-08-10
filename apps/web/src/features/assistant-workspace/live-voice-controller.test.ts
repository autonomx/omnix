import { afterEach, describe, expect, it } from 'vitest';

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
  liveVoiceAssistantOwnsFloor,
  liveVoiceSpeechThreshold,
  semanticFinalizationRemainingMs,
} from './live-voice-controller';

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
        selectedProvider: 'kyutai',
      },
    }));
    expect(semanticFinalizationRemainingMs('', 'balanced', 120)).toBe(1_580);

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: {
        stage: 'stt_negotiated',
        provider: 'kyutai',
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

    expect(semanticFinalizationRemainingMs('That should still be one turn', 'balanced', 514, 0)).toBe(86);
    expect(semanticFinalizationRemainingMs('That should still be one turn', 'balanced', 599, 0)).toBe(1);
    expect(semanticFinalizationRemainingMs('That should still be one turn', 'balanced', 600, 0)).toBe(0);
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
