import { test, expect, type Page } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const name = process.env.PS1_BROWSER_DEMO;
if (!name) throw new Error('Use the scoped browser-test runner; PS1_BROWSER_DEMO is required.');
const directory = resolve('..', '.local', 'demos', name);
const values = Object.fromEntries(
  readFileSync(resolve(directory, 'backend.env'), 'utf8')
    .trim()
    .split(/\r?\n/)
    .map((line) => {
      const i = line.indexOf('=');
      return [line.slice(0, i), line.slice(i + 1)];
    }),
);
const live = process.env.PS1_BROWSER_LIVE === '1';
const shots = resolve('..', 'output', 'playwright', 'regressions');
let cleanRun = '';
let heldRun = '';
let selectedRun = '';
let ledgerPO = '';
mkdirSync(shots, { recursive: true });

async function capture(page: Page, options: Parameters<Page['screenshot']>[0]) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  await page.screenshot(options);
}

async function connect(page: Page) {
  await page.goto('/?view=history');
  await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Invoice history', exact: true })).toBeVisible();
}
async function upload(page: Page, fixture: string) {
  await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
  await page.getByLabel('Invoice PDF').setInputFiles(resolve(directory, fixture + '.pdf'));
  await page.getByRole('button', { name: 'Submit invoice', exact: true }).click();
  await expect(page).toHaveURL(/run=[a-f0-9-]{36}/);
}
async function approved(page: Page) {
  await expect(
    page.getByRole('heading', { name: 'Approved for downstream processing', exact: true }),
  ).toBeVisible();
}

