import { expect, test } from '@playwright/test';

const MESSAGE_COUNT = 5_000;
const createdAt = '2026-10-01T12:00:00Z';
const session = {
  id: 'long-session',
  title: 'Long session',
  created_at: createdAt,
  updated_at: createdAt,
  messages: Array.from({ length: MESSAGE_COUNT }, (_, index) => ({
    id: `message-${index}`,
    role: index % 2 ? 'assistant' : 'user',
    content: index % 7 ? `Message ${index}` : `Message ${index}\n\n${'A longer paragraph that wraps across several lines. '.repeat(6)}`,
    created_at: createdAt,
    metadata: {},
  })),
};

test.beforeEach(async ({ page }) => {
  // Never forward an unmocked call to an operator's gateway.
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unmocked_test_route' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
  await page.route((url) => url.pathname === '/api/chat/sessions', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ sessions: [{ ...session, messages: undefined, message_count: MESSAGE_COUNT }] }),
  }));
  await page.route((url) => url.pathname === `/api/chat/sessions/${session.id}`, (route) => route.fulfill({
    contentType: 'application/json', body: JSON.stringify(session),
  }));
});

test('a 5,000 message transcript keeps a bounded DOM and scrolls end to end', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/chatbot');
  // The dev server compiles the chat workspace on first use.
  await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 60_000 });
  const transcript = page.locator('.assistant-chat-messages');
  await expect(transcript.getByText(`Message ${MESSAGE_COUNT - 1}`, { exact: true })).toBeVisible({ timeout: 15_000 });

  const rendered = await transcript.locator('article.assistant-chat-message').count();
  expect(rendered).toBeGreaterThan(0);
  expect(rendered).toBeLessThan(60);

  await transcript.evaluate((element) => { element.scrollTop = 0; });
  await expect(transcript.getByText('Message 0', { exact: true })).toBeVisible();
  expect(await transcript.locator('article.assistant-chat-message').count()).toBeLessThan(60);
});
