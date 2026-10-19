import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
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

for (const [theme, mode] of [['aurora', 'dark'], ['graphite', 'light']] as const) {
  test(`a block reply renders as components in the transcript (${theme} ${mode})`, async ({ page }) => {
    test.setTimeout(90_000);
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

    const plot = transcript.locator('.gui-chart-svg').first();
    const box = await plot.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(300);
    if (process.env.OMNIX_GUI_SCREENSHOTS) {
      await page.waitForTimeout(800); // past the blocks' fade-in
      await page.screenshot({ path: `${process.env.OMNIX_GUI_SCREENSHOTS}/transcript-${theme}-${mode}.png` });
    }
  });
}
