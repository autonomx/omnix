import { describe, expect, it } from 'vitest';
import { createTimelineNote, filterTimelineItemsByKind, sortTimelineItems } from './timeline-items';

describe('timeline item contracts', () => {
  it('sorts items by time and id', () => {
    const late = { id: 'b', kind: 'turn' as const, label: 'Late', createdAt: '2026-01-02' };
    const early = { id: 'a', kind: 'event' as const, label: 'Early', createdAt: '2026-01-01' };
    expect(sortTimelineItems([late, early])).toEqual([early, late]);
  });

  it('filters and creates note items', () => {
    const note = createTimelineNote('n1', 'Ready', '2026-01-01');
    expect(filterTimelineItemsByKind([note], 'note')).toEqual([note]);
  });
});
