import { expect, test } from '@playwright/test';

const modules = [
  'RPG',
  'Chatbot',
  'Storyteller',
  'Podcast',
  'Voice / TTS',
  'Voice Cloning',
  'STT',
  'Image Generation',
  'Providers',
  'Models',
  'Jobs / Runs',
  'Assets',
  'Reports',
  'Settings',
  'Diagnostics',
];

test('shared Omnix app shell exposes all module entrypoints', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Omnix' })).toBeVisible();

  for (const module of modules) {
    await expect(page.getByRole('button', { name: module })).toBeVisible();
  }
});

test('module navigation keeps features in the shared shell', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Podcast' }).click();

  await expect(page).toHaveURL(/\/podcast$/);
  await expect(page.getByRole('main').getByRole('heading', { name: 'Podcast', level: 2 })).toBeVisible();
  await expect(page.getByText('Uses the shared app shell.')).toBeVisible();
});
