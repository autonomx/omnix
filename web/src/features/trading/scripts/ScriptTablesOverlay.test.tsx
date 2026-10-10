import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { IndicatorOutput } from '../indicators/coreIndicators';
import { ScriptTablesOverlay } from './ScriptTablesOverlay';

function table(key: string, position: string, text: string, visible = true): IndicatorOutput {
  return {
    key, title: `table ${key}`, pane: 0, kind: 'table', points: [], visible,
    table: { position, rows: [[{ text, color: '#D1D4DC' }, null]], background: '#131722' },
  };
}

describe('script tables over the chart (TVP-11.1)', () => {
  it('draws each table at its position, stacking tables that share one, and skips hidden ones', () => {
    const { container } = render(<ScriptTablesOverlay outputs={[
      table('a', 'top_right', 'RSI 42'), table('b', 'top_right', 'MACD'), table('c', 'bottom_left', 'Vol'), table('d', 'middle_center', 'off', false),
      { key: 'line', title: 'Line', pane: 0, kind: 'line', points: [] },
    ]} />);
    const slots = container.querySelectorAll('.trading-script-table-slot');
    expect([...slots].map((slot) => slot.className)).toEqual(['trading-script-table-slot is-top-right', 'trading-script-table-slot is-bottom-left']);
    expect(slots[0].querySelectorAll('table')).toHaveLength(2);
    expect(screen.getByRole('table', { name: 'table a' })).toHaveStyle({ background: '#131722' });
    expect(screen.getByText('RSI 42')).toHaveStyle({ color: '#D1D4DC' });
    expect(screen.queryByText('off')).toBeNull();
  });

  it('draws nothing without tables', () => {
    const { container } = render(<ScriptTablesOverlay outputs={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
