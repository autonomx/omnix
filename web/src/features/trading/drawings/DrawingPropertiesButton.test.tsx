import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradingChartContextMenu } from '../TradingChartContextMenu';
import type { TradingDrawing } from './drawingCommands';
import { DrawingPropertiesButton } from './DrawingPropertiesButton';

afterEach(cleanup);

const fibonacci: TradingDrawing = {
  drawingId: 'fib',
  instrumentId: 'fixture',
  toolType: 'fibonacci',
  points: [{ time: '2026-10-07T00:00:00.000Z', price: 1 }, { time: '2026-10-07T01:00:00.000Z', price: 2 }],
  selected: true,
  revision: 1,
};

describe('generic drawing properties dialog', () => {
  it('edits booleans and list-of-level records from the tool schema', () => {
    const onChange = vi.fn();
    render(<DrawingPropertiesButton drawing={fibonacci} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
    expect(screen.getByRole('dialog', { name: 'Fib retracement settings' })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Labels'));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ showLabels: false }));

    fireEvent.change(screen.getByLabelText('Levels 2 Level'), { target: { value: '0.25' } });
    const levels = onChange.mock.lastCall![0].levels;
    expect(levels[1]).toEqual({ value: 0.25, color: '', visible: true });
    expect(levels).toHaveLength(7);

    fireEvent.click(screen.getByLabelText('Levels 7 Visible'));
    expect(onChange.mock.lastCall![0].levels[6]).toMatchObject({ value: 1, visible: false });

    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(onChange.mock.lastCall![0].levels).toHaveLength(8);
    fireEvent.click(screen.getByRole('button', { name: 'Remove Levels 1' }));
    expect(onChange.mock.lastCall![0].levels[0]).toMatchObject({ value: 0.236 });
  });

  it('renders nothing for a tool without properties', () => {
    const { container } = render(<DrawingPropertiesButton drawing={{ ...fibonacci, toolType: 'text' }} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('drawing context-menu actions', () => {
  it('lists the actions a drawing tool offers and runs them with the drawing id', () => {
    const onDrawingAction = vi.fn();
    const noop = () => undefined;
    render(
      <TradingChartContextMenu
        point={{ x: 0, y: 0, time: '2026-10-07T00:00:00.000Z', price: 1, source: 'context-menu', drawingId: 'position', drawingActions: [{ id: 'ticket', label: 'Open order ticket' }] }}
        symbol="TEST"
        indicatorContext={false}
        drawingCount={1}
        indicatorCount={0}
        cursorLocked={false}
        tableVisible={false}
        onClose={noop}
        onReset={noop}
        onCopyPrice={noop}
        onPastePrice={noop}
        onAddAlert={null}
        onToggleCursor={noop}
        onToggleTable={noop}
        onObjectTree={noop}
        onApplyTemplate={noop}
        onRemoveDrawings={noop}
        onRemoveIndicators={noop}
        onSettings={noop}
        onDrawingAction={onDrawingAction}
      />,
    );
    fireEvent.click(screen.getByRole('menuitem', { name: /Open order ticket/ }));
    expect(onDrawingAction).toHaveBeenCalledWith('position', 'ticket');
  });
});
