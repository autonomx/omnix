import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatUiRenderer } from './ChatUiRenderer';
import { parseChatUi, type ParsedChatUi } from './schema';
import type { ChatUiInteraction } from './uiActions';

const fixturesRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../resources/chat/generative_ui/fixtures');

const mocks = vi.hoisted(() => ({
  throwStats: false,
  mountTimeSeriesChart: vi.fn(),
  fetchChatPriceBars: vi.fn(),
}));

vi.mock('./chatChartAdapter', () => ({ mountTimeSeriesChart: mocks.mountTimeSeriesChart }));
vi.mock('../../../trading', () => ({
  fetchChatPriceBars: mocks.fetchChatPriceBars,
  tradingChartHref: (instrumentId: string) => `/trading?instrument=${encodeURIComponent(instrumentId)}`,
}));
vi.mock('./components/StatsBlockView', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./components/StatsBlockView')>();
  return {
    StatsBlockView: (props: Parameters<typeof actual.StatsBlockView>[0]) => {
      if (mocks.throwStats) throw new Error('stats exploded');
      return actual.StatsBlockView(props);
    },
  };
});

function fixture(name: string): { ui: ParsedChatUi; content: string; raw: Record<string, unknown> } {
  const data = JSON.parse(readFileSync(join(fixturesRoot, `${name}.json`), 'utf8')) as { content: string; expected: Record<string, unknown> };
  const ui = parseChatUi({ ui: data.expected }, data.content);
  if (!ui) throw new Error(`fixture ${name} did not parse`);
  return { ui, content: data.content, raw: data.expected };
}

function interaction(overrides: Partial<ChatUiInteraction> = {}): ChatUiInteraction {
  return { active: true, submissions: {}, choose: vi.fn(), fillComposer: vi.fn(), ...overrides };
}

