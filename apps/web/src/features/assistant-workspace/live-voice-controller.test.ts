import { afterEach, describe, expect, it } from 'vitest';
import { liveVoiceSpeechThreshold } from './live-voice-controller';

const SETTINGS_KEY = 'omnix.chatbot.assistantSettings';

afterEach(() => {
  window.localStorage.clear();
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
