import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  workers: 1,
  fullyParallel: false,
  timeout: 90000,
  expect: { timeout: 60000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.PS1_BROWSER_BASE_URL ?? 'http://127.0.0.1:5173',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    channel:
      process.env.PS1_BROWSER_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : undefined),
  },
});
