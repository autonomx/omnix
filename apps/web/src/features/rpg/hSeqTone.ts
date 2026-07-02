import type { HermesSequencePreviewState } from './HermesSequencePreview';

export function hSeqItemCount(value: HermesSequencePreviewState | null | undefined): number {
  return value?.items?.length ?? 0;
}

export function hSeqHasRows(value: HermesSequencePreviewState | null | undefined): boolean {
  return hSeqItemCount(value) > 0;
}
