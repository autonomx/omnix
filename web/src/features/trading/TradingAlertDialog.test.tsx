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
