import type { HermesSequencePreviewState } from './HermesSequencePreview';

export function hSeqSummary(value: HermesSequencePreviewState | null | undefined): string {
  if (!value) return 'not ready';
  const count = value.items?.length ?? 0;
  const name = value.objective?.trim() || 'untitled';
  return `${name} (${count} item${count === 1 ? '' : 's'})`;
}
