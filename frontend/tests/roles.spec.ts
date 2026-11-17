import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { RunPage } from '../src/api';

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
  await page.getByRole('button', { name: 'Submit invoice', exact: true }).click();
  await expect(page).toHaveURL(/run=[a-f0-9-]{36}/);
  return new URL(page.url()).searchParams.get('run')!;
}

test.describe.serial('Private submitter and financial reviewer roles', () => {
  test.skip(!enabled, 'Use scripts.browser_checks --roles for isolated role data');
  test('submitter only sees submission tools and their own result', async ({ page }) => {
    await connect(page, values.APP_API_TOKEN);
    await expect(page.getByRole('heading', { name: 'Submit invoice', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'My invoices', exact: true })).toBeVisible();
    for (const label of ['Review queue', 'Purchase orders', 'Overview', 'Try a Scenario'])
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
      path: resolve('..', 'output', 'playwright', 'roles-submitter.png'),
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
    await expect(page.getByRole('heading', { name: 'My invoices', exact: true })).toBeVisible();
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
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
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
    await expect(page.getByRole('heading', { name: 'My invoices', exact: true })).toBeVisible();
    await expect(page.locator('tbody tr')).toHaveCount(0);
    for (const foreign of [ownRun, heldRun]) {
      const result = await page.request.get('/api/v1/runs/' + foreign, {
        headers: { Authorization: 'Bearer ' + carol },
      });
      expect(result.status()).toBe(404);
    }
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    await upload(page, 'E3-text');
    await expect(page.getByRole('heading', { name: 'Rejected', exact: true })).toBeVisible();
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
  });

  test('financial reviewer gets finance tools and resumes without an OpenAI key', async ({
    page,
  }) => {
    await connect(page, values.REVIEWER_API_TOKEN, '/');
    await expect(page).toHaveURL(/view=review/);
    const invoice = page.getByRole('link', { name: /Aster Technology Services REVIEW-001/ });
    await expect(page.getByRole('row').filter({ has: invoice })).toContainText(
      'Choose purchase order',
    );
    await invoice.click();
    await expect(page).toHaveURL(new RegExp('selected=' + heldRun));
    await expect(page.getByRole('heading', { name: 'Purchase order required' })).toBeVisible();
    await expect(page.getByRole('link', { name: /^Review queue(?: \d+)?$/ })).toBeVisible();
    for (const label of ['Purchase orders', 'Overview'])
      await expect(page.getByRole('link', { name: label, exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Submit invoice', exact: true })).toHaveCount(0);
    await expect(page.getByLabel('Your OpenAI API key')).toHaveCount(0);
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Confirm selection & resume' })).toBeDisabled();
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(page.getByRole('heading', { name: 'Purchase order required' })).toBeVisible();
      await expect(page.getByRole('img', { name: 'Invoice PDF preview, page 1' })).toHaveAttribute(
        'data-rendered',
        'true',
      );
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({
        path: resolve('..', 'output', 'playwright', `queue-detail-${width}.png`),
        fullPage: true,
      });
      if (width < 1100) {
        await page.getByRole('link', { name: 'Back to review queue', exact: true }).click();
        await expect(page.getByLabel('Review items')).toBeVisible();
        await expect(page.getByLabel('Selected invoice')).toBeHidden();
        await invoice.click();
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: 'Expand PDF', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Expanded invoice PDF' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('img')).toHaveAttribute('data-rendered', 'true');
    await expect(page.getByRole('button', { name: 'Close expanded PDF' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(page.getByRole('button', { name: 'Expand PDF', exact: true })).toBeFocused();
    await page.getByLabel('Search invoices').fill('Technology');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await invoice.click();
    await expect(page).toHaveURL(/q=Technology/);
    await page.goBack();
    await expect(page).not.toHaveURL(/selected=/);
    await page.goForward();
    await expect(page).toHaveURL(new RegExp('selected=' + heldRun));
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
      path: resolve('..', 'output', 'playwright', 'roles-reviewer.png'),
      fullPage: true,
    });
    let responseCount = 0;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/reviews/*/respond', async (route) => {
      responseCount++;
      expect(route.request().headers()['x-idempotency-key']).toBeTruthy();
      await gate;
      await route.continue();
    });
    await page.getByRole('button', { name: 'Confirm selection & resume' }).click();
    await expect(page.getByRole('button', { name: 'Recording response…' })).toBeDisabled();
    await page.keyboard.press('Enter');
    expect(responseCount).toBe(1);
    release();
    await expect(
      page.getByRole('heading', { name: 'Approved for downstream processing' }),
    ).toBeVisible();
    expect(responseCount).toBe(1);
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });
});

test.describe('Workspace entry and role navigation', () => {
  test.skip(!enabled, 'Use scripts.browser_checks --roles');
  test('queue distinguishes missing from ambiguous PO reasons', async ({ page }) => {
    // Labelled synthetic API projection only; no invoice approval or processing is fabricated.
    await page.setViewportSize({ width: 390, height: 844 });
    const records: RunPage = {
      total_count: 2,
      next_cursor: null,
      items: ['PO_MISSING', 'PO_AMBIGUOUS'].map((code, index) => ({
        run_id: `00000000-0000-4000-8000-00000000000${index + 1}`,
        created_at: '2026-11-17T10:00:00Z',
        job_state: 'WAITING_REVIEW',
        decision: 'NEEDS_REVIEW',
        invoice_number: code + '-FIXTURE',
        vendor_name: 'Synthetic queue-label fixture',
        currency: 'INR',
        total_gross: '11800.00',
        reason: 'Synthetic label test',
        reason_code: code,
        source_mode: 'MOCK_OPENAI',
      })),
    };
    await page.route('**/api/v1/runs?*', (route) => route.fulfill({ json: records }));
    await connect(page, values.REVIEWER_API_TOKEN, '/');
    const missing = page.getByRole('row').filter({ hasText: 'PO_MISSING-FIXTURE' });
    const ambiguous = page.getByRole('row').filter({ hasText: 'PO_AMBIGUOUS-FIXTURE' });
    await expect(missing.getByText('Missing PO', { exact: true })).toBeVisible();
    await expect(ambiguous.getByText('Choose purchase order', { exact: true })).toBeVisible();
    await expect(ambiguous.getByText('Missing PO', { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  });
  test('signed-out entry hides financial content, handles invalid access and verifies once', async ({
    page,
  }) => {
    await page.goto('/?view=review');
    await expect(page).toHaveTitle('Invoice operations');
    await expect(page.getByRole('heading', { name: 'Connect to your workspace' })).toBeVisible();
    await expect(page.getByRole('navigation')).toHaveCount(0);
    await expect(page.getByLabel('Search invoices')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Review queue', exact: true })).toHaveCount(0);
    await expect(page.locator('footer')).toHaveCount(0);
    await page.getByLabel('Workspace access token').fill('invalid-synthetic-token');
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Workspace access was rejected');
    await expect(page.getByLabel('Workspace access token')).toHaveAttribute('aria-invalid', 'true');
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let attempts = 0;
    await page.route('**/api/v1/access', async (route) => {
      attempts++;
      await gate;
      await route.continue();
    });
    await page.getByLabel('Workspace access token').fill(values.REVIEWER_API_TOKEN);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Verifying access…' })).toBeDisabled();
    await expect(page.getByRole('navigation')).toHaveCount(0);
    release();
    await expect(page.getByRole('heading', { name: 'Review queue', exact: true })).toBeVisible();
    expect(attempts).toBe(1);
  });

  test('submitter lands on own invoices; reviewer-only URLs remain unavailable', async ({
    page,
  }) => {
    await connect(page, bob, '/');
    await expect(page).toHaveURL(/view=history/);
    await expect(page.getByRole('heading', { name: 'My invoices', exact: true })).toBeVisible();
    await expect(page.getByRole('navigation').getByRole('link')).toHaveCount(3);
    await page.getByRole('link', { name: 'OpenAI connection', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'OpenAI connection', exact: true }),
    ).toBeVisible();
    await page.evaluate(() => {
      history.pushState(null, '', '?view=purchase-orders');
      dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(page.getByRole('alert')).toContainText('do not have access');
    await expect(page.getByRole('heading', { name: 'Purchase orders', exact: true })).toHaveCount(
      0,
    );
    await page.getByRole('link', { name: 'Return to my invoices' }).click();
    await expect(page.getByRole('heading', { name: 'My invoices', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Workspace account: Invoice submitter' }).click();
    await page.getByRole('button', { name: 'Disconnect', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Connect to your workspace' })).toBeVisible();
    await expect(page.getByRole('navigation')).toHaveCount(0);
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });

  test('empty queue stays the reviewer landing; errors and filtered empty results are distinct', async ({
    page,
  }) => {
    await connect(page, values.REVIEWER_API_TOKEN, '/');
    await expect(page).toHaveURL(/view=review/);
    await expect(page.getByRole('heading', { name: 'Your review queue is clear' })).toBeVisible();
    await page.route('**/api/v1/runs?*', (route) =>
      route.fulfill({ status: 503, json: { detail: 'Queue temporarily unavailable.' } }),
    );
    await page.getByRole('button', { name: 'Refresh review queue' }).click();
    await expect(page.getByRole('alert')).toContainText('Queue temporarily unavailable');
    await expect(page.getByRole('heading', { name: 'Your review queue is clear' })).toHaveCount(0);
    await page.unroute('**/api/v1/runs?*');
    await page.getByRole('button', { name: 'Refresh review queue' }).click();
    await expect(page.getByRole('heading', { name: 'Your review queue is clear' })).toBeVisible();
    await page.getByLabel('Search invoices').fill('nothing-to-find');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'No matching invoices', exact: true }),
    ).toBeVisible();
    await page.getByRole('link', { name: 'Clear search' }).click();
    await expect(page.getByRole('heading', { name: 'Your review queue is clear' })).toBeVisible();
  });

  test('reviewers cannot open OpenAI setup or submission through direct frontend URLs', async ({
    page,
  }) => {
    await connect(page, values.REVIEWER_API_TOKEN, '/?view=connection');
    await expect(page.getByRole('alert')).toContainText('do not have access');
    await expect(page.getByLabel('Your OpenAI API key')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'OpenAI connection', exact: true })).toHaveCount(0);
    await page.evaluate(() => {
      history.pushState(null, '', '?view=upload');
      dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(page.getByRole('alert')).toContainText('do not have access');
    await expect(page.getByLabel('Invoice PDF')).toHaveCount(0);
  });
});
