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
    await expect(
      page.getByText(
        'Approved for payment processing. Finance will confirm the payment schedule.',
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.getByText('Technical audit events', { exact: false })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Inspect PO ledger' })).toHaveCount(0);
    await expect(page.getByLabel('Reviewer access token')).toHaveCount(0);
    for (const label of ['PO comparison', 'Financial checks', 'Review response'])
      await expect(page.getByRole('tab', { name: label, exact: true })).toHaveCount(0);
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
    await expect(
      page.getByText('A financial reviewer will review this invoice.', { exact: true }),
    ).toBeVisible();
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
    await expect(
      page.getByText('This invoice is not approved for payment. See the reason.', {
        exact: true,
      }),
    ).toBeVisible();
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
    await page.getByRole('tab', { name: 'Invoice data', exact: true }).click();
    await expect(
      page.getByRole('region', { name: 'Invoice line items', exact: true }),
    ).toBeVisible();
    await page.getByRole('tab', { name: 'Review response', exact: true }).click();
    await expect(page.getByLabel('Review rationale', { exact: true })).toHaveValue(
      'Matched against supporting procurement record.',
    );
    await expect(page.getByRole('radio', { name: /PO-SELECT-001/ })).toBeChecked();
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
  for (const role of ['submitter', 'reviewer'] as const) {
    test(`public demo disclosure copies and fills ${role} access; server verifies the role`, async ({
      page,
      context,
    }) => {
      // Synthetic presentation response; actual role auth still uses this disposable API.
      await page.route('**/api/v1/demo-access', (route) =>
        route.fulfill({
          json: {
            roles: [
              { role: 'submitter', token: values.APP_API_TOKEN },
              { role: 'reviewer', token: values.REVIEWER_API_TOKEN },
            ],
          },
        }),
      );
      await context.grantPermissions(['clipboard-read', 'clipboard-write']);
      await page.setViewportSize({ width: role === 'submitter' ? 1440 : 390, height: 1000 });
      await page.goto('/');
      const disclosure = page.getByText('Get demo access', { exact: true });
      await expect(disclosure).toBeVisible();
      await expect(page.getByRole('button', { name: `Use ${role} token` })).toBeHidden();
      await disclosure.focus();
      await page.keyboard.press('Enter');
      await expect(
        page.getByText(/These demo identities and their activity are shared/),
      ).toBeVisible();
      await expect(page.getByText(/Connect your own OpenAI API key/)).toBeVisible();
      await expect(page.getByText(/No OpenAI API key is needed/)).toBeVisible();
      const purchaseOrderNote = page.getByRole('region', { name: 'Testing with purchase orders' });
      await expect(purchaseOrderNote).toContainText('sample invoice PDFs');
      await expect(purchaseOrderNote).toContainText('check the available POs');
      await expect(purchaseOrderNote).toContainText('Reviewers can also create a new PO');
      await expect(purchaseOrderNote).toContainText(
        'Existing POs cannot be edited or deleted here.',
      );
      const credential = role === 'submitter' ? values.APP_API_TOKEN : values.REVIEWER_API_TOKEN;
      await page.getByRole('button', { name: `Copy ${role} token` }).click();
      await expect(page.getByRole('status')).toContainText('token copied.');
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(credential);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({
        path: resolve('..', 'output', 'playwright', `demo-access-${role}.png`),
        fullPage: true,
      });
      await page.getByRole('button', { name: `Use ${role} token` }).click();
      await expect(page.getByLabel('Workspace access token')).toHaveValue(credential);
      await expect(page.getByLabel('Workspace access token')).toBeFocused();
      await expect(page.getByRole('heading', { name: 'Connect to your workspace' })).toBeVisible();
      await page.getByRole('button', { name: 'Connect', exact: true }).click();
      await expect(page).toHaveURL(role === 'submitter' ? /view=history/ : /view=review/);
      await expect(page.getByRole('link', { name: 'OpenAI connection', exact: true })).toHaveCount(
        role === 'submitter' ? 1 : 0,
      );
      await expect(page.getByRole('link', { name: 'Purchase orders', exact: true })).toHaveCount(
        role === 'reviewer' ? 1 : 0,
      );
    });
  }
  for (const failure of ['disabled', 'legacy', 'network', 'malformed']) {
    test(`manual access works when demo access is ${failure}`, async ({ page }) => {
      await page.route('**/api/v1/demo-access', (route) => {
        if (failure === 'network') return route.abort();
        if (failure === 'legacy') return route.fulfill({ status: 404, json: {} });
        return route.fulfill({
          json: { roles: failure === 'malformed' ? [{ role: 'reviewer', token: 123 }] : [] },
        });
      });
      await page.goto('/');
      await expect(page.getByText('Need an access token?', { exact: true })).toBeVisible();
      await expect(page.getByText('Get demo access', { exact: true })).toHaveCount(0);
      await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
      await page.getByRole('button', { name: 'Connect', exact: true }).click();
      await expect(page).toHaveURL(/view=history/);
    });
  }
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

  test('reviewer registers a vendor, sees blacklisted choices blocked, then records authorization before creating a PO', async ({
    page,
  }) => {
    await connect(page, values.REVIEWER_API_TOKEN, '/?view=purchase-orders');
    await page.getByRole('button', { name: 'Manage vendors', exact: true }).click();
    const manager = page.getByRole('region', { name: 'Manage vendors', exact: true });
    await expect(manager.getByRole('heading', { name: 'Manage vendors' })).toBeFocused();
    await manager.getByRole('button', { name: 'Add vendor', exact: true }).click();
    const add = manager.getByRole('form', { name: 'Add vendor', exact: true });
    await add.getByLabel('Legal vendor name', { exact: true }).fill('Custom supplies & Services');
    await add.getByLabel('Vendor status', { exact: true }).selectOption('BLACKLISTED');
    await add
      .getByLabel('Vendor authorization rationale', { exact: true })
      .fill('Synthetic supplier restriction for browser testing.');
    await add.getByRole('button', { name: 'Save vendor', exact: true }).click();
    await expect(manager.getByRole('status').filter({ hasText: 'Vendor added' })).toContainText(
      'Vendor added',
    );
    await expect(manager.getByLabel('Vendor directory')).toContainText('Blacklisted');
    await manager.getByRole('button', { name: 'Add vendor', exact: true }).click();
    await add.getByLabel('Legal vendor name', { exact: true }).fill('Custom supplies & Services');
    await add.getByLabel('Vendor status', { exact: true }).selectOption('ACTIVE');
    await add
      .getByLabel('Vendor authorization rationale', { exact: true })
      .fill('Duplicate identity must not be created.');
    await add.getByRole('button', { name: 'Save vendor', exact: true }).click();
    await expect(add.getByRole('alert')).toContainText('already exists');
    await add.getByRole('button', { name: 'Cancel vendor changes' }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: resolve('..', 'output', 'playwright', 'vendors-desktop.png'),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({
      path: resolve('..', 'output', 'playwright', 'vendors-phone.png'),
      fullPage: true,
    });
    await manager.getByRole('button', { name: 'Back to purchase orders' }).click();
    await page.getByRole('button', { name: 'Create purchase order', exact: true }).click();
    const form = page.getByRole('region', { name: 'Create purchase order', exact: true });
    await form
      .getByLabel('Vendor', { exact: true })
      .selectOption({ label: 'Custom supplies & Services · Blacklisted' });
    await expect(form.getByRole('alert')).toContainText(
      'cannot be created for a blacklisted vendor',
    );
    await expect(
      form.getByRole('button', { name: 'Create purchase order', exact: true }),
    ).toBeDisabled();
    const vendorId = await form.getByLabel('Vendor', { exact: true }).inputValue();
    const forged = await page.request.post('/api/v1/purchase-orders', {
      headers: {
        Authorization: 'Bearer ' + values.REVIEWER_API_TOKEN,
        'X-Idempotency-Key': 'browser-blacklist',
      },
      data: {
        vendor_id: vendorId,
        po_number: 'PO-BLACKLISTED',
        currency: 'INR',
        issued_at: '2026-10-01',
        cap_gross: '118',
        reason: 'Forged blocked request.',
        lines: [
          { description: 'Custom supplies', quantity: '1', unit_price: '100', tax_rate: '18' },
        ],
      },
    });
    expect(forged.status()).toBe(409);
    expect((await forged.json()).detail.message).toContain('blacklisted');
    await form.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Manage vendors', exact: true }).click();
    await manager
      .getByRole('button', { name: 'Change status for Custom supplies & Services' })
      .click();
    const change = manager.getByRole('form', { name: 'Change vendor status' });
    await change.getByLabel('Vendor status', { exact: true }).selectOption('ACTIVE');
    await change
      .getByLabel('Vendor authorization rationale', { exact: true })
      .fill('Supplier verified and authorized for synthetic purchases.');
    await change.getByRole('button', { name: 'Save status', exact: true }).click();
    await expect(
      manager.getByRole('status').filter({ hasText: 'Vendor status recorded' }),
    ).toBeVisible();
    await manager.getByRole('button', { name: 'Back to purchase orders' }).click();
    await page.getByRole('button', { name: 'Create purchase order', exact: true }).click();
    await form
      .getByLabel('Vendor', { exact: true })
      .selectOption({ label: 'Custom supplies & Services · Approved' });
    await expect(form.getByRole('alert')).toHaveCount(0);
    await form.getByLabel('PO reference', { exact: true }).fill('PO-CUSTOM-VENDOR');
    await form.getByLabel('PO issue date', { exact: true }).fill('2026-10-01');
    await form.getByLabel('Description', { exact: true }).fill('Custom supplies');
    await form.getByLabel('Quantity', { exact: true }).fill('1');
    await form.getByLabel('Net unit price (INR)', { exact: true }).fill('100');
    await form.getByLabel('Tax rate (%)', { exact: true }).fill('18');
    await form.getByRole('button', { name: 'Calculate totals', exact: true }).click();
    await expect(form.getByLabel('Calculated order totals')).toContainText('₹118.00');
    await form.getByRole('button', { name: 'Use total as spending cap' }).click();
    await expect(form.getByLabel('Gross spending cap (INR)', { exact: true })).toHaveValue(
      '118.00',
    );
    await form
      .getByLabel('Authorization rationale', { exact: true })
      .fill('Approved custom vendor and order for test.');
    await form.getByRole('button', { name: 'Create purchase order', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'PO-CUSTOM-VENDOR', exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel('Order totals including tax')).toContainText('₹118.00');
  });

  test('reviewer creates a PO once after a lost response, then a submitter invoice allocates against it', async ({
    page,
  }) => {
    await connect(page, values.REVIEWER_API_TOKEN, '/?view=purchase-orders');
    await page.getByRole('button', { name: 'Create purchase order', exact: true }).click();
    const form = page.getByRole('region', { name: 'Create purchase order', exact: true });
    await expect(form.getByRole('heading', { name: 'Create purchase order' })).toBeFocused();
    await form
      .getByLabel('Vendor', { exact: true })
      .selectOption({ label: 'Aster Office Supplies · Approved · 27ABCDE1234F1Z5' });
    await form.getByLabel('PO reference', { exact: true }).fill('PO-CREATED');
    await form.getByLabel('Gross spending cap (INR)', { exact: true }).fill('23600.00');
    await form.getByLabel('PO issue date', { exact: true }).fill('2026-10-01');
    const line = form.getByRole('region', { name: 'PO line 1', exact: true });
    await line.getByLabel('SKU (optional)', { exact: true }).fill('PAPER');
    await line.getByLabel('Description', { exact: true }).fill('Office paper');
    await line.getByLabel('Quantity', { exact: true }).fill('20');
    await line.getByLabel('Net unit price (INR)', { exact: true }).fill('1000');
    await line.getByLabel('Tax rate (%)', { exact: true }).fill('18');
    await form
      .getByLabel('Authorization rationale', { exact: true })
      .fill('Authorized synthetic office-paper purchase for reviewer-created PO testing.');
    await form.getByRole('button', { name: 'Add line', exact: true }).click();
    await form.getByRole('button', { name: 'Remove line 2', exact: true }).click();
    await form.getByRole('button', { name: 'Calculate totals', exact: true }).click();
    const totals = form.getByLabel('Calculated order totals');
    await expect(totals).toContainText('₹23,600.00');
    await expect(totals).toContainText('₹3,600.00');
    await line.getByLabel('Quantity', { exact: true }).fill('21');
    await expect(totals.getByRole('button', { name: 'Use total as spending cap' })).toHaveCount(0);
    await expect(form.getByLabel('Gross spending cap (INR)', { exact: true })).toHaveValue(
      '23600.00',
    );
    await line.getByLabel('Quantity', { exact: true }).fill('20');
    await form.getByRole('button', { name: 'Calculate totals', exact: true }).click();
    await expect(totals).toContainText('₹23,600.00');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: resolve('..', 'output', 'playwright', 'create-po-desktop.png'),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({
      path: resolve('..', 'output', 'playwright', 'create-po-phone.png'),
      fullPage: true,
    });
    const keys: string[] = [];
    let committed!: () => void, release!: () => void;
    const firstCommit = new Promise<void>((resolve) => {
      committed = resolve;
    });
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/v1/purchase-orders', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      keys.push(route.request().headers()['x-idempotency-key']);
      if (keys.length === 1) {
        const result = await route.fetch();
        expect(result.status()).toBe(201);
        committed();
        await gate;
        return route.abort('failed');
      }
      await route.continue();
    });
    await form.getByRole('button', { name: 'Create purchase order', exact: true }).click();
    await firstCommit;
    await expect(
      form.getByRole('button', { name: 'Creating purchase order…', exact: true }),
    ).toBeDisabled();
    await form
      .locator('form')
      .evaluate((element) =>
        element.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })),
      );
    expect(keys).toHaveLength(1);
    release();
    await expect(form.getByRole('alert')).toContainText('Cannot reach the server');
    await form.getByRole('button', { name: 'Create purchase order', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'PO-CREATED', exact: true })).toBeVisible();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    const poId = new URL(page.url()).searchParams.get('po')!;
    await expect(page.getByRole('region', { name: 'PO creation record' })).toContainText(
      'reviewer',
    );
    await expect(page.getByRole('region', { name: 'PO line terms' })).toContainText('Office paper');
    await expect(page.getByText('No approved invoice has consumed this PO.')).toBeVisible();
    const submitter = await page.context().newPage();
    await connect(submitter, values.APP_API_TOKEN, '/?view=upload');
    await expect(
      submitter.getByRole('button', { name: 'Create purchase order', exact: true }),
    ).toHaveCount(0);
    expect(
      (
        await submitter.request.get('/api/v1/vendors', {
          headers: { Authorization: 'Bearer ' + values.APP_API_TOKEN },
        })
      ).status(),
    ).toBe(403);
    await upload(submitter, 'PO-created-invoice');
    await expect(submitter.getByRole('heading', { name: 'Approved', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Refresh purchase orders' }).click();
    await expect(page.getByRole('link', { name: 'CREATED-001', exact: true })).toBeVisible();
    const ledger = await page.request.get('/api/v1/purchase-orders/' + poId, {
      headers: { Authorization: 'Bearer ' + values.REVIEWER_API_TOKEN },
    });
    const data = await ledger.json();
    expect(data.available_gross).toBe('11800.00');
    expect(data.allocation_count).toBe(1);
    expect(data.lines[0].committed_quantity).toBe('10.000000');
    await submitter.close();
  });
});

