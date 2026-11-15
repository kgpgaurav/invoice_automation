import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const enabled = process.env.PS1_BROWSER_ROLES === '1';
const name = process.env.PS1_BROWSER_DEMO;
if (!name) throw new Error('Use scripts.browser_checks.');
const directory = resolve('..', '.local', 'demos', name);
const values = Object.fromEntries(
  readFileSync(resolve(directory, 'backend.env'), 'utf8')
    .trim()
    .split(/\r?\n/)
    .map((line) => {
      const at = line.indexOf('=');
      return [line.slice(0, at), line.slice(at + 1)];
    }),
);
const bob = enabled ? JSON.parse(values.SUBMITTER_API_TOKENS)['submitter-b'] : '';
const carol = enabled ? JSON.parse(values.SUBMITTER_API_TOKENS)['submitter-c'] : '';
let ownRun = '',
  heldRun = '';

async function connect(page: Page, token: string, url = '/?view=upload') {
  await page.goto(url);
  await page.getByLabel('Workspace access token').fill(token);
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
}
async function upload(page: Page, file: string) {
  await page.getByLabel('Invoice PDF').setInputFiles(resolve(directory, file + '.pdf'));
  await page.getByRole('button', { name: 'Process invoice', exact: true }).click();
  await expect(page).toHaveURL(/run=[a-f0-9-]{36}/);
  return new URL(page.url()).searchParams.get('run')!;
}

test.describe.serial('Private submitter and financial reviewer roles', () => {
  test.skip(!enabled, 'Use scripts.browser_checks --roles for isolated role data');
  test('submitter only sees submission tools and their own result', async ({ page }) => {
    await connect(page, values.APP_API_TOKEN);
    await expect(page.getByRole('heading', { name: 'Process Invoice', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'My Invoices', exact: true })).toBeVisible();
    for (const label of ['Review Queue', 'Purchase Orders', 'Overview', 'Try a Scenario'])
      await expect(page.getByRole('link', { name: label, exact: true })).toHaveCount(0);
    ownRun = await upload(page, 'H1');
    await expect(page.getByRole('heading', { name: 'Approved', exact: true })).toBeVisible();
    await expect(page.getByText('Technical audit events', { exact: false })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Inspect PO ledger' })).toHaveCount(0);
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
    await expect(page.getByRole('img', { name: 'Invoice PDF preview, page 1' })).toHaveAttribute(
      'data-rendered',
      'true',
    );
    await page.evaluate(() => {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: resolve('..', 'docs', 'screenshots', 'roles-submitter.png'),
      fullPage: true,
    });
    const forbidden = await page.request.get('/api/v1/purchase-orders', {
      headers: { Authorization: 'Bearer ' + values.APP_API_TOKEN },
    });
    expect(forbidden.status()).toBe(403);
    await page.setViewportSize({ width: 390, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  });

  test('another submitter cannot see the first invoice and cannot review their own hold', async ({
    page,
  }) => {
    await connect(page, bob, '/?view=history');
    await expect(page.getByRole('heading', { name: 'My Invoices', exact: true })).toBeVisible();
    await expect(page.getByText('INV-001', { exact: true })).toHaveCount(0);
    expect(
      (
        await page.request.get('/api/v1/runs/' + ownRun, {
          headers: { Authorization: 'Bearer ' + bob },
        })
      ).status(),
    ).toBe(404);
    await connect(page, bob, '/?view=purchase-orders');
    await expect(page.getByRole('alert')).toContainText('do not have access');
    await page.getByRole('link', { name: 'Process Invoice', exact: true }).first().click();
    heldRun = await upload(page, 'E2');
    await expect(page.getByRole('heading', { name: 'Needs review', exact: true })).toBeVisible();
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
    await expect(
      page.getByRole('heading', { name: 'Choose the supporting purchase order' }),
    ).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Confirm selection & resume' })).toHaveCount(0);
  });

  test('third static submitter has separate history and cannot duplicate an approval', async ({
    page,
  }) => {
    await connect(page, carol, '/?view=history');
    await expect(page.getByRole('heading', { name: 'My Invoices', exact: true })).toBeVisible();
    await expect(page.locator('tbody tr')).toHaveCount(0);
    for (const foreign of [ownRun, heldRun]) {
      const result = await page.request.get('/api/v1/runs/' + foreign, {
        headers: { Authorization: 'Bearer ' + carol },
      });
      expect(result.status()).toBe(404);
    }
    await page.getByRole('link', { name: 'Process Invoice', exact: true }).first().click();
    await upload(page, 'E3-text');
    await expect(page.getByRole('heading', { name: 'Rejected', exact: true })).toBeVisible();
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
  });

  test('financial reviewer gets finance tools and resumes without an OpenAI key', async ({
    page,
  }) => {
    await connect(page, values.REVIEWER_API_TOKEN, '/?run=' + heldRun);
    await expect(
      page.getByRole('heading', { name: 'Choose the supporting purchase order' }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: /^Review Queue(?: \d+)?$/ })).toBeVisible();
    for (const label of ['Purchase Orders', 'Overview'])
      await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Process Invoice', exact: true })).toHaveCount(0);
    await expect(page.getByLabel('Your OpenAI API key')).toHaveCount(0);
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
    await page.getByLabel('Action', { exact: true }).selectOption('SELECT_PO');
    await page.getByRole('radio', { name: /PO-SELECT-001/ }).check();
    await page
      .getByLabel('Review rationale', { exact: true })
      .fill('Matched against supporting procurement record.');
    await expect(page.getByRole('img', { name: 'Invoice PDF preview, page 1' })).toHaveAttribute(
      'data-rendered',
      'true',
    );
    await page.evaluate(() => {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: resolve('..', 'docs', 'screenshots', 'roles-reviewer.png'),
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Confirm selection & resume' }).click();
    await expect(
      page.getByRole('heading', { name: 'Approved for downstream processing' }),
    ).toBeVisible();
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });
});
