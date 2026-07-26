// seed.spec.js — CrochetTracker E2E seed exemplar
//
// Proves: full user flow across project → element → pattern → row toggle
//         survives a page reload.
//
// Seed patterns demonstrated:
//   - Unique test data (timestamp suffix)
//   - Role-based locators (getByRole, getByLabel)
//   - Wait for state (toBeVisible), not waitForTimeout
//   - Auth via storageState (playwright.config.ts)
//   - Own setup → action → assertion → cleanup
//   - One test per file

import { test, expect } from '@playwright/test';

test('row state persists after page reload', async ({ page }) => {
  const projectName = `Seed Project ${Date.now()}`;
  const elementName = 'Body';
  const pattern = 'Row 1\nRow 2\nRow 3';

  // ── Create project ──

  await page.goto('/projects/new');
  await page.getByLabel('Project name').fill(projectName);
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible();

  // ── Create element ──

  await page.getByRole('link', { name: 'Add element' }).click();
  await page.getByLabel('Element name').fill(elementName);
  await page.getByRole('button', { name: 'Add element' }).click();
  await expect(page.getByRole('heading', { name: elementName })).toBeVisible();

  // ── Paste pattern ──

  await page.getByLabel('Pattern text').fill(pattern);
  await page.getByRole('button', { name: 'Save pattern' }).click();
  await expect(page.getByText('Row 1')).toBeVisible();
  await expect(page.getByText('Row 2')).toBeVisible();
  await expect(page.getByText('Row 3')).toBeVisible();

  // ── Mark first row as in-progress ──

  await page.getByRole('button', { name: 'Mark row 1 as next state' }).click();
  await expect(page.getByText('◐')).toBeVisible();

  // ── Verify persistence after reload ──

  await page.reload();
  await expect(page.getByText('◐')).toBeVisible();

  // ── Cleanup: delete project ──

  await page.goto('/projects/');
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete project' }).click();
  await expect(page.getByText(projectName)).not.toBeVisible();
});
