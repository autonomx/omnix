import { afterEach, describe, expect, it, vi } from 'vitest';
import { tradingApi } from './tradingApi';
import type { TradingAlert } from './tradingTypes';

const alert: TradingAlert = {
  alert_id: 'alert-1',
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  binding_id: null,
  condition_type: 'price_above',
  threshold: '100',
  enabled: true,
  cooldown_seconds: 60,
  revision: 3,
};

afterEach(() => vi.unstubAllGlobals());

describe('Trading alert client', () => {
  it('sends revision headers for updates and archives', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(alert), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await tradingApi.updateAlert(alert, {
      instrument_id: alert.instrument_id,
      binding_id: null,
      condition_type: alert.condition_type,
      threshold: alert.threshold,
      enabled: false,
      cooldown_seconds: alert.cooldown_seconds,
    });
    await tradingApi.archiveAlert(alert);

    const update = fetchMock.mock.calls[0][1] as RequestInit;
    const archive = fetchMock.mock.calls[1][1] as RequestInit;
    expect(update.method).toBe('PUT');
    expect((update.headers as Record<string, string>)['If-Match']).toBe('3');
    expect(archive.method).toBe('DELETE');
    expect((archive.headers as Record<string, string>)['If-Match']).toBe('3');
  });

  it('keeps alert evaluation on the server endpoint', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ triggers: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await tradingApi.evaluateAlerts(alert.instrument_id, '101.5', '2026-08-05T12:00:00Z');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/trading/alerts/evaluate');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
  });
});
