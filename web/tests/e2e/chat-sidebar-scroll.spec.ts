import { expect, test, type Page } from '@playwright/test';

const SESSIONS = Array.from({ length: 40 }, (_, index) => ({
  id: `chat:${index + 1}`,
  title: `Chat number ${index + 1}`,
  message_count: 0,
  messages: [],
  created_at: '2026-06-14T00:00:00Z',
  updated_at: '2026-06-14T00:00:00Z',
}));

async function openChat(page: Page): Promise<void> {
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const { pathname } = new URL(route.request().url());
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (pathname === '/api/auth/session') return json({ enforced: false, mode: 'disabled', authenticated: true, roles: ['owner'] });
    if (pathname === '/api/chat/sessions') return json({ sessions: SESSIONS });
    const session = SESSIONS.find((candidate) => pathname === `/api/chat/sessions/${encodeURIComponent(candidate.id)}`);
    if (session) return json(session);
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not mocked' }) });
  });
  await page.setViewportSize({ width: 1400, height: 800 });
  await page.goto('/chatbot');
  await expect(page.locator('.assistant-chatgpt-session[title="Chat number 40"]')).toBeAttached();
}

test('scrolling the chat sidebar leaves only New chat in place', async ({ page }) => {
  await openChat(page);
  const newChat = page.getByRole('button', { name: 'New chat' });
  const rail = page.locator('.assistant-chat-sidebar-scroll');
  const firstView = page.getByRole('button', { name: 'Open Chats view' });

  // At the top: New chat, then the views, then the sessions.
  await expect(newChat).toBeVisible();
  await expect(firstView).toBeInViewport();
  const newChatTop = (await newChat.boundingBox())?.y;
  const firstViewTop = (await firstView.boundingBox())?.y ?? 0;
  const pinnedTop = (await page.getByRole('heading', { name: 'Pinned' }).boundingBox())?.y ?? 0;
  expect(newChatTop).toBeLessThan(firstViewTop);
  expect(firstViewTop).toBeLessThan(pinnedTop);

  await rail.evaluate((element) => { element.scrollTop = element.scrollHeight; });

  await expect(page.locator('.assistant-chat-sidebar-new')).toHaveClass(/scrolled/);
  expect((await newChat.boundingBox())?.y).toBe(newChatTop);
  const railTop = (await rail.boundingBox())?.y ?? 0;
  const lastView = page.getByRole('button', { name: 'Open Settings view' });
  expect(((await lastView.boundingBox())?.y ?? 0) + ((await lastView.boundingBox())?.height ?? 0)).toBeLessThanOrEqual(railTop);
  await expect(page.locator('.assistant-chatgpt-session[title="Chat number 40"]')).toBeInViewport();

  await rail.evaluate((element) => { element.scrollTop = 0; });
  await expect(page.locator('.assistant-chat-sidebar-new')).not.toHaveClass(/scrolled/);
});

test('a minimized chat sidebar keeps New chat as an icon', async ({ page }) => {
  await openChat(page);
  await page.getByRole('button', { name: 'Minimize assistant sidebar' }).click();

  const newChat = page.getByRole('button', { name: 'New chat' });
  await expect(newChat).toBeVisible();
  await expect(newChat.locator('span').nth(1)).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Sessions' })).toBeHidden();
});
