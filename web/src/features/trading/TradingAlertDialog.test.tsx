import { readFileSync } from 'node:fs';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradingAlertDialog, type TradingAlertEditorState } from './TradingAlertDialog';

afterEach(cleanup);

const editor: TradingAlertEditorState = {
  mode: 'create', alertId: null, x: 0, y: 0, condition: 'price_above', threshold: '100', expiresAt: '',
  expiration: 'never', triggerPolicy: 'every_time', message: '', notifications: ['app', 'sound'],
  indicator: 'rsi', period: '14', lookback: '1',
};

function renderDialog(state: TradingAlertEditorState, onChange = vi.fn()) {
  render(<TradingAlertDialog editor={state} symbol="BTC" latestPrice={100} status="ready" onChange={onChange} onSubmit={vi.fn()} onClose={vi.fn()} />);
  return onChange;
}

describe('TradingAlertDialog webhook, name and placeholders (TVP-1.5)', () => {
  it('asks for a webhook URL with the Webhook channel, required until one is stored', () => {
    const onChange = renderDialog({ ...editor, notifications: ['app', 'webhook'] });
    const url = screen.getByLabelText('Webhook URL') as HTMLInputElement;
    expect(url.required).toBe(true);
    fireEvent.change(url, { target: { value: 'https://hooks.example/x' } });
    expect(onChange).toHaveBeenCalledWith({ webhookUrl: 'https://hooks.example/x' });
    fireEvent.change(screen.getByLabelText('Webhook signing secret'), { target: { value: 's3' } });
    expect(onChange).toHaveBeenCalledWith({ webhookSecret: 's3' });
  });

  it('shows a stored webhook by its host only and keeps it unless replaced', () => {
    renderDialog({ ...editor, notifications: ['webhook'], webhookDisplay: 'https://hooks.example', webhookHasSecret: true });
    const url = screen.getByLabelText('Webhook URL') as HTMLInputElement;
    expect(url.required).toBe(false);
    expect(url.value).toBe('');
    expect(url.placeholder).toContain('https://hooks.example');
    expect((screen.getByLabelText('Webhook signing secret') as HTMLInputElement).placeholder).toContain('Secret saved');
  });

  it('edits the name and lists the message placeholders', () => {
    const onChange = renderDialog(editor);
    fireEvent.change(screen.getByLabelText('Alert name'), { target: { value: 'Breakout' } });
    expect(onChange).toHaveBeenCalledWith({ name: 'Breakout' });
    expect(screen.getByText(/\{\{ticker\}\}/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Webhook URL')).toBeNull();
  });

  it('stacks the message box above its placeholder list, styled like the other fields', () => {
    // The settings row is a flex row; the box and its long list side by side squeezed the box to a sliver.
    renderDialog(editor);
    const field = screen.getByLabelText('Alert message').parentElement as HTMLElement;
    expect(field.className).toBe('trading-alert-message-field');
    expect(field.lastElementChild?.className).toBe('trading-alert-placeholders');
    const overlay = readFileSync('src/features/trading/TradingChartAlertOverlay.css', 'utf8');
    expect(overlay).toContain('.trading-alert-dialog-settings dd.trading-alert-message-field{flex-direction:column;align-items:stretch;');
    expect(overlay).toContain('.trading-alert-dialog-settings select,.trading-alert-dialog-settings textarea{min-width:0;width:100%;');
    const opaque = readFileSync('src/features/trading/TradingChartAlertOpaque.css', 'utf8');
    expect(opaque.match(/\.trading-alert-dialog-settings textarea/g)).toHaveLength(3);  // both layers, light theme
  });

  it('opens above the chart controls, so the y-axis currency never shows through its close button', () => {
    const zIndex = (file: string, selector: string) => {
      const css = readFileSync(`src/features/trading/${file}`, 'utf8');
      const rule = css.slice(css.indexOf(`${selector}{`));
      return Number(/z-index:(\d+)/.exec(rule.slice(0, rule.indexOf('}')))?.[1]);
    };
    const dialog = zIndex('TradingChartAlertOverlay.css', '.trading-chart-alert-editor-positioner');
    expect(dialog).toBeGreaterThan(zIndex('TradingYAxisControls.css', '.trading-y-axis-controls'));
    expect(dialog).toBeGreaterThan(zIndex('TradingChartEnhancements.css', '.trading-indicator-object-toolbar'));
  });
});

describe('TradingAlertDialog sound', () => {
  it('offers the sound picker only with the Sound channel', () => {
    renderDialog({ ...editor, notifications: ['app'] });
    expect(screen.queryByLabelText('Alert sound')).toBeNull();
  });

  it('chooses the sound, chime by default', () => {
    const onChange = renderDialog(editor);
    const picker = screen.getByLabelText('Alert sound') as HTMLSelectElement;
    expect(picker.value).toBe('chime');
    fireEvent.change(picker, { target: { value: 'alarm' } });
    expect(onChange).toHaveBeenCalledWith({ sound: 'alarm' });
  });
});

describe('TradingAlertDialog chart indicators (TVP-1.3)', () => {
  const choices = [{ key: 'rsi', label: 'RSI (14)', outputs: [{ key: 'rsi:14', title: 'RSI' }], inputs: { period: 14 } as never }];

  it('offers the chart indicators instead of the legacy list on a new indicator alert', () => {
    render(<TradingAlertDialog editor={{ ...editor, condition: 'indicator_above' }} symbol="BTC" latestPrice={100} status="ready" onChange={vi.fn()} onSubmit={vi.fn()} onClose={vi.fn()} indicatorChoices={choices} />);
    expect(screen.getByLabelText('Alert chart indicator')).toBeInTheDocument();
    expect(screen.queryByLabelText('Alert indicator')).toBeNull();
    expect(screen.queryByLabelText('Alert crossing')).toBeNull();
  });

  it('keeps the legacy list without chart indicators', () => {
    render(<TradingAlertDialog editor={{ ...editor, condition: 'indicator_above' }} symbol="BTC" latestPrice={100} status="ready" onChange={vi.fn()} onSubmit={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByLabelText('Alert indicator')).toBeInTheDocument();
  });
});

describe('TradingAlertDialog drawing levels (TVP-1.4)', () => {
  it('picks the drawing level the line alert follows', () => {
    const levels = [
      { key: 'upper', label: 'Upper line', anchors: [{ time: 'a', price: 2 }, { time: 'b', price: 3 }] as const },
      { key: 'lower', label: 'Lower line', anchors: [{ time: 'a', price: 1 }, { time: 'b', price: 2 }] as const },
    ];
    const onChange = renderDialog({ ...editor, condition: 'trendline_crossing', drawingId: 'ch', drawingLevels: levels, drawingLevel: 'upper', trendlinePoints: [{ time: 'a', price: 2 }, { time: 'b', price: 3 }] });
    fireEvent.change(screen.getByLabelText('Alert drawing level'), { target: { value: 'lower' } });
    expect(onChange).toHaveBeenCalledWith({ drawingLevel: 'lower', trendlinePoints: [{ time: 'a', price: 1 }, { time: 'b', price: 2 }] });
  });
});
