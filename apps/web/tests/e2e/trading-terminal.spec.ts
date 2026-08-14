import { expect, test, type Page, type Route } from '@playwright/test';

const instrument = {
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  asset_class: 'crypto',
  instrument_type: 'spot',
  venue: 'BINANCE',
  venue_symbol: 'BTC-USDT',
  display_symbol: 'BTCUSDT',
  base_currency: 'BTC',
  quote_currency: 'USDT',
  exchange_timezone: 'UTC',
  session_calendar: '24x7',
  price_scale: 100,
  minimum_tick: '0.01',
  status: 'active',
} as const;

const binding = {
  binding_id: 'binance:historical_polling:crypto:BINANCE:spot:BTC-USDT',
  instrument_id: instrument.instrument_id,
  provider: 'binance',
  provider_symbol: 'BTCUSDT',
  feed_type: 'historical_polling',
  realtime_scope: 'mocked e2e feed',
  delay_seconds: 0,
  adjustment_capabilities: ['raw'],
  supported_intervals: ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w', '1mo'],
  usage_scope: 'personal_local',
  is_official_api: true,
} as const;

const workspacePayload = (name = 'Main Workspace') => ({
  schemaVersion: 2,
  name,
  layout: 'auto',
  activeChartId: 'chart-1',
  charts: [{
    chartId: 'chart-1',
    instrumentId: instrument.instrument_id,
    bindingId: binding.binding_id,
    interval: '1h',
    chartType: 'candlestick',
    indicators: [
      { id: 'sma', period: 20, enabled: true },
      { id: 'rsi', period: 14, enabled: true },
      { id: 'macd', period: 9, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9, enabled: false },
    ],
  }],
  links: { instrument: false, interval: false, crosshair: true, visibleRange: true },
  panels: { right: false, bottom: false },
  favoriteInstrumentIds: [],
});

function bars() {
  return Array.from({ length: 120 }, (_, index) => {
    const start = new Date(Date.UTC(2026, 0, 1, index, 0));
    const end = new Date(start.getTime() + 3_600_000);
    const base = 70_000 + index * 10;
    return {
      instrument_id: instrument.instrument_id,
      interval: '1h',
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      open: String(base),
      high: String(base + 30),
      low: String(base - 20),
      close: String(base + 10),
      volume: String(100 + index),
      is_final: true,
      adjustment_mode: 'raw',
      session: '24x7',
      provider: 'binance',
      provider_event_id: String(index),
      provider_sequence: index,
      ingestion_revision: 1,
      received_at: '2026-01-06T00:00:00Z',
    };
  });
}

type MockState = {
  records: Map<string, { record_id: string; record_type: string; revision: number; payload: Record<string, unknown>; status: string }>;
  alerts: Array<Record<string, unknown>>;
  drawingWrites: number;
  barLimits: number[];
};

