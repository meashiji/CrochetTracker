// row-state-persistence.spec.js
//
// Risk: #1 — Row-mark write silently fails; user re-opens to find stale state.
//   (test-plan.md §2, Risk #1: "HTMX POST returns an error, UI updates,
//    DB doesn't; user re-opens to find stale state")
//
// Proves: toggling a row's state, then reloading the page, still shows
//   the updated state — the write reached the DB and survives a fresh read.
//
// Seed: seed.spec.js (role-based locators, unique data, storageState auth)

import { test, expect } from '@playwright/test';

test('row state persists after page reload', async ({ page }) => {
  const projectName = `Risk1 Project ${Date.now()}`;
  const pattern = 'Row 1\nRow 2\nRow 3';

  // ── Setup: create project + element + pattern via UI ──

  await page.goto('/projects/new');
  await page.getByLabel('Project name').fill(projectName);
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: projectName })).toBeVisible();

  await page.getByRole('link', { name: 'Add element' }).click();
  await page.getByLabel('Element name').fill('Body');
  await page.getByRole('button', { name: 'Add element' }).click();

  await page.getByLabel('Pattern text').fill(pattern);
  await page.getByRole('button', { name: 'Save pattern' }).click();
  await expect(page.getByRole('button', { name: 'Mark row 1 as next state' })).toBeVisible();

  // ── Act: mark first row as in-progress ──

  await page.getByRole('button', { name: 'Mark row 1 as next state' }).click();
  await expect(page.getByText('◐')).toBeVisible();

  // ── Assert: state survives a page reload ──

  await page.reload();
  await expect(page.getByText('◐')).toBeVisible();

  // ── Cleanup: delete project ──

  await page.goto('/projects/');
  page.on('dialog', (dialog) => dialog.accept());
  await page
    .getByRole('listitem')
    .filter({ hasText: projectName })
    .getByLabel('Delete project')
    .click();
  await expect(page.getByText(projectName)).not.toBeVisible();
});