test('reviewer confirms demo reset, cancels safely and replays a lost response without deleting new work', async ({
  page,
}) => {
  test.skip(!enabled, 'Only the isolated role demo enables reset');
  await connect(page, values.REVIEWER_API_TOKEN, '/?view=overview');
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Reset demo data', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Reset demo workspace' });
  await expect(dialog).toBeVisible();
  const reset = dialog.getByRole('button', { name: 'Clear data & restore demo' });
  await expect(reset).toBeDisabled();
  await expect(dialog).toContainText('Custom vendors and purchase orders are removed');
  await dialog.getByRole('button', { name: 'Cancel reset' }).click();
  await expect(dialog).not.toBeVisible();
  const original = await page.request.get('/api/v1/runs', {
    headers: { Authorization: 'Bearer ' + values.REVIEWER_API_TOKEN },
  });
  expect((await original.json()).total_count).toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Reset demo data', exact: true }).click();
  await expect(dialog.getByLabel('Type RESET DEMO to clear data for everyone')).toBeEnabled();
  await dialog.getByLabel('Type RESET DEMO to clear data for everyone').fill('RESET DEMO');
  await expect(reset).toBeEnabled();
  const keys: string[] = [];
  let lose = true;
  await page.route('**/api/v1/demo/reset', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    keys.push(route.request().headers()['x-idempotency-key']);
    if (lose) {
      lose = false;
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      return route.abort();
    }
    return route.continue();
  });
  await reset.click();
  await expect(dialog.getByRole('alert')).toContainText('Cannot reach the server');
  const newer = await page.request.post('/api/v1/invoices/process', {
    headers: {
      Authorization: 'Bearer ' + values.APP_API_TOKEN,
      'X-Idempotency-Key': 'after-demo-reset',
    },
    multipart: {
      file: {
        name: 'H1.pdf',
        mimeType: 'application/pdf',
        buffer: readFileSync(resolve(directory, 'H1.pdf')),
      },
    },
  });
  expect(newer.status()).toBe(202);
  await reset.click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Demo reset complete' })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const history = await page.request.get('/api/v1/runs', {
    headers: { Authorization: 'Bearer ' + values.REVIEWER_API_TOKEN },
  });
  expect((await history.json()).total_count).toBe(1);
  const po = await page.request.get('/api/v1/purchase-orders', {
    headers: { Authorization: 'Bearer ' + values.REVIEWER_API_TOKEN },
  });
  expect((await po.json()).total_count).toBe(4);
  const submitter = await page.context().newPage();
  await connect(submitter, values.APP_API_TOKEN, '/?view=history');
  await expect(submitter.getByRole('button', { name: 'Reset demo data', exact: true })).toHaveCount(
    0,
  );
  const forbidden = await submitter.request.get('/api/v1/demo/reset', {
    headers: { Authorization: 'Bearer ' + values.APP_API_TOKEN },
  });
  expect(forbidden.status()).toBe(403);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.getByRole('button', { name: 'Reset demo data', exact: true }).click();
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await dialog.getByRole('button', { name: 'Cancel reset' }).click();
  await submitter.close();
});
