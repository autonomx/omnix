import { describe, expect, it } from 'vitest';

import { type MicLevelReport, MIC_LEVEL_WINDOW_MS, createMicLevelWindow } from './live-voice-mic-level';

function frames(window: ReturnType<typeof createMicLevelWindow>, levels: number[], threshold: number, at: number): MicLevelReport | null {
  levels.slice(0, -1).forEach((rms) => window.observe(rms, threshold, at - 1));
  return window.observe(levels[levels.length - 1], threshold, at);
}

describe('the mic level window of a live call', () => {
  it('reports nothing until the window has passed', () => {
    const window = createMicLevelWindow(0);
    expect(frames(window, [0.01, 0.02], 0.03, MIC_LEVEL_WINDOW_MS - 1)).toBeNull();
  });

  it('tells speech too quiet to open the turn from a mic that hears nothing', () => {
    const quiet = createMicLevelWindow(0);
    expect(frames(quiet, [0.02, 0.025, 0.031, 0.02], 0.03, MIC_LEVEL_WINDOW_MS)).toEqual({
      frames: 4, peak_rms: 0.031, frames_over_threshold: 1, longest_over_threshold_run: 1, threshold: 0.03,
    });

    const dead = createMicLevelWindow(0);
    expect(frames(dead, [0, 0, 0], 0.03, MIC_LEVEL_WINDOW_MS)).toEqual({
      frames: 3, peak_rms: 0, frames_over_threshold: 0, longest_over_threshold_run: 0, threshold: 0.03,
    });
  });

  it('counts the longest run over the threshold and starts afresh after each report', () => {
    const window = createMicLevelWindow(0);
    const report = frames(window, [0.04, 0.05, 0.01, 0.04], 0.03, MIC_LEVEL_WINDOW_MS);
    expect(report?.longest_over_threshold_run).toBe(2);
    expect(report?.frames_over_threshold).toBe(3);

    expect(window.observe(0.01, 0.03, MIC_LEVEL_WINDOW_MS + 1)).toBeNull();
    expect(window.observe(0.01, 0.03, MIC_LEVEL_WINDOW_MS * 2)).toEqual({
      frames: 2, peak_rms: 0.01, frames_over_threshold: 0, longest_over_threshold_run: 0, threshold: 0.03,
    });
  });
});
