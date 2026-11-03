/**
 * What the mic heard while no turn was open. Audio below the speech threshold never reaches the recognizer, so
 * without this a question that was too quiet and a mic that hears nothing leave the same empty trace.
 */
export const MIC_LEVEL_WINDOW_MS = 2_000;

export type MicLevelReport = {
  frames: number;
  peak_rms: number;
  frames_over_threshold: number;
  longest_over_threshold_run: number;
  threshold: number;
};

export function createMicLevelWindow(startedAt: number) {
  let windowStartedAt = startedAt;
  let frames = 0;
  let peak = 0;
  let over = 0;
  let run = 0;
  let longestRun = 0;
  return {
    /** Takes one frame's level; returns the finished window when this frame ends one. */
    observe(rms: number, threshold: number, now: number): MicLevelReport | null {
      frames += 1;
      peak = Math.max(peak, rms);
      run = rms >= threshold ? run + 1 : 0;
      if (run > 0) over += 1;
      longestRun = Math.max(longestRun, run);
      if (now - windowStartedAt < MIC_LEVEL_WINDOW_MS) return null;
      const report = { frames, peak_rms: peak, frames_over_threshold: over, longest_over_threshold_run: longestRun, threshold };
      windowStartedAt = now;
      frames = 0;
      peak = 0;
      over = 0;
      run = 0;
      longestRun = 0;
      return report;
    },
  };
}