beforeEach(() => {
  mocks.throwStats = false;
  mocks.mountTimeSeriesChart.mockReset().mockResolvedValue(() => undefined);
  mocks.fetchChatPriceBars.mockReset();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('ChatUiRenderer', () => {
  it('renders a mixed reply: Markdown with a table, stats tiles, an alert and choices', () => {
    const { ui } = fixture('mixed_reply');
    const { container } = render(<ChatUiRenderer ui={ui} messageId="msg:1" interaction={interaction()} />);

    expect(screen.getByRole('heading', { level: 1, name: 'Quarter review' })).toBeInTheDocument();
    expect(container.querySelector('.assistant-markdown-table table')).not.toBeNull();
    const stats = screen.getByRole('region', { name: 'Headline figures' });
    expect(within(stats).getByText('$6,930')).toBeInTheDocument();
    expect(within(stats).getByText('AI-generated values')).toBeInTheDocument();
    expect(container.querySelector('.assistant-markdown-alert-note')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Forecast Q4' })).toBeEnabled();
    expect(container.textContent).not.toContain('omnix-ui');
  });

  it('shows a block that throws as its text and keeps the rest of the reply', () => {
    mocks.throwStats = true;
    const { ui } = fixture('mixed_reply');
    render(<ChatUiRenderer ui={ui} messageId="msg:1" interaction={interaction()} />);

    expect(screen.getByText('Revenue: $6,930 (+4.1%). Orders: 212 (+5.5%).')).toHaveClass('gui-fallback-text');
    expect(screen.getByRole('button', { name: 'Break down by region' })).toBeInTheDocument();
  });

  it('marks bound values as sourced and names the source', () => {
    const { ui } = fixture('stats_bound');
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(screen.getByText('CPI 2.4% in September', { selector: '.gui-stat-value' })).toBeInTheDocument();
    expect(screen.getByLabelText('Sourced from 1 source')).toBeInTheDocument();
    expect(screen.queryByText('AI-generated values')).toBeNull();
  });

  it('draws category bars in SVG and toggles a data table with formatted values', () => {
    const { ui } = fixture('chart_category_bar');
    const { container } = render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(container.querySelectorAll('rect.gui-chart-bar')).toHaveLength(4);
    expect(screen.getByRole('img', { name: /Revenue by segment/ })).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: 'Show data' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    const table = screen.getByRole('table');
    expect(within(table).getByRole('rowheader', { name: 'Services' })).toBeInTheDocument();
    expect(within(table).getByText('$24.2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide data' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('draws time series through the chat chart adapter with resolved theme colours', async () => {
    const { ui } = fixture('chart_time_line');
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    await waitFor(() => expect(mocks.mountTimeSeriesChart).toHaveBeenCalledTimes(1));
    const [, input] = mocks.mountTimeSeriesChart.mock.calls[0];
    expect(input.kind).toBe('line');
    expect(input.series.map((series: { name: string }) => series.name)).toEqual(['AAPL', 'MSFT']);
    expect(input.series[0].points[0]).toEqual([1_791_158_400, 0.4]);
    expect(input.formatValue(1.8)).toBe('1.8%');
    expect(screen.getByRole('list', { name: 'Series' })).toBeInTheDocument();
  });

  it('shows the data table when the chart library cannot draw', async () => {
    mocks.mountTimeSeriesChart.mockRejectedValue(new Error('no canvas'));
    const { ui } = fixture('chart_time_line');
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.getAllByText('2026-10-08').length).toBeGreaterThan(0);
  });

  it('renders source chips as safe external links', () => {
    const { ui } = fixture('sources_bound');
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    const link = screen.getByRole('link', { name: /Fed holds rates/ });
    expect(link).toHaveAttribute('href', 'https://example.com/fed');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not link a source with an unsafe URL', () => {
    const { ui } = fixture('sources_bound');
    const block = ui.segments.find((segment) => segment.kind === 'block');
    if (block?.kind !== 'block' || block.block.type !== 'sources') throw new Error('expected a sources block');
    block.block.refs[0].url = 'javascript:alert(1)';
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(screen.queryByRole('link', { name: /Fed holds rates/ })).toBeNull();
    expect(screen.getByText('Fed holds rates')).toBeInTheDocument();
  });

  it('sends exactly the label a choice shows, with its action reference', () => {
    const { ui } = fixture('choices_basic');
    const handlers = interaction();
    render(<ChatUiRenderer ui={ui} messageId="msg:reply" interaction={handlers} />);

    const button = screen.getByRole('button', { name: 'Show the 1-year trend' });
    button.focus();
    expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(handlers.choose).toHaveBeenCalledWith('Show the 1-year trend', {
      source_message_id: 'msg:reply', block_id: 'b1', action: 'choose', option_index: 1,
    });
    expect(screen.getByRole('group', { name: 'Next step' })).toBeInTheDocument();
  });

  it('disables older choices and highlights the one that was chosen', () => {
    const { ui } = fixture('choices_basic');
    const submissions = { b1: { content: 'Explain the dip', action: { source_message_id: 'msg:reply', block_id: 'b1', action: 'choose' as const, option_index: 2 } } };
    render(<ChatUiRenderer ui={ui} messageId="msg:reply" interaction={interaction({ active: false, submissions })} />);

    expect(screen.getByRole('button', { name: 'Compare with MSFT' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Explain the dip' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Explain the dip' })).toHaveAttribute('data-chosen', 'true');
  });

  it('fills the composer from a form without sending, substituting values as plain text', () => {
    const { ui } = fixture('form_basic');
    const handlers = interaction();
    render(<ChatUiRenderer ui={ui} messageId="msg:reply" interaction={handlers} />);

    fireEvent.change(screen.getByLabelText('Symbol *'), { target: { value: 'NVDA' } });
    fireEvent.click(screen.getByLabelText('Extended hours'));
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'keep {risk} literal' } });
    fireEvent.click(screen.getByRole('button', { name: 'Fill message' }));

    expect(handlers.choose).not.toHaveBeenCalled();
    expect(handlers.fillComposer).toHaveBeenCalledWith(
      'Backtest NVDA with a 2% stop, extended hours yes. Notes: keep {risk} literal',
      { source_message_id: 'msg:reply', block_id: 'b1', action: 'submit', values: { symbol: 'NVDA', risk: 2, extended: true, notes: 'keep {risk} literal' } },
    );
  });

  it('disables a form that is not the latest reply', () => {
    const { ui } = fixture('form_basic');
    render(<ChatUiRenderer ui={ui} messageId="msg:reply" interaction={interaction({ active: false })} />);

    expect(screen.getByLabelText('Symbol *')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fill message' })).toBeDisabled();
  });

  it('pins a price chart to its as-of time and links to the trading chart', async () => {
    const { ui } = fixture('price_chart_pinned');
    const asOf = Date.parse('2026-10-11T14:03:22Z') / 1000;
    mocks.fetchChatPriceBars.mockResolvedValue([
      { time: asOf - 3 * 86_400, close: 228 },
      { time: asOf - 86_400, close: 231 },
      { time: asOf + 86_400, close: 999 },
    ]);
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(screen.getByRole('link', { name: 'Open in chart' })).toHaveAttribute('href', '/trading?instrument=equity%3ANASDAQ%3AAAPL');
    expect(screen.getByText('2026-10-11')).toBeInTheDocument();
    await waitFor(() => expect(mocks.mountTimeSeriesChart).toHaveBeenCalledTimes(1));
    const [instrumentId, interval, limit] = mocks.fetchChatPriceBars.mock.calls[0];
    expect([instrumentId, interval]).toEqual(['equity:NASDAQ:AAPL', '1d']);
    expect(limit).toBeGreaterThan(183);
    const [, input] = mocks.mountTimeSeriesChart.mock.calls[0];
    expect(input.series[0].points.map(([, close]: [number, number]) => close)).toEqual([228, 231]);
  });

  it('says when market data is unavailable', async () => {
    mocks.fetchChatPriceBars.mockRejectedValue(new Error('502'));
    const { ui } = fixture('price_chart_pinned');
    render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(await screen.findByText(/Market data is unavailable/)).toBeInTheDocument();
  });

  it('renders fallback text for degraded blocks without JSON', () => {
    const { ui } = fixture('degraded_blocks');
    const { container } = render(<ChatUiRenderer ui={ui} messageId="msg:1" />);

    expect(screen.getByText('Options: Yes; No')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/[{}]/);
  });
});