test.describe.serial('PDF-to-decision workspace', () => {
  test('H1 through upload, API, separate worker and database', async ({ page }) => {
    await connect(page);
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    await capture(page, {
      path: resolve(shots, live ? 'phase1-live-upload.png' : 'phase1-upload.png'),
      fullPage: true,
    });
    await page.getByLabel('Invoice PDF').setInputFiles({
      name: 'bad.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('invalid'),
    });
    await expect(page.getByRole('alert')).toContainText('PDF signature');
    await upload(page, 'H1');
    await approved(page);
    await expect(page.getByRole('heading', { name: 'Processing timeline' })).toBeVisible();
    await expect(page.locator('.rule-check.passed')).toHaveCount(7);
    cleanRun = new URL(page.url()).searchParams.get('run')!;
    await page.getByText('Extracted details', { exact: true }).click();
    await page.getByRole('button', { name: 'View Invoice Number source, page 1' }).click();
    await expect(page.getByRole('status')).toContainText('Showing page 1');
    await expect(page.getByRole('img', { name: 'Invoice PDF preview, page 1' })).toHaveAttribute(
      'data-rendered',
      'true',
    );
    await expect(page.getByRole('link', { name: 'Open PDF' })).toHaveAttribute('href', /^blob:/);
    if (!live) await expect(page.getByText('MOCKED EXTRACTION', { exact: true })).toBeVisible();
    else await expect(page.getByText('MOCKED EXTRACTION', { exact: true })).toHaveCount(0);
    await capture(page, {
      path: resolve(shots, live ? 'phase1-live-h1.png' : 'phase1-mock-h1.png'),
      fullPage: true,
    });
    const id = new URL(page.url()).searchParams.get('run');
    const result = await page.request.get(`/api/v1/runs/${id}`, {
      headers: { Authorization: 'Bearer ' + values.APP_API_TOKEN },
    });
    const detail = await result.json();
    expect(detail.approved_gross).toBe('11800.00');
    await page.getByText(/^Technical audit events/).click();
    await expect(page.getByText('Run Completed', { exact: false })).toBeVisible();
    const count = await page.locator('.timeline-event').count();
    const reconnect = page.waitForResponse(
      (response) => response.url().includes('/events/stream?') && response.status() === 200,
    );
    await page.getByRole('button', { name: 'Reconnect live stream' }).click();
    await reconnect;
    expect(await page.locator('.timeline-event').count()).toBe(count);
    if (live) {
      expect(detail.usage.recorded_attempts).toBeGreaterThan(0);
      expect(detail.source_mode).toBe('LIVE_OPENAI');
    }
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Connect to your workspace' })).toBeVisible();
    expect(new URL(page.url()).searchParams.get('run')).toBe(id);
  });

  test('E2 offered PO selection, failed reviewer auth and same-key retry/resume', async ({
    page,
  }) => {
    test.skip(live, 'Only explicit H1 incurs live API cost');
    await connect(page);
    await upload(page, 'E2');
    await expect(
      page.getByRole('heading', { name: 'Choose the supporting purchase order' }),
    ).toBeVisible();
    await page.getByLabel('Action', { exact: true }).selectOption('SELECT_PO');
    await page.getByRole('radio', { name: /PO-SELECT-001/ }).check();
    await page
      .getByLabel('Review rationale', { exact: true })
      .fill('Matched the supporting PO-SELECT-001 procurement record.');
    await page.getByLabel('Reviewer access token').fill(values.APP_API_TOKEN);
    const keys: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/respond')) keys.push(r.headers()['x-idempotency-key']);
    });
    await page.getByRole('button', { name: 'Confirm selection & resume' }).click();
    await expect(page.getByRole('alert')).toContainText('Reviewer access was rejected');
    await page.getByLabel('Reviewer access token').fill(values.REVIEWER_API_TOKEN);
    await capture(page, { path: resolve(shots, 'phase1-mock-review.png'), fullPage: true });
    for (const width of [768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(page.getByRole('radio', { name: /PO-SELECT-001/ })).toBeChecked();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await capture(page, {
        path: resolve(shots, `phase1-po-selection-${width}.png`),
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: 'Confirm selection & resume' }).click();
    await approved(page);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    selectedRun = new URL(page.url()).searchParams.get('run')!;
    await page.getByText(/^Technical audit events/).click();
    await expect(page.getByText('Review Resolved', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });

  test('E1 partial accumulation holds the INR 5000 excess; polling fallback', async ({ page }) => {
    test.skip(live, 'Live smoke scope is H1 only');
    await connect(page);
    await page.route('**/events/stream?*', (route) => route.abort());
    await upload(page, 'E1-prior');
    await approved(page);
    await upload(page, 'E1');
    await expect(page.getByRole('heading', { name: 'Review required' })).toBeVisible();
    heldRun = new URL(page.url()).searchParams.get('run')!;
    await expect(page.getByLabel('Balance at assessment')).toContainText('₹1,00,000.00');
    await expect(page.getByLabel('Balance at assessment')).toContainText('₹70,000.00');
    await expect(page.getByLabel('Balance at assessment')).toContainText('₹30,000.00');
    await expect(page.getByLabel('Balance at assessment')).toContainText('₹35,000.00');
    await expect(page.getByLabel('Balance at assessment')).toContainText('₹5,000.00');
    await expect(page.locator('[data-rule=PO_BALANCE] .check-status')).toHaveText(
      'Requires review',
    );
    await expect(page.locator('.rule-check.passed')).toHaveCount(0);
    await expect(page.getByText('Polling fallback · every 2 seconds')).toBeVisible();
    await expect(page.getByRole('option', { name: 'Select PO & resume' })).toHaveCount(0);
    await capture(page, { path: resolve(shots, 'phase1-mock-overrun.png'), fullPage: true });
  });

  test('E3 normalized text duplicate rejects, E4 bank mismatch reviews; scan stays conservative', async ({
    page,
  }) => {
    test.skip(live, 'Live smoke scope is H1 only');
    await connect(page);
    await upload(page, 'E3-text');
    await expect(
      page.getByRole('heading', { name: 'Invoice rejected', exact: true }),
    ).toBeVisible();
    await expect(page.locator('.decision-banner')).toContainText('already approved');
    await upload(page, 'E4');
    await expect(page.getByRole('heading', { name: 'Review required' })).toBeVisible();
    await expect(page.locator('.decision-banner')).toContainText(/bank details/i);
    await upload(page, 'E3-scan');
    await expect(page.getByRole('heading', { name: 'Review required' })).toBeVisible();
    await expect(page.locator('.findings')).toContainText('no local text corroboration');
  });

  test('401, 404, 409 and network failures stay clear and retry safely', async ({ page }) => {
    test.skip(live, 'Live smoke scope is H1 only');
    await page.goto('/?view=history');
    await page.getByLabel('Workspace access token').fill('invalid-workspace-token');
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Workspace access was rejected');
    await page.goto('/?run=00000000-0000-0000-0000-000000000000');
    await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('no longer available');
    await connect(page);
    await upload(page, 'E1');
    await expect(page.getByRole('heading', { name: 'Resolve this exception' })).toBeVisible();
    await page.getByLabel('Action', { exact: true }).selectOption('REQUEST_INFO');
    await page.getByLabel('Reviewer access token').fill(values.REVIEWER_API_TOKEN);
    await page
      .getByLabel('Review rationale', { exact: true })
      .fill('Request supporting amended procurement source.');
    const keys: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/respond')) keys.push(r.headers()['x-idempotency-key']);
    });
    await page.route(
      '**/reviews/*/respond',
      (route) =>
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: '{"detail":"Injected busy review"}',
        }),
      { times: 1 },
    );
    await page.getByRole('button', { name: 'Submit review response' }).click();
    await expect(page.getByRole('alert')).toContainText('record changed');
    await page.route('**/reviews/*/respond', (route) => route.abort(), { times: 1 });
    await page.getByRole('button', { name: 'Submit review response' }).click();
    await expect(page.getByRole('alert')).toContainText('Cannot reach the server');
    await page.getByRole('button', { name: 'Submit review response' }).click();
    await expect(
      page.getByRole('heading', { name: 'Source information requested', exact: true }),
    ).toBeVisible();
    expect(new Set(keys).size).toBe(1);
  });

  test('history filters, cursor pagination and narrow-screen layout', async ({ page }) => {
    test.skip(live, 'Live smoke scope is H1 only');
    await connect(page);
    for (let i = 0; i < 5; i++)
      await page.request.post('/api/v1/invoices/process', {
        headers: {
          Authorization: 'Bearer ' + values.APP_API_TOKEN,
          'X-Idempotency-Key': `pagination-${i}`,
        },
        multipart: {
          file: {
            name: 'invoice.pdf',
            mimeType: 'application/pdf',
            buffer: readFileSync(resolve(directory, 'H1.pdf')),
          },
        },
      });
    await page.getByRole('button', { name: 'Refresh history' }).click();
    await expect(page.getByRole('button', { name: /Next/ })).toBeEnabled();
    await capture(page, { path: resolve(shots, 'phase1-mock-dashboard.png'), fullPage: true });
    await page.getByRole('button', { name: /Next/ }).click();
    await expect(page.getByRole('button', { name: 'Previous' })).toBeEnabled();
    await page.getByLabel('Decision', { exact: true }).selectOption('NEEDS_REVIEW');
    await expect(page.locator('tbody tr')).toHaveCount(3);
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, { path: resolve(shots, 'phase1-history-mobile.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  });

  test('review-first landing, literal search, scenario limits and PO ledger', async ({ page }) => {
    test.skip(live, 'Phase 1 routine browser suite is mocked extraction only');
    await page.goto('/');
    await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await expect(page).toHaveURL(/view=review/);
    await expect(page.getByRole('heading', { name: 'Review queue', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Review invoice' }).first()).toBeVisible();
    await capture(page, { path: resolve(shots, 'phase1-review-queue.png'), fullPage: true });
    await page.getByLabel('Search invoices').fill('Industrial');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.locator('tbody tr')).toHaveCount(1);
    await page.getByRole('link', { name: 'Purchase orders', exact: true }).click();
    await page.getByRole('link', { name: 'PO-PARTIAL', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'PO-PARTIAL', exact: true })).toBeVisible();
    ledgerPO = new URL(page.url()).searchParams.get('po')!;
    await expect(
      page
        .getByRole('region', { name: 'Purchase order balances' })
        .getByText('₹1,00,000.00', { exact: true }),
    ).toBeVisible();
    await expect(page.getByText('₹30,000.00', { exact: true })).toBeVisible();
    const allocations = page.getByRole('region', { name: 'Approved invoice allocations' });
    await expect(allocations.locator('tbody tr')).toHaveCount(1);
    await expect(allocations.locator('tbody')).toContainText('₹70,000.00');
    await capture(page, { path: resolve(shots, 'phase1-po-ledger.png'), fullPage: true });
    await page.getByRole('link', { name: 'View invoice', exact: false }).click();
    await approved(page);
    await page.getByRole('link', { name: 'Overview', exact: true }).click();
    await expect(page.getByText('Straight-through processing rate', { exact: true })).toBeVisible();
    await expect(page.getByText('DEMO DATA INCLUDED', { exact: true })).toBeVisible();
    await capture(page, { path: resolve(shots, 'phase1-overview.png'), fullPage: true });
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    await page.getByRole('link', { name: 'Try a scenario', exact: true }).last().click();
    await expect(page.getByRole('button', { name: 'Use local PDF' })).toHaveCount(5);
    await expect(page.getByRole('button', { name: 'Fixture not available' })).toBeDisabled();
    await expect(page.getByText(/not independently repeatable yet/)).toBeVisible();
    await capture(page, { path: resolve(shots, 'phase1-scenarios.png'), fullPage: true });
  });

  test('desktop, tablet and mobile layouts preserve the document and financial context', async ({
    page,
  }) => {
    test.skip(live, 'No additional paid model calls in Phase 1');
    await connect(page);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      for (const [route, name] of [
        ['?run=' + cleanRun, 'approved'],
        ['?run=' + heldRun, 'overrun'],
        ['?run=' + selectedRun, 'resumed'],
        ['?view=review', 'queue'],
        ['?view=upload', 'upload'],
        ['?view=purchase-orders', 'purchase-orders'],
        ['?po=' + ledgerPO, 'po-ledger'],
      ] as const) {
        await page.getByRole('link', { name: 'Invoice history', exact: true }).focus();
        await page.evaluate((path) => {
          history.pushState(null, '', path);
          dispatchEvent(new PopStateEvent('popstate'));
        }, route);
        if (route.includes('run=')) {
          await expect(
            page.getByRole('heading', { name: 'Financial rule checklist' }),
          ).toBeVisible();
          await expect(
            page.getByRole('img', { name: 'Invoice PDF preview, page 1' }),
          ).toHaveAttribute('data-rendered', 'true');
        } else if (name === 'upload') await expect(page.getByLabel('Invoice PDF')).toBeAttached();
        else await expect(page.locator('tbody tr').first()).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
          true,
        );
        await capture(page, {
          path: resolve(shots, `phase1-${name}-${width}.png`),
          fullPage: true,
        });
      }
      await page.getByRole('link', { name: 'Review queue', exact: false }).first().focus();
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/view=review/);
    }
  });

  test('keyboard landmarks, labels, focus, contrast and readable read failures', async ({
    page,
  }) => {
    test.skip(live, 'Routine browser accessibility checks incur no model calls');
    await page.goto('/?view=upload');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('main')).toBeFocused();
    await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByRole('link', { name: 'Purchase orders', exact: true }).focus();
    const outline = await page
      .getByRole('link', { name: 'Purchase orders', exact: true })
      .evaluate((el) => getComputedStyle(el).outlineWidth);
    expect(parseFloat(outline)).toBeGreaterThanOrEqual(3);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Purchase orders', exact: true })).toBeVisible();
    const contrasts = await page.evaluate(() => {
      const css = getComputedStyle(document.documentElement);
      const luminance = (hex: string) => {
        const rgb = hex
          .trim()
          .replace('#', '')
          .match(/.{2}/g)!
          .map((v) => parseInt(v, 16) / 255)
          .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
      };
      return [
        ['--text', '--background'],
        ['--muted', '--background'],
        ['--approved', '--approved-bg'],
        ['--review', '--review-bg'],
        ['--rejected', '--rejected-bg'],
        ['--failed', '--failed-bg'],
        ['--brand-text', '--surface'],
      ].map(([a, b]) => {
        const x = luminance(css.getPropertyValue(a)),
          y = luminance(css.getPropertyValue(b));
        return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
      });
    });
    for (const ratio of contrasts) expect(ratio).toBeGreaterThanOrEqual(4.5);
    await page.route('**/api/v1/purchase-orders?*', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: '{"detail":"Purchase orders are temporarily unavailable."}',
      }),
    );
    await page.getByRole('button', { name: 'Refresh purchase orders' }).click();
    await expect(page.getByRole('alert')).toContainText('temporarily unavailable');
    await page.unroute('**/api/v1/purchase-orders?*');
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(
      '**/api/v1/purchase-orders?*',
      async (route) => {
        await gate;
        await route.continue();
      },
      { times: 1 },
    );
    await page.getByRole('button', { name: 'Refresh purchase orders' }).click();
    await expect(page.getByRole('status')).toContainText('Loading purchase orders');
    release();
    await expect(page.locator('tbody tr').first()).toBeVisible();
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    const unlabelled = await page
      .locator('input,select,textarea')
      .evaluateAll(
        (inputs) =>
          inputs.filter(
            (input) =>
              !input.getAttribute('aria-label') && !(input as HTMLInputElement).labels?.length,
          ).length,
      );
    expect(unlabelled).toBe(0);
    await page.getByRole('link', { name: 'Invoice history', exact: true }).click();
    await page.getByLabel('Search invoices').fill('not-an-existing-invoice');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'No matching invoices.' })).toBeVisible();
  });

  test('an unregistered mock PDF reports its actual cause without pretending to classify it', async ({
    page,
  }) => {
    test.skip(live, 'No personal documents or new live calls');
    await connect(page);
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    await expect(page.getByText(/Mock workspaces accept only/)).toBeVisible();
    await page.getByLabel('Invoice PDF').setInputFiles({
      name: 'unregistered-synthetic.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.concat([
        readFileSync(resolve(directory, 'H1.pdf')),
        Buffer.from('\n% unregistered synthetic test variant\n'),
      ]),
    });
    await page.getByRole('button', { name: 'Submit invoice', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Processing could not complete', exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel('Financial decision')).toContainText(
      'does not match a prepared mock-demo invoice',
    );
    await expect(page.getByLabel('Financial decision')).toContainText(
      'not analyzed by an external model',
    );
    await expect(page.locator('.rule-check.passed')).toHaveCount(0);
    const ident = new URL(page.url()).searchParams.get('run');
    const response = await page.request.get('/api/v1/runs/' + ident, {
      headers: { Authorization: 'Bearer ' + values.APP_API_TOKEN },
    });
    const detail = await response.json();
    expect(detail.processing_failure.code).toBe('MOCK_FIXTURE_NOT_FOUND');
    expect(detail.usage.recorded_attempts).toBe(0);
    expect(detail.usage.reserved_attempts).toBe(0);
    expect(detail.decision).toBeNull();
    expect(detail.approved_gross).toBeNull();
    await capture(page, { path: resolve(shots, 'mock-unsupported-pdf.png'), fullPage: true });
    await page.getByRole('link', { name: 'Invoice history', exact: true }).click();
    await expect(page.locator('tbody tr').first()).toContainText(
      'does not match a prepared mock-demo invoice',
    );
  });
});
