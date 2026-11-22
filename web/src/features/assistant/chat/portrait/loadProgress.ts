/**
 * The progress of "Load live video" (owner request, 2026-11-22: show how far the load is). The portrait service says
 * only whether its model is loading or ready, so the bar is built from the steps the button walks through: the model
 * (when it is not up), the chat's face (its picture prepared and its idle loop rendered), then each portrait guest's.
 * A step fills evenly to 90% at its expected time and then creeps toward 99%, so the bar keeps moving and never claims
 * to be done before it is. Expected times start from measured loads (FlashHead: about 10-14 s for the model, a few
 * seconds a face) and follow this machine's own loads, kept in the browser.
 */

export type LoadStepKind = 'model' | 'face' | 'guest';
export type LoadStep = { id: string; kind: LoadStepKind; name: string; expectedMs: number };
export type LoadPlan = { steps: LoadStep[]; index: number; since: number };

const TIMES_KEY = 'omnix.livePortrait.loadTimes';
const DEFAULT_MS: Record<LoadStepKind, number> = { model: 12_000, face: 5_000, guest: 5_000 };
const MIN_RECORDED_MS = 300; // a face already prepared answers at once: that says nothing of a render
const MAX_RECORDED_MS = 180_000;
const AVERAGE_WEIGHT = 0.4;

function storedTimes(): Partial<Record<LoadStepKind, number>> {
  try {
    const raw = window.localStorage.getItem(TIMES_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === 'object' ? parsed as Partial<Record<LoadStepKind, number>> : {};
  } catch {
    return {};
  }
}

/** How long a step of this kind is expected to take here. */
export function expectedStepMs(kind: LoadStepKind): number {
  const stored = storedTimes()[kind];
  return typeof stored === 'number' && Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_MS[kind];
}

/** Folds a finished step's time into its kind's expected time. */
export function recordStepMs(kind: LoadStepKind, ms: number): void {
  if (!(ms >= MIN_RECORDED_MS) || ms > MAX_RECORDED_MS) return;
  const times = storedTimes();
  const before = expectedStepMs(kind);
  times[kind] = Math.round(before + (ms - before) * AVERAGE_WEIGHT);
  try {
    window.localStorage.setItem(TIMES_KEY, JSON.stringify(times));
  } catch {
    // Private mode or full storage: the defaults hold.
  }
}

export function stepId(kind: LoadStepKind, characterId = ''): string {
  return kind === 'guest' ? `guest:${characterId}` : kind;
}

export function planLoad(steps: readonly Omit<LoadStep, 'expectedMs'>[], now: number): LoadPlan {
  return { steps: steps.map((step) => ({ ...step, expectedMs: expectedStepMs(step.kind) })), index: 0, since: now };
}

/**
 * Moves the plan on to step `id`, forward only. The step left is recorded when it was the one just before; a step
 * skipped over (a guest prepared elsewhere meanwhile) is not.
 */
export function moveTo(plan: LoadPlan, id: string, now: number): LoadPlan {
  const target = plan.steps.findIndex((step) => step.id === id);
  if (target <= plan.index) return plan;
  if (target === plan.index + 1) recordStepMs(plan.steps[plan.index].kind, now - plan.since);
  return { ...plan, index: target, since: now };
}

/** Records the step under way, which the load has just finished. */
export function finishLoad(plan: LoadPlan, now: number): void {
  const step = plan.steps[plan.index];
  if (step) recordStepMs(step.kind, now - plan.since);
}

function stepFraction(elapsedMs: number, expectedMs: number): number {
  const ratio = Math.max(0, elapsedMs) / Math.max(1, expectedMs);
  return ratio <= 1 ? 0.9 * ratio : 0.9 + 0.09 * (1 - Math.exp(-(ratio - 1) * 1.5));
}

/** How far the whole load is, 0 to 1 (below 1 until it is done). */
export function loadFraction(plan: LoadPlan, now: number): number {
  const total = plan.steps.reduce((sum, step) => sum + step.expectedMs, 0);
  if (total <= 0) return 0;
  const done = plan.steps.slice(0, plan.index).reduce((sum, step) => sum + step.expectedMs, 0);
  const current = plan.steps[plan.index];
  const partial = current ? current.expectedMs * stepFraction(now - plan.since, current.expectedMs) : 0;
  return Math.min(0.99, (done + partial) / total);
}

/** About how long is left, in whole seconds; null once past the expected time (then it is "almost there"). */
export function secondsLeft(plan: LoadPlan, now: number): number | null {
  const current = plan.steps[plan.index];
  if (!current) return null;
  const later = plan.steps.slice(plan.index + 1).reduce((sum, step) => sum + step.expectedMs, 0);
  const left = current.expectedMs - (now - plan.since) + later;
  return left > 500 ? Math.ceil(left / 1000) : null;
}

export function stepLabel(step: LoadStep): string {
  if (step.kind === 'model') return 'Loading the portrait model…';
  if (step.kind === 'face') return step.name ? `Rendering ${step.name}'s live video…` : 'Rendering the live video…';
  return step.name ? `Preparing ${step.name}…` : 'Preparing a guest…';
}
