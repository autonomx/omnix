import { beforeEach, describe, expect, it } from 'vitest';
import {
  expectedStepMs, finishLoad, loadFraction, moveTo, planLoad, recordStepMs, secondsLeft, stepId, stepLabel,
} from './loadProgress';

const steps = [
  { id: stepId('model'), kind: 'model' as const, name: '' },
  { id: stepId('face'), kind: 'face' as const, name: 'Jinx' },
  { id: stepId('guest', 'abhishek'), kind: 'guest' as const, name: 'Abhishek' },
];

describe('the live video load progress', () => {
  beforeEach(() => window.localStorage.clear());

  it('fills each step evenly to 90% of its share at its expected time, then creeps without reaching the end', () => {
    const plan = planLoad(steps, 0); // 12 s + 5 s + 5 s expected
    expect(loadFraction(plan, 0)).toBe(0);
    expect(loadFraction(plan, 6_000)).toBeCloseTo((12_000 * 0.45) / 22_000);
    expect(loadFraction(plan, 12_000)).toBeCloseTo((12_000 * 0.9) / 22_000);
    const late = loadFraction(plan, 60_000);
    expect(late).toBeGreaterThan(loadFraction(plan, 12_000));
    expect(late).toBeLessThan(12_000 / 22_000); // a slow model never runs into the face's share
    const atFace = moveTo(plan, stepId('face'), 10_000);
    expect(loadFraction(atFace, 10_000)).toBeCloseTo(12_000 / 22_000);
    const atGuest = moveTo(atFace, stepId('guest', 'abhishek'), 14_000);
    expect(loadFraction(atGuest, 1_000_000)).toBeLessThanOrEqual(0.99);
  });

  it('says about how long is left, and "almost there" once past it', () => {
    const plan = planLoad(steps, 0);
    expect(secondsLeft(plan, 0)).toBe(22);
    expect(secondsLeft(moveTo(plan, stepId('guest', 'abhishek'), 1_000), 3_000)).toBe(3);
    expect(secondsLeft(moveTo(plan, stepId('guest', 'abhishek'), 1_000), 9_000)).toBeNull();
  });

  it('moves forward only, and learns a step\'s time from this machine\'s loads', () => {
    const plan = moveTo(planLoad(steps, 0), stepId('face'), 20_000);
    expect(moveTo(plan, stepId('model'), 21_000)).toBe(plan);
    expect(expectedStepMs('model')).toBe(12_000 + (20_000 - 12_000) * 0.4);
    expect(planLoad(steps, 0).steps[0].expectedMs).toBe(15_200);
    // A step skipped over is not recorded; a face that answered at once says nothing of a render.
    moveTo(planLoad(steps, 0), stepId('guest', 'abhishek'), 3_000);
    expect(expectedStepMs('model')).toBe(15_200);
    finishLoad(planLoad([steps[1]], 0), 100);
    expect(expectedStepMs('face')).toBe(5_000);
    recordStepMs('face', 2_000);
    expect(expectedStepMs('face')).toBe(3_800);
  });

  it('names the step under way', () => {
    expect(steps.map((step) => stepLabel({ ...step, expectedMs: 1 }))).toEqual([
      'Loading the portrait model…', "Rendering Jinx's live video…", 'Preparing Abhishek…',
    ]);
  });
});
