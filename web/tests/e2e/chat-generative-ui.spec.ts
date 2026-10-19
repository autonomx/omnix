import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

// Chat generative UI visual QA (GUI-2.5, GUI-6.2): every golden fixture in each theme preset,
// light and dark, at 375 px and 1280 px, through the development-only fixture gallery.
test.beforeEach(async ({ page }) => {
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unmocked_test_route' }),
  }));
});

const themes = ['aurora', 'graphite', 'liquid-glass', 'evergreen'] as const;
const appearances = ['dark', 'light'] as const;
const widths = [375, 1280] as const;

for (const theme of themes) {
  for (const appearance of appearances) {
    for (const width of widths) {
      test(`fixtures in ${theme} ${appearance} at ${width}px: no blocking axe violations or page scroll`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto('/dev/chat-ui-fixtures');
        await page.getByLabel('Theme').selectOption(theme);
        await page.getByLabel('Appearance').selectOption(appearance);
        await page.getByLabel('Width').selectOption(String(width));
        await expect(page.getByRole('heading', { name: /Chat generative UI fixtures/ })).toBeVisible();
        await expect(page.getByText(/Loading market data/)).toHaveCount(0);

        const results = await new AxeBuilder({ page })
          .include('.gui-gallery article')
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();
        const blocking = results.violations
          .filter((violation) => violation.impact === 'critical' || violation.impact === 'serious')
          .map((violation) => ({ id: violation.id, nodes: violation.nodes.slice(0, 5).map((node) => node.target.join(' ')) }));
        expect(blocking).toEqual([]);

        const overflow = await page.evaluate(() => document.scrollingElement!.scrollWidth - document.scrollingElement!.clientWidth);
        expect(overflow).toBeLessThanOrEqual(0);
      });
    }
  }
}
