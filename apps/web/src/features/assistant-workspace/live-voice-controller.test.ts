import { afterEach, describe, expect, it } from 'vitest';
import {
  liveVoiceAssistantOwnsFloor,
  liveVoiceSpeechThreshold,
} from './live-voice-controller';

const SETTINGS_KEY = 'omnix.chatbot.assistantSettings';

afterEach(() => {
  window.localStorage.clear();
  document.body.innerHTML = '';
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
  it('gives immediate user speech priority over a startup greeting', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-output-kind="greeting">
        <div class="assistant-voice-orb" data-voice-mode="speaking"></div>
      </section>`;
    const card = document.querySelector<HTMLElement>('.assistant-live-card');
    expect(card).not.toBeNull();
    expect(liveVoiceAssistantOwnsFloor(card!)).toBe(false);
  });

  it('keeps overlap classification for a normal assistant response', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card" data-live-voice-output-kind="response">
        <div class="assistant-voice-orb" data-voice-mode="speaking"></div>
      </section>`;
    const card = document.querySelector<HTMLElement>('.assistant-live-card');
    expect(card).not.toBeNull();
    expect(liveVoiceAssistantOwnsFloor(card!)).toBe(true);
  });
});
