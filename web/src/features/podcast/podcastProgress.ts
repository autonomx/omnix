/**
 * How far a podcast run is, for the progress bar under Generate (owner request 2026-11-24). A run writes the script,
 * then makes the preview (one voice job per line, or the cast speaking it), then the final render (every line again,
 * then the mix). Preview and final render cost about the same per line (about ten seconds on a local GPU) and the
 * script about a tenth of the whole, so those are the shares of the bar. When the final render reuses the preview's
 * takes (`podcastTakes.ts`) it only speaks what the preview missed and mixes, so the preview takes most of the bar.
 */
export type RunStage = 'script' | 'preview' | 'final';

export type RunProgress = {
  stage: RunStage;
  /** Steps done within the stage, out of `total`. */
  done: number;
  total: number;
  /** What the run is doing now, e.g. "Final render: line 12 of 40 (Ada)". */
  label: string;
  /** The final render reuses the preview's takes. */
  reuse?: boolean;
};

const SHARES: Record<RunStage, { start: number; span: number }> = {
  script: { start: 0, span: 10 },
  preview: { start: 10, span: 45 },
  final: { start: 55, span: 45 },
};
const REUSE_SHARES: Record<RunStage, { start: number; span: number }> = {
  script: { start: 0, span: 10 },
  preview: { start: 10, span: 80 },
  final: { start: 90, span: 10 },
};

/** The run as a whole percentage: the stages before this one, plus this one's share of steps done. */
export function runPercent(progress: Pick<RunProgress, 'stage' | 'done' | 'total' | 'reuse'>): number {
  const { start, span } = (progress.reuse ? REUSE_SHARES : SHARES)[progress.stage];
  const fraction = progress.total > 0 ? Math.min(1, Math.max(0, progress.done / progress.total)) : 0;
  return Math.round(start + span * fraction);
}

/** The stage rail's active step (see `stages()` in the workspace): the script is the plan and script, the preview the speaking turns, the final render the mix. */
export function activeStageIndex(stage: RunStage | undefined): number {
  return stage === 'script' ? 1 : stage === 'final' ? 3 : 2;
}

/** A job's reported steps, if it has reported any. */
export function jobSteps(progress: { current?: number | null; total?: number | null } | null | undefined) {
  const total = Number(progress?.total || 0);
  return total > 0 ? { done: Number(progress?.current || 0), total } : { done: 0, total: 1 };
}
