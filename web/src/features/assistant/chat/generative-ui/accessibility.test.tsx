import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import axe from 'axe-core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatUiRenderer } from './ChatUiRenderer';
import { parseChatUi } from './schema';
import type { ChatUiInteraction } from './uiActions';

// GUI-6.2: every golden fixture renders without axe violations (colour contrast is checked
// per theme preset in the browser; jsdom has no layout or computed colours).
const fixturesRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../resources/chat/generative_ui/fixtures');
const fixtures = readdirSync(fixturesRoot).filter((name) => name.endsWith('.json'))
  .map((name) => JSON.parse(readFileSync(join(fixturesRoot, name), 'utf8')) as { name: string; content: string; expected: unknown });

vi.mock('./chatChartAdapter', () => ({ mountTimeSeriesChart: vi.fn().mockResolvedValue(() => undefined) }));
vi.mock('../../../trading', () => ({
  fetchChatPriceBars: vi.fn().mockResolvedValue([{ time: 1_790_000_000, close: 1 }, { time: 1_790_086_400, close: 2 }]),
  tradingChartHref: (id: string) => `/trading?instrument=${id}`,
}));

const interaction: ChatUiInteraction = { active: true, submissions: {}, choose: vi.fn(), fillComposer: vi.fn() };

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function violations(container: HTMLElement) {
  const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  return result.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`);
}

describe('generative UI accessibility', () => {
  it.each(fixtures.map((fixture) => [fixture.name, fixture] as const))('%s has no axe violations', async (_name, fixture) => {
    const ui = parseChatUi({ ui: fixture.expected }, fixture.content);
    if (!ui) throw new Error('fixture did not parse');
    const { container } = render(<main><ChatUiRenderer ui={ui} messageId="msg:a11y" interaction={interaction} /></main>);

    expect(await violations(container)).toEqual([]);
  });

  it('keeps chart data tables and widgets reachable by keyboard in reading order', async () => {
    const fixture = fixtures.find((item) => item.name === 'chart_category_bar');
    const ui = fixture && parseChatUi({ ui: fixture.expected }, fixture.content);
    if (!ui) throw new Error('fixture did not parse');
    const { container } = render(<main><ChatUiRenderer ui={ui} messageId="msg:a11y" interaction={interaction} /></main>);

    const toggle = screen.getByRole('button', { name: 'Show data' });
    fireEvent.click(toggle);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-controls', screen.getByRole('table').parentElement?.id);
    expect(await violations(container)).toEqual([]);
  });
});
