import type { HermesSequencePreviewState } from './HermesSequencePreview';

export function hSeqRiskTone(value: HermesSequencePreviewState | null | undefined): 'quiet' | 'warn' | 'danger' {
  const risk = value?.risk?.toLowerCase();
  if (risk === 'high') return 'danger';
  if (risk === 'medium') return 'warn';
  return 'quiet';
}

export function hSeqNeedsReview(value: HermesSequencePreviewState | null | undefined): boolean {
  return Boolean(value?.user_gate || value?.items?.some((item) => item.user_gate !== false));
}
