import type { HermesRpgSequenceResponse } from '../../api/hermesRpgSequenceClient';
import type { HermesSequencePreviewItem, HermesSequencePreviewState } from './HermesSequencePreview';

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function booleanValue(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function itemValue(value: unknown): HermesSequencePreviewItem {
  const item = recordValue(value);
  return {
    item_id: stringValue(item.item_id),
    statement: stringValue(item.statement),
    expected_effect: stringValue(item.expected_effect),
    guards: Array.isArray(item.guards) ? item.guards.filter((guard): guard is string => typeof guard === 'string') : undefined,
    user_gate: booleanValue(item.user_gate),
    status: stringValue(item.status),
  };
}

export function hermesSequencePreviewModel(response: HermesRpgSequenceResponse | null | undefined): HermesSequencePreviewState | null {
  const sequence = recordValue(response?.sequence);
  if (!response || Object.keys(sequence).length === 0) return null;
  const items = Array.isArray(sequence.items) ? sequence.items.map(itemValue) : [];
  return {
    sequence_id: stringValue(sequence.sequence_id),
    objective: stringValue(sequence.objective),
    domain: stringValue(sequence.domain),
    state_owner: stringValue(sequence.state_owner),
    risk: stringValue(sequence.risk),
    user_gate: booleanValue(sequence.user_gate),
    status: stringValue(sequence.status),
    items,
  };
}
