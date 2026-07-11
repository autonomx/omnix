import { describe, expect, it } from 'vitest';

import { assessAcousticBargeIn, calculatePcm16Rms } from './live-voice-barge-in-detector';

describe('acoustic barge-in detector', () => {
  it('calculates normalized PCM reference energy', () => {
    expect(calculatePcm16Rms(new Int16Array([32767, -32768]))).toBeGreaterThan(0.99);
    expect(calculatePcm16Rms(new Int16Array())).toBe(0);
  });

  it('does not classify speech when assistant playback is inactive', () => {
    expect(assessAcousticBargeIn({
      assistantSpeaking: false,
      microphoneRms: 0.08,
      playbackRms: 0,
      playbackReferenceAgeMs: 0,
      speechThreshold: 0.02,
    }).decision).toBe('no_playback');
  });

  it('treats low microphone energy relative to recent playback as likely echo', () => {
    const result = assessAcousticBargeIn({
      assistantSpeaking: true,
      microphoneRms: 0.024,
      playbackRms: 0.08,
      playbackReferenceAgeMs: 120,
      speechThreshold: 0.018,
    });
    expect(result.decision).toBe('likely_echo');
    expect(result.energyRatio).toBeCloseTo(0.3);
  });

  it('uses strong waveform similarity to reject speaker echo', () => {
    const result = assessAcousticBargeIn({
      assistantSpeaking: true,
      microphoneRms: 0.035,
      playbackRms: 0.07,
      playbackReferenceAgeMs: 80,
      speechThreshold: 0.018,
      waveformSimilarity: 0.93,
      calibratedEchoGain: 0.2,
      interruptionSensitivity: 0.75,
    });

    expect(result.decision).toBe('likely_echo');
    expect(result.reason).toBe('waveform_matches_playback');
    expect(result.waveformSimilarity).toBe(0.93);
  });

  it('uses waveform separation to identify independent speech before STT', () => {
    const result = assessAcousticBargeIn({
      assistantSpeaking: true,
      microphoneRms: 0.045,
      playbackRms: 0.06,
      playbackReferenceAgeMs: 80,
      speechThreshold: 0.018,
      waveformSimilarity: 0.08,
      interruptionSensitivity: 0.8,
    });

    expect(result.decision).toBe('independent_speech');
    expect(result.reason).toBe('waveform_separates_from_playback');
  });

  it('ducks for strong independent speech and defers ambiguous candidates to STT', () => {
    expect(assessAcousticBargeIn({
      assistantSpeaking: true,
      microphoneRms: 0.09,
      playbackRms: 0.06,
      playbackReferenceAgeMs: 80,
      speechThreshold: 0.018,
    }).decision).toBe('independent_speech');

    expect(assessAcousticBargeIn({
      assistantSpeaking: true,
      microphoneRms: 0.04,
      playbackRms: 0.06,
      playbackReferenceAgeMs: 80,
      speechThreshold: 0.018,
    }).decision).toBe('uncertain');
  });
});
