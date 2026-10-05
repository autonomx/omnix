import { expect, test } from '@playwright/test';

// WP-9.10: every workspace shows an error state, not a blank page or a crash,
// when the gateway fails.
test.beforeEach(async ({ page }) => {
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'The gateway is unavailable.' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
});

// RPG is being retired (DECISIONS, WP-9.3); its gateway errors stay in its hidden panels.
const workspaces = [
  ['Chatbot', '/chatbot'],
  ['Storyteller', '/storyteller'],
  ['Podcast', '/podcast'],
  ['Voice Studio', '/voice'],
  ['Voice Cloning', '/voice-cloning'],
  ['STT', '/stt'],
  ['Image Generation', '/image-generation'],
  ['Audiobook', '/audiobook'],
  ['Trading', '/trading'],
  ['Providers', '/providers'],
  ['Models', '/models'],
  ['Jobs / Runs', '/jobs'],
  ['Assets', '/assets'],
  ['Reports', '/reports'],
  ['Settings', '/settings'],
  ['Diagnostics', '/diagnostics'],
] as const;

const ERROR_TEXT = /could not|couldn't|failed|unavailable|error|not reachable|offline/i;

for (const [workspace, route] of workspaces) {
  test(`${workspace} shows an error state when the gateway fails`, async ({ page }) => {
    await page.goto(route);
    await expect(page.getByRole('banner').getByLabel(`${workspace}, Local-first`)).toBeVisible();
    await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 30_000 });

    const main = page.getByRole('main');
    await expect(main.getByText(ERROR_TEXT).first()).toBeVisible({ timeout: 15_000 });
    await expect(main.getByRole('heading', { name: /stopped working|needs a reload/ })).toHaveCount(0);
  });
}
