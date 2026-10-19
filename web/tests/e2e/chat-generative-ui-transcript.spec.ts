import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

// A stored block reply in the real Chat workspace (GUI-2.2): components render with room to
// lay out, Markdown around them renders as before, and no block JSON is shown.
const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(resolve(here, '../../../resources/chat/generative_ui/fixtures/mixed_reply.json'), 'utf8')) as { content: string; expected: unknown };
const chart = JSON.parse(readFileSync(resolve(here, '../../../resources/chat/generative_ui/fixtures/chart_category_bar.json'), 'utf8')) as { content: string; expected: unknown };
const createdAt = '2026-10-11T12:00:00Z';
const session = {
  id: 'gui-session',
  title: 'Generative UI',
  created_at: createdAt,
  updated_at: createdAt,
  message_count: 4,
  messages: [
    { id: 'u1', role: 'user', content: 'How was the quarter?', created_at: createdAt, metadata: {} },
    { id: 'a1', role: 'assistant', content: chart.content, created_at: createdAt, metadata: { ui: chart.expected } },
    { id: 'u2', role: 'user', content: 'And the headline?', created_at: createdAt, metadata: {} },
    { id: 'a2', role: 'assistant', content: fixture.content, created_at: createdAt, metadata: { ui: fixture.expected } },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unmocked_test_route' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
  await page.route((url) => url.pathname === '/api/chat/sessions', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ sessions: [{ ...session, messages: undefined }] }),
  }));
  await page.route((url) => url.pathname === `/api/chat/sessions/${session.id}`, (route) => route.fulfill({
    contentType: 'application/json', body: JSON.stringify(session),
  }));
});

const combinations = (['aurora', 'graphite', 'liquid-glass', 'evergreen'] as const).flatMap((theme) => (
  (['dark', 'light'] as const).flatMap((mode) => ([1280, 375] as const).map((width) => [theme, mode, width] as const))
));

for (const [theme, mode, width] of combinations) {
  test(`a block reply renders as components in the transcript (${theme} ${mode} ${width}px)`, async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(([themeId, appearance]) => {
      window.localStorage.setItem('omnix.appearance.theme', themeId);
      window.localStorage.setItem('omnix.appearance.mode', appearance);
    }, [theme, mode]);
    await page.goto(`/chatbot?session=${session.id}`);
    await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 60_000 });
    const transcript = page.locator('.assistant-chat-messages');
    const stats = transcript.getByRole('region', { name: 'Headline figures' });
    await expect(stats).toBeVisible({ timeout: 15_000 });
    await expect(transcript.getByRole('button', { name: 'Forecast Q4' })).toBeVisible();
    await expect(transcript).not.toContainText('omnix-ui');

    // Blocks fill their message's width and never extend past it. (The workspace gives a message
    // about 230 px at 375 px; the top bar's own overflow at 1280 px exists without blocks.)
    const fit = await page.evaluate(() => [...document.querySelectorAll('.assistant-ui-reply')].map((reply) => {
      const content = reply.getBoundingClientRect();
      const inner = content.width - 40;
      return [...reply.querySelectorAll('.gui-block, .assistant-markdown-table')].map((block) => {
        const box = block.getBoundingClientRect();
        return { fills: box.width >= inner * 0.9, inside: box.left >= content.left - 1 && box.right <= content.right + 1 };
      });
    }).flat());
    expect(fit.length).toBeGreaterThan(3);
    expect(fit.filter((item) => !item.fills || !item.inside)).toEqual([]);

    // In situ (GUI-6.2): no blocking violations, contrast included, in the blocks and tables.
    await page.waitForTimeout(600); // past the blocks' fade-in
    const results = await new AxeBuilder({ page })
      .include('.assistant-chat-messages .gui-block')
      .include('.assistant-chat-messages .assistant-markdown-table')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const blocking = results.violations
      .filter((violation) => violation.impact === 'critical' || violation.impact === 'serious')
      .map((violation) => ({ id: violation.id, nodes: violation.nodes.slice(0, 5).map((node) => node.target.join(' ')) }));
    expect(blocking).toEqual([]);

    if (process.env.OMNIX_GUI_SCREENSHOTS) {
      await page.screenshot({ path: `${process.env.OMNIX_GUI_SCREENSHOTS}/transcript-${theme}-${mode}-${width}.png` });
    }
  });
}
