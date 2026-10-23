import { defineConfig } from '@playwright/test';

// The Electron smoke suite (desktop roadmap DT-4.3): the real app on the staged runtime (desktop/staging/stage), a fresh data folder
// per run. Slow by nature: the first start runs initdb and every migration.
export default defineConfig({
  testDir: '.',
  testMatch: ['*.spec.ts'],
  timeout: 420_000,
  expect: { timeout: 30_000 },
  workers: 1,
  reporter: [['list']],
});
