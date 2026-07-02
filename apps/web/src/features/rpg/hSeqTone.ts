import type { HermesSequencePreviewState } from './HermesSequencePreview';

export function hSeqTone(value: HermesSequencePreviewState | null | undefined): 'quiet' | 'warn' | 'danger' {
  const level = value?.risk?.toLowerCase();
  if (level === 'high') return 'danger';
  if (level === 'medium') return 'warn';
  return 'quiet';
}

export function hSeqHasGate(value: HermesSequencePreviewState | null | undefined): boolean {
  return Boolean(value?.user_gate || value?.items?.some((item) => item.user_gate !== false));
}
