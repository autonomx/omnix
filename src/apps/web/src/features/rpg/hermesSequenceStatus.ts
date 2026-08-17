import type { HermesRpgSequenceResponse } from '../../api/hermesRpgSequenceClient';

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

export function hermesSequenceStatusLabel(response: HermesRpgSequenceResponse | null | undefined): string {
  if (!response) return 'not checked';
  if (response.ok) return 'ready';
  const validation = recordValue(response.validation);
  const gate = recordValue(response.gate);
  const errors = Array.isArray(validation.errors) ? validation.errors.length : 0;
  if (errors > 0) return `${errors} validation issue${errors === 1 ? '' : 's'}`;
  const blocked = numberValue(gate.blocked_count);
  if (blocked > 0) return `${blocked} gated item${blocked === 1 ? '' : 's'}`;
  const sequence = recordValue(response.sequence);
  if (Object.keys(sequence).length > 0) {
    const items = Array.isArray(sequence.items) ? sequence.items : [];
    if (items.length === 0) return 'empty';
  }
  return 'not ready';
}

export function hermesSequenceCanUseFirstItem(response: HermesRpgSequenceResponse | null | undefined): boolean {
  if (!response?.ok) return false;
  const sequence = recordValue(response.sequence);
  const items = Array.isArray(sequence.items) ? sequence.items : [];
  return items.some((item) => typeof recordValue(item).statement === 'string' && Boolean((recordValue(item).statement as string).trim()));
}