async function fulfill(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installTradingMocks(page: Page): Promise<MockState> {
  const main = {
    record_id: 'main',
    record_type: 'workspace',
    revision: 1,
    payload: workspacePayload(),
    status: 'active',
  };
  const state: MockState = {
    records: new Map([['main', main]]),
    alerts: [],
    drawingWrites: 0,
    barLimits: [],
  };

  await page.route('**/api/trading/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === '/api/trading/providers/status' || path === '/api/trading/providers') {
      await fulfill(route, {
        ok: true,
        providers: [{
          provider: 'binance',
          display_name: 'Binance fixture',
          enabled: true,
          status: 'ready',
          policy: {
            usage_scope: 'personal_local',
            redistribution_allowed: false,
            authentication_required: false,
            is_official_api: true,
            realtime_scope: 'mocked e2e feed',
            delay_seconds: 0,
            terms_reference: 'https://www.binance.com/en/terms',
            supported_asset_classes: ['crypto'],
            supported_intervals: binding.supported_intervals,
            history_depth: 'fixture',
            rate_limit_policy: 'fixture',
          },
          bindings: [binding],
          runtime: {
            request_count: 1,
            success_count: 1,
            failure_count: 0,
            consecutive_failures: 0,
            rate_limit_count: 0,
            in_flight: 0,
            max_concurrency: 4,
          },
        }],
      });
      return;
    }
    if (path === '/api/trading/instruments/search') {
      await fulfill(route, { instruments: [instrument] });
      return;
    }
    if (path === '/api/trading/bars') {
      state.barLimits.push(Number(url.searchParams.get('limit') ?? '0'));
      const dataset = bars();
      await fulfill(route, {
        instrument,
        binding,
        provenance: {
          instrument_id: instrument.instrument_id,
          requested_binding: binding.binding_id,
          resolved_binding: binding.binding_id,
          fallback_reason: null,
          dataset_fingerprint: 'playwright-bars-v1',
          freshness_mode: 'polled',
          as_of: dataset.at(-1)?.end_time,
          received_at: '2026-01-06T00:00:00Z',
          delay_seconds: 0,
          cached: false,
          history_complete: true,
        },
        interval: url.searchParams.get('interval') ?? '1h',
        bars: dataset.map((bar) => ({ ...bar, interval: url.searchParams.get('interval') ?? '1h' })),
      });
      return;
    }
    if (path === '/api/trading/diagnostics') {
      await fulfill(route, { ok: true, diagnostics: { providers: [], cache: { disk_bounded: true }, streams: [] } });
      return;
    }
    if (path === '/api/trading/workspaces' && method === 'GET') {
      await fulfill(route, { records: [...state.records.values()] });
      return;
    }
    if (path === '/api/trading/workspaces' && method === 'POST') {
      const input = request.postDataJSON() as { record_id: string; payload: Record<string, unknown> };
      const record = { record_id: input.record_id, record_type: 'workspace', revision: 1, payload: input.payload, status: 'active' };
      state.records.set(record.record_id, record);
      await fulfill(route, record, 201);
      return;
    }
    if (path.startsWith('/api/trading/workspaces/') && method === 'PUT') {
      const id = decodeURIComponent(path.split('/').at(-1) ?? '');
      const input = request.postDataJSON() as { payload: Record<string, unknown> };
      const previous = state.records.get(id);
      const record = { record_id: id, record_type: 'workspace', revision: (previous?.revision ?? 0) + 1, payload: input.payload, status: 'active' };
      state.records.set(id, record);
      await fulfill(route, record);
      return;
    }
    if (path.startsWith('/api/trading/workspaces/') && method === 'DELETE') {
      const id = decodeURIComponent(path.split('/').at(-1) ?? '');
      const previous = state.records.get(id);
      if (previous) state.records.delete(id);
      await fulfill(route, { ...(previous ?? main), status: 'archived', revision: (previous?.revision ?? 1) + 1 });
      return;
    }
    if (path === '/api/trading/drawings' && method === 'GET') {
      await fulfill(route, { records: [] });
      return;
    }
    if (path === '/api/trading/drawings' && method === 'POST') {
      state.drawingWrites += 1;
      const input = request.postDataJSON() as { record_id: string; payload: Record<string, unknown> };
      await fulfill(route, { record_id: input.record_id, record_type: 'drawing', revision: 1, payload: input.payload, status: 'active' }, 201);
      return;
    }
    if (path.startsWith('/api/trading/drawings/') && method === 'PUT') {
      state.drawingWrites += 1;
      const input = request.postDataJSON() as { record_id: string; payload: Record<string, unknown> };
      await fulfill(route, { record_id: input.record_id, record_type: 'drawing', revision: 2, payload: input.payload, status: 'active' });
      return;
    }
    if (path === '/api/trading/alerts' && method === 'GET') {
      await fulfill(route, { alerts: state.alerts });
      return;
    }
    if (path === '/api/trading/alerts' && method === 'POST') {
      const input = request.postDataJSON() as Record<string, unknown>;
      const alert = { ...input, enabled: true, revision: 1, last_observed_price: null, last_observed_value: null, last_triggered_at: null };
      state.alerts.unshift(alert);
      await fulfill(route, alert, 201);
      return;
    }
    if (path === '/api/trading/alerts/triggers') {
      await fulfill(route, { triggers: [] });
      return;
    }
    if (path.startsWith('/api/trading/alerts/') && method === 'PUT') {
      const id = decodeURIComponent(path.split('/').at(-1) ?? '');
      const input = request.postDataJSON() as Record<string, unknown>;
      const existing = state.alerts.find((alert) => alert.alert_id === id) ?? {};
      const updated = { ...existing, ...input, alert_id: id, revision: Number(existing.revision ?? 1) + 1 };
      state.alerts = state.alerts.map((alert) => alert.alert_id === id ? updated : alert);
      await fulfill(route, updated);
      return;
    }

    await fulfill(route, { records: [], alerts: [], triggers: [] });
  });

  return state;
}

