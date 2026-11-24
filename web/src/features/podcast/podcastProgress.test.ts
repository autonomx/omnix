import { describe, expect, it } from 'vitest';
import { activeStageIndex, jobSteps, runPercent } from './podcastProgress';

describe('podcast run progress', () => {
  it('fills the bar across the script, the preview and the final render', () => {
    expect(runPercent({ stage: 'script', done: 0, total: 1 })).toBe(0);
    expect(runPercent({ stage: 'script', done: 4, total: 8 })).toBe(5);
    expect(runPercent({ stage: 'preview', done: 0, total: 40 })).toBe(10);
    expect(runPercent({ stage: 'preview', done: 20, total: 40 })).toBe(33);
    expect(runPercent({ stage: 'final', done: 0, total: 41 })).toBe(55);
    expect(runPercent({ stage: 'final', done: 41, total: 41 })).toBe(100);
  });

  it('never leaves its stage for odd counts', () => {
    expect(runPercent({ stage: 'preview', done: 50, total: 40 })).toBe(55);
    expect(runPercent({ stage: 'final', done: -1, total: 3 })).toBe(55);
    expect(runPercent({ stage: 'final', done: 2, total: 0 })).toBe(55);
  });

  it('gives the preview most of the bar when the final render reuses its takes', () => {
    expect(runPercent({ stage: 'preview', done: 20, total: 40, reuse: true })).toBe(50);
    expect(runPercent({ stage: 'final', done: 0, total: 1, reuse: true })).toBe(90);
    expect(runPercent({ stage: 'final', done: 1, total: 1, reuse: true })).toBe(100);
  });

  it('reads a job\'s reported steps, and none before it reports', () => {
    expect(jobSteps({ current: 3, total: 7 })).toEqual({ done: 3, total: 7 });
    expect(jobSteps(null)).toEqual({ done: 0, total: 1 });
    expect(jobSteps({ current: 0, total: 0 })).toEqual({ done: 0, total: 1 });
  });

  it('lights the stage rail step the run is on', () => {
    expect(activeStageIndex('script')).toBe(1);
    expect(activeStageIndex('preview')).toBe(2);
    expect(activeStageIndex('final')).toBe(3);
    expect(activeStageIndex(undefined)).toBe(2);
  });
});
