import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  // Never forward an unmocked call to an operator's gateway; workspaces render their empty and error states.
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unmocked_test_route' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
});

const workspaces = [
  ['RPG', '/rpg'],
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

for (const [workspace, route] of workspaces) {
  test(`${workspace} has no critical or serious accessibility violations`, async ({ page }) => {
    await page.goto(route);
    await expect(page.getByRole('banner').getByLabel(`${workspace}, Local-first`)).toBeVisible();
    // Analyse the loaded workspace, not the lazy-loading fallback.
    await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 20_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const blocking = results.violations
      .filter((violation) => violation.impact === 'critical' || violation.impact === 'serious')
      .map((violation) => ({ id: violation.id, nodes: violation.nodes.slice(0, 5).map((node) => node.target.join(' ')) }));
    expect(blocking).toEqual([]);
  });
}
