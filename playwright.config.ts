import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 30_000,
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:8000',
    headless: true,
    storageState: 'auth.json',
  },
  webServer: {
    command: 'uv run uvicorn app.main:app --port 8000',
    port: 8000,
    reuseExistingServer: !process.env.CI,
  },
});
