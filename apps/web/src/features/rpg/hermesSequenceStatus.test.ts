import { describe, expect, it } from 'vitest';
import { hermesSequenceCanUseFirstItem, hermesSequenceStatusLabel } from './hermesSequenceStatus';

describe('hermesSequenceStatus', () => {
  it('labels missing and ready responses', () => {
    expect(hermesSequenceStatusLabel(null)).toBe('not checked');
    expect(hermesSequenceStatusLabel({ ok: true })).toBe('ready');
  });

  it('labels validation and gate issues', () => {
    expect(hermesSequenceStatusLabel({ ok: false, validation: { errors: ['missing_objective'] } })).toBe('1 validation issue');
    expect(hermesSequenceStatusLabel({ ok: false, gate: { blocked_count: 2 } })).toBe('2 gated items');
    expect(hermesSequenceStatusLabel({ ok: false, sequence: { items: [] } })).toBe('empty');
  });

  it('reports whether a first item is usable', () => {
    expect(hermesSequenceCanUseFirstItem({ ok: false })).toBe(false);
    expect(hermesSequenceCanUseFirstItem({ ok: true, sequence: { items: [{ statement: 'look around' }] } })).toBe(true);
  });
});