test('Trading terminal smoke covers flexible layout, saved workspaces, drawings, and chart alerts', async ({ page }) => {
  const state = await installTradingMocks(page);
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => {
    const message = error.stack ?? error.message;
    pageErrors.push(message);
    console.error(`[trading-pageerror] ${message}`);
  });
  page.on('console', (message) => {
    if (message.type() === 'error') console.error(`[trading-console] ${message.text()}`);
  });
  await page.goto('/trading');

  await expect(page.getByRole('main', { name: /Trading/i })).toBeVisible();
  await expect(page.locator('.trading-chart-panel').first()).toBeVisible();
  await expect.poll(() => pageErrors, { message: 'Trading must initialize without browser exceptions' }).toEqual([]);
  await expect(page.locator('.trading-chart-ohlc').first()).toBeVisible();
  await expect(page.locator('.trading-terminal-header .trading-command-bar')).toBeAttached();
  await expect(page.locator('.trading-terminal-header')).toHaveCSS('height', '42px');
  await expect(page.getByRole('button', { name: 'Enter fullscreen chart' })).toHaveCount(1);
  await expect(page.getByRole('group', { name: 'Overlay indicators' })).toHaveCount(1);
  await page.getByRole('button', { name: 'Hide SMA 20 overlay' }).click();
  await expect(page.getByRole('button', { name: 'Show SMA 20 overlay' })).toBeVisible();
  await page.getByRole('button', { name: 'Show SMA 20 overlay' }).click();
  await page.getByRole('button', { name: 'Delete SMA 20 overlay' }).click();
  await expect(page.getByRole('button', { name: 'Delete SMA 20 overlay' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Indicators' }).click();
  const smaOption = page.getByRole('group', { name: 'Technical indicators' }).getByRole('button', { name: 'SMA 20', exact: true });
  await expect(smaOption).toHaveAttribute('aria-pressed', 'false');
  await smaOption.click();
  await expect(page.locator('.trading-timeframe-buttons > button')).toHaveCount(3);
  await expect(page.getByRole('button', { name: '1H' })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'All supported Trading intervals' })).toContainText('1H');
  const rangeNav = page.getByRole('navigation', { name: 'chart-1 visible range' });
  const timeframe = page.getByRole('combobox', { name: 'All supported Trading intervals' });
  for (const [range, interval] of [['1D', '1m'], ['5D', '5m'], ['1M', '30m'], ['3M', '1h'], ['6M', '2h'], ['YTD', '1d'], ['1Y', '1d'], ['5Y', '1w'], ['All', '1mo']] as const) {
    await rangeNav.getByRole('button', { name: range, exact: true }).click();
    const expectedLabel = interval.endsWith('mo') ? interval.replace('mo', 'M') : interval.endsWith('m') ? interval : interval.toUpperCase();
    await expect(timeframe).toContainText(expectedLabel);
    await expect(rangeNav.getByRole('button', { name: range, exact: true })).toHaveAttribute('aria-pressed', 'true');
  }
  await timeframe.click();
  const intervalMenu = page.getByRole('listbox', { name: 'TradingView intervals' });
  await expect(intervalMenu).toBeVisible();
  await expect(intervalMenu.getByRole('group', { name: 'Ticks' })).toContainText('1 tick');
  await expect(intervalMenu.getByRole('group', { name: 'Ranges' })).toContainText('1000 ranges');
  await expect(intervalMenu.getByRole('option', { name: '2 minutes' })).toBeEnabled();
  await intervalMenu.getByRole('option', { name: '5 minutes', exact: true }).click();
  await expect(timeframe).toContainText('5m');
  await expect.poll(() => state.barLimits).toContain(5_000);

  await page.getByLabel('Number of charts').selectOption('3');
  await expect(page.locator('.trading-chart-panel')).toHaveCount(3);
  await expect(page.getByRole('button', { name: 'Enter fullscreen chart' })).toHaveCount(3);
  await page.getByLabel('Grid columns').selectOption('columns-3');

  page.once('dialog', (dialog) => dialog.accept('Swing Research'));
  await page.getByRole('button', { name: 'Create workspace' }).click();
  await expect(page.getByLabel('Saved Trading workspace')).toContainText('Swing Research');

  await page.getByRole('button', { name: 'Favorite active instrument' }).click();
  await expect(page.getByRole('button', { name: 'Remove active instrument from favorites' })).toBeVisible();

  await page.getByRole('button', { name: 'Trend line' }).click();
  const overlay = page.locator('.trading-chart-panel.active .trading-drawing-overlay');
  const box = await overlay.boundingBox();
  expect(box).not.toBeNull();
  if (box) {
    await page.mouse.move(box.x + 100, box.y + 120);
    await page.mouse.down();
    await page.mouse.move(box.x + 260, box.y + 70);
    await page.mouse.up();
  }
  await expect.poll(() => state.drawingWrites).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Place price alert' }).click();
  await overlay.click({ position: { x: 180, y: 100 } });
  await expect(page.getByText('Add alert at price')).toBeVisible();
  await page.getByRole('button', { name: 'Create alert' }).click();
  await expect.poll(() => state.alerts.length).toBe(1);
  await expect(page.locator('.trading-alert-price-label')).toHaveCount(3);
  await expect(page.locator('.trading-chart-panel').filter({ has: page.locator('.trading-alert-price-label') })).toHaveCount(3);
});

