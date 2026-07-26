// auth.setup.js — Logs in via API and saves storage state for all E2E tests.

import { test as setup } from '@playwright/test';

const BASE = process.env.BASE_URL ?? 'http://localhost:8000';
const authFile = 'tests/e2e/.auth/user.json';

setup('authenticate', async ({ request }) => {
  await request.post(`${BASE}/auth/signup`, {
    form: { email: 'e2e@test.example', password: 'testpass123' },
  });
  await request.post(`${BASE}/auth/login`, {
    form: { email: 'e2e@test.example', password: 'testpass123' },
  });

  // Save signed-in state (cookies) for other tests to reuse
  await request.storageState({ path: authFile });
});
