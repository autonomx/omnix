import { afterEach, describe, expect, it } from 'vitest';

import { liveConversationStore } from './live-conversation-store';
import {
  liveVoiceAssistantOwnsFloor,
  liveVoiceSpeechThreshold,
} from './live-voice-controller';

const SETTINGS_KEY = 'omnix.chatbot.assistantSettings';

afterEach(() => {
  window.localStorage.clear();
  document.body.innerHTML = '';
  liveConversationStore.reset();
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
