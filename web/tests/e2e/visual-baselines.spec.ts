import { expect, test, type Page } from '@playwright/test';

// WP-9.8: screenshots of every workspace in dark and light mode, captured before
// the CSS migration. A difference fails the test; updating a baseline
// (`--update-snapshots`) is a reviewed change that a person approves.
const FIXED_TIME = new Date('2026-10-01T12:00:00Z');

// Font rendering differs by platform; the approved baselines are the Windows ones.
test.skip(process.platform !== 'win32', 'Visual baselines are captured and approved on Windows.');

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(FIXED_TIME);
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'The gateway is unavailable.' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
});

const workspaces = [
  ['chatbot', '/chatbot'],
  ['storyteller', '/storyteller'],
  ['podcast', '/podcast'],
  ['voice', '/voice'],
  ['voice-cloning', '/voice-cloning'],
  ['stt', '/stt'],
  ['image-generation', '/image-generation'],
  ['audiobook', '/audiobook'],
  ['trading', '/trading'],
  ['providers', '/providers'],
  ['models', '/models'],
  ['jobs', '/jobs'],
  ['assets', '/assets'],
  ['reports', '/reports'],
  ['settings', '/settings'],
  ['diagnostics', '/diagnostics'],
] as const;

const themes = ['aurora', 'graphite', 'liquid-glass', 'evergreen'] as const;

// Waits until no request has started for longer than React Query's retry delay,
// so every screen is captured after its failed requests settle. Trading polls,
// so the wait is bounded.
async function settle(page: Page): Promise<void> {
  let lastRequest = Date.now();
  const onRequest = () => { lastRequest = Date.now(); };
  page.on('request', onRequest);
  const deadline = Date.now() + 12_000;
  while (Date.now() - lastRequest < 2_500 && Date.now() < deadline) {
    await page.waitForTimeout(250);
  }
  page.off('request', onRequest);
}

async function openWith(page: Page, route: string, mode: 'dark' | 'light', theme: string): Promise<void> {
  await page.addInitScript(([storedMode, storedTheme]) => {
    window.localStorage.setItem('omnix.appearance.mode', storedMode);
    window.localStorage.setItem('omnix.appearance.theme', storedTheme);
  }, [mode, theme]);
  await page.goto(route);
  await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 30_000 });
  await settle(page);
  await page.evaluate(() => document.fonts.ready);
}

const screenshot = { animations: 'disabled', caret: 'hide', maxDiffPixelRatio: 0.002 } as const;

for (const mode of ['dark', 'light'] as const) {
  for (const [name, route] of workspaces) {
    test(`${name} in ${mode} mode matches its baseline`, async ({ page }) => {
      await openWith(page, route, mode, 'aurora');
      await expect(page).toHaveScreenshot(`${name}-${mode}.png`, screenshot);
    });
  }
  for (const theme of themes.slice(1)) {
    test(`chatbot with the ${theme} theme in ${mode} mode matches its baseline`, async ({ page }) => {
      await openWith(page, '/chatbot', mode, theme);
      await expect(page).toHaveScreenshot(`chatbot-${theme}-${mode}.png`, screenshot);
    });
  }
}
