import { expect, test, type Page } from '@playwright/test';

const CHARACTER = {
  id: 'character-1', display_name: 'Test character', description: '', personality_prompt: '', default_greeting: '',
  speech_style: {}, status: 'active', active_version: 1, default_voice_asset_id: null,
};

async function openCharacters(page: Page): Promise<void> {
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const { pathname } = new URL(route.request().url());
    const json = (body: unknown) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    if (pathname === '/api/auth/session') return json({ enforced: false, mode: 'disabled', authenticated: true, roles: ['owner'] });
    if (pathname === '/api/characters') return json({ characters: [CHARACTER] });
    if (pathname.endsWith('/avatar-pack/optional')) return json(null);
    if (pathname.endsWith('/live2d-models')) return json({ models: [], runtime_installed: false });
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not mocked' }) });
  });
  await page.setViewportSize({ width: 1400, height: 700 });
  await page.goto('/chatbot');
  await page.getByRole('button', { name: /Characters/ }).first().click();
}

// The hidden file input takes focus when it opens its dialog and again when the dialog is cancelled. The chat shell
// is overflow-hidden, so if focus scrolls it the view goes blank with no scrollbar to bring it back.
for (const [tab, input] of [['Live portrait', 'Portrait image'], ['Generated avatar', 'Upload source image']]) {
  test(`opening the ${tab} file picker leaves the chat shell where it is`, async ({ page }) => {
    await openCharacters(page);
    await page.getByRole('tab', { name: 'Live avatar' }).click();
    await page.getByRole('tab', { name: tab }).click();

    const picker = page.locator('label.character-avatar-upload-picker', { has: page.getByLabel(input) });
    const chooser = page.waitForEvent('filechooser');
    await picker.locator('span').click();
    await chooser;

    await expect(picker.locator('span')).toBeInViewport();
    expect(await page.locator('.assistant-chat-main').evaluate((shell) => shell.scrollTop)).toBe(0);
  });
}

test('the section tabs stay in reach, and a section opens at its top', async ({ page }) => {
  await openCharacters(page);
  await page.getByRole('tab', { name: 'Live avatar' }).click();
  const view = page.locator('.assistant-view-panel');
  await view.evaluate((panel) => { panel.scrollTop = panel.scrollHeight; });
  expect(await view.evaluate((panel) => panel.scrollTop)).toBeGreaterThan(0);

  await expect(page.getByRole('tablist', { name: 'Character sections' })).toBeInViewport();
  await page.getByRole('tab', { name: 'Danger zone' }).click();
  await expect(page.getByRole('heading', { name: 'Danger zone / cleanup' })).toBeInViewport();
  await expect(page.getByRole('combobox', { name: 'Select character' })).toBeInViewport();
  expect(await page.locator('.assistant-chat-main').evaluate((shell) => shell.scrollTop)).toBe(0);
});
