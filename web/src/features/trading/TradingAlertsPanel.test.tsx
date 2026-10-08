import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const tradingApi = vi.hoisted(() => ({
  alerts: vi.fn(),
  alertTriggers: vi.fn(),
  updateAlert: vi.fn(),
  archiveAlert: vi.fn(),
  createAlert: vi.fn(),
}));

vi.mock('./tradingApi', () => ({ tradingApi }));
vi.mock('./useTradingAlerts', () => ({
  useTradingAlertMutations: () => ({ remove: vi.fn(), refresh: vi.fn(async () => undefined) }),
}));

import { TradingAlertsPanel } from './TradingAlertsPanel';

const conditionsAlert = {
  alert_id: 'multi-1',
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  binding_id: null,
  condition_type: 'conditions',
  threshold: '0',
  frequency: 'once_per_bar_close',
  conditions: [
    { source: { kind: 'price', field: 'close' }, operator: 'crossing_up', target: { kind: 'value', value: '100' } },
    { source: { kind: 'indicator', indicator_id: 'rsi', inputs: { period: 14 }, output: 'rsi:14' }, operator: 'greater_than', target: { kind: 'value', value: '70' } },
  ],
  parameters: { message: '', notification_channels: ['app'], trigger_policy: 'once_per_bar_close' },
  evaluation_policy: { interval: '1h', allow_partial_bars: false, formula_version: 'omnix-indicators-v2' },
  enabled: true,
  cooldown_seconds: 0,
  revision: 2,
  created_at: '2026-10-08T09:00:00Z',
};

const trigger = {
  trigger_id: 't-1',
  alert_id: 'gone',
  instrument_id: 'crypto:BINANCE:spot:ETH-USDT',
  observed_value: '1',
  observed_price: '1',
  threshold: '0',
  condition_type: 'conditions',
  observed_at: '2026-10-08T09:00:00Z',
  evaluated_at: '2026-10-08T09:00:01Z',
  idempotency_key: 'k',
  payload: {},
};

describe('TradingAlertsPanel with alerts described by conditions', () => {
  it('lists, describes and edits them without touching their conditions', async () => {
    tradingApi.alerts.mockResolvedValue([conditionsAlert]);
    tradingApi.alertTriggers.mockResolvedValue([trigger]);
    tradingApi.updateAlert.mockResolvedValue(conditionsAlert);
    render(<TradingAlertsPanel instrumentId={conditionsAlert.instrument_id} bindingId={null} />);

    const title = 'BTCUSDT Price crossing up 100.00 and rsi:14 greater than 70.00';
    expect(await screen.findByTitle(title)).toBeTruthy();
    fireEvent.mouseEnter(screen.getByTitle(title).closest('li') as HTMLElement);
    expect(screen.getByRole('tooltip').textContent).toContain('Trigger: once per bar close');

    fireEvent.click(screen.getByRole('button', { name: `Options for ${title}` }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit alert' }));
    expect(screen.getByText('Price crossing up 100.00 and rsi:14 greater than 70.00')).toBeTruthy();
    expect(screen.queryByLabelText('Alert value')).toBeNull();
    const triggerSelect = screen.getByLabelText('Alert trigger') as HTMLSelectElement;
    expect(triggerSelect.value).toBe('once_per_bar_close');
    fireEvent.change(triggerSelect, { target: { value: 'once_per_minute' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(tradingApi.updateAlert).toHaveBeenCalled());
    const input = tradingApi.updateAlert.mock.calls[0][1];
    expect(input.condition_type).toBe('conditions');
    expect(input.conditions).toEqual(conditionsAlert.conditions);
    expect(input.frequency).toBe('once_per_minute');
    expect(input.cooldown_seconds).toBe(0);

    fireEvent.click(screen.getByRole('tab', { name: /Log/ }));
    expect(await screen.findByTitle('ETHUSDT conditions met 0.00')).toBeTruthy();
  });
});