test('indicator panes expose close, minimize, and reorder controls', async ({ page }) => {
  await installTradingMocks(page);
  await page.goto('/trading');

  const rsiControls = page.locator('.trading-indicator-pane-controls[data-indicator-id="rsi"]');
  await expect(rsiControls).toBeVisible();
  await expect(page.getByRole('button', { name: 'Move RSI 14 panel up' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Move RSI 14 panel down' })).toBeDisabled();

  await page.getByRole('button', { name: 'Minimize RSI 14 panel' }).click();
  await expect(page.getByRole('button', { name: 'Restore RSI 14 panel' })).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: 'Restore RSI 14 panel' }).click();

  await page.getByRole('button', { name: 'Indicators' }).click();
  await page.getByRole('button', { name: 'MACD 9' }).click();
  await expect(page.locator('.trading-indicator-pane-controls')).toHaveCount(2);
  await page.getByRole('button', { name: 'Move RSI 14 panel down' }).click();
  await expect.poll(async () => page.locator('.trading-indicator-pane-controls').evaluateAll((items) => items.map((item) => item.getAttribute('data-indicator-id')))).toEqual(['macd', 'rsi']);

  await page.getByRole('button', { name: 'Close RSI 14 panel' }).click();
  await expect(page.locator('.trading-indicator-pane-controls[data-indicator-id="rsi"]')).toHaveCount(0);
});
