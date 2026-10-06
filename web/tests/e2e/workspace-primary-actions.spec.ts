import { expect, test } from '@playwright/test';

// WP-9.10: the primary action of the workspaces that app-shell.spec.ts does not
// cover, against a mocked gateway.
test.beforeEach(async ({ page }) => {
  await page.route((url) => url.pathname.startsWith('/api/'), (route) => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'unmocked_test_route' }),
  }));
  await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
});

test('audiobook creates a project from its details', async ({ page }) => {
  const created: unknown[] = [];
  await page.route((url) => url.pathname === '/api/audiobook/projects', async (route) => {
    if (route.request().method() === 'POST') {
      created.push(route.request().postDataJSON());
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'book:1', title: 'The Lantern', author: 'Mira Vale', language: 'en', state: 'draft' }) });
      return;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ projects: [] }) });
  });

  await page.goto('/audiobook');
  await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 30_000 });
  await page.getByLabel('Project title *').fill('The Lantern');
  await page.getByLabel('Author').fill('Mira Vale');
  await page.getByRole('button', { name: /Create project/ }).click();

  await expect(page.getByRole('status').filter({ hasText: 'Project created. Upload a source book to begin.' })).toBeVisible();
  expect(created).toEqual([expect.objectContaining({ title: 'The Lantern', author: 'Mira Vale', language: 'en' })]);
  await expect(page).toHaveURL(/[?&]project=book%3A1|[?&]project=book:1/);
});

test('settings saves a changed default', async ({ page }) => {
  const saved: string[] = [];
  await page.route((url) => url.pathname === '/api/settings/profile', async (route) => {
    if (route.request().method() === 'POST') {
      saved.push(route.request().postData() ?? '');
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true }) });
      return;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ settings: { settings_control_center: {} } }) });
  });

  await page.goto('/settings?category=jobs-assets-storage');
  await expect(page.getByText(/^Loading .* workspace…$/)).toHaveCount(0, { timeout: 30_000 });
  await page.getByLabel('Retention days').fill('45');
  await expect(page.getByRole('status').filter({ hasText: '1 unsaved change' })).toBeVisible();
  await page.getByRole('button', { name: 'Save changes' }).click();

  await expect.poll(() => saved.length).toBe(1);
  expect(saved[0]).toContain('"retentionDays":45');
});
