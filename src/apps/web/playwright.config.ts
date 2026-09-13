import { defineConfig, devices } from '@playwright/test';

const programData = process.env.ProgramData;
const systemDrive = process.env.SystemDrive;
if (programData && systemDrive && programData.toLowerCase().startsWith('%systemdrive%')) {
  process.env.ProgramData = programData.replace(/^%SystemDrive%/i, systemDrive);
}

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
