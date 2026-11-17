import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const name = process.env.PS1_BROWSER_DEMO;
if (!name) throw new Error('Use scripts.browser_checks for isolated UI tests.');
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
const key = 'synthetic-browser-reviewer-key-never-live';
const connection = {
  session_token: 'synthetic-opaque-session-capability',
  models: ['gpt-6-luna'],
  expires_at: new Date(Date.now() + 3600000).toISOString(),
};

test.beforeEach(async ({ page }) => {
  test.skip(process.env.PS1_BROWSER_LIVE === '1', 'Paid browser smoke remains H1 only');
  await page.route('**/openai/config', (route) =>
    route.fulfill({
      json: {
        mode: 'reviewer',
        mock_mode: false,
        supported_models: ['gpt-6-luna'],
        max_pdf_bytes: 12 * 1048576,
        max_pdf_pages: 5,
      },
    }),
  );
  await page.goto('/?view=upload');
  await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
  await page.getByRole('link', { name: 'OpenAI connection', exact: true }).click();
});

test('reviewer key, explicit model and disconnect; upload stopped before processing', async ({
  page,
}) => {
  let disconnected = false;
  await page.route('**/openai/sessions', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ api_key: key });
    await route.fulfill({ json: connection });
  });
  await page.route('**/openai/session', async (route) => {
    expect(route.request().headers()['x-openai-session']).toBe(connection.session_token);
    disconnected = true;
    await route.fulfill({ status: 204 });
  });
  await expect(page.getByRole('heading', { name: 'Before adding an invoice' })).toBeVisible();
  await expect(page.getByLabel('Before adding an invoice').getByRole('listitem')).toHaveCount(3);
  const fontFaces = await page.evaluate(async () => {
    const faces = await document.fonts.load('400 14px "DM Sans Variable"', 'Invoice ₹11,800.00');
    return faces.filter((face) => face.status === 'loaded').length;
  });
  expect(fontFaces).toBeGreaterThanOrEqual(2);
  await expect(page.locator('body')).toHaveCSS('font-family', /DM Sans Variable/);
  await page.screenshot({
    path: resolve('..', 'output', 'playwright', 'dm-sans-key-setup.png'),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: resolve('..', 'output', 'playwright', 'dm-sans-key-setup-mobile.png'),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('link', { name: 'Submit invoice', exact: true }).click();
  await expect(page.getByLabel('Extraction connection')).toContainText(
    'Add your OpenAI API key first',
  );
  await expect(page.getByRole('note', { name: 'Mock extraction' })).toHaveCount(0);
  await expect(page.getByText(/configured worker/i)).toHaveCount(0);
  await page.getByLabel('Invoice PDF').setInputFiles(resolve(directory, 'H1.pdf'));
  await expect(page.getByRole('button', { name: 'Submit invoice', exact: true })).toBeDisabled();
  await page.getByRole('link', { name: 'Set up connection', exact: true }).click();
  await page.getByLabel('Your OpenAI API key').fill(key);
  await page.getByRole('button', { name: 'Connect OpenAI', exact: true }).click();
  await expect(page.getByLabel('Invoice extraction model')).toHaveValue('');
  await expect(page.getByLabel('Your OpenAI API key')).toHaveCount(0);
  await page.getByRole('link', { name: 'Submit invoice', exact: true }).click();
  await expect(page.getByLabel('Extraction connection')).toContainText(
    'Select a model before adding an invoice',
  );
  await page.getByLabel('Invoice PDF').setInputFiles(resolve(directory, 'H1.pdf'));
  await expect(page.getByRole('button', { name: 'Submit invoice', exact: true })).toBeDisabled();
  await page.getByRole('link', { name: 'OpenAI connection', exact: true }).click();
  await page.getByLabel('Invoice extraction model').selectOption('gpt-6-luna');
  await page.getByRole('link', { name: 'Submit invoice', exact: true }).click();
  await expect(page.getByLabel('Extraction connection')).toContainText('OpenAI connection ready');
  await page.getByLabel('Invoice PDF').setInputFiles(resolve(directory, 'H1.pdf'));
  await page.route('**/invoices/process', async (route) => {
    expect(route.request().headers()['x-openai-session']).toBe(connection.session_token);
    expect(route.request().postData()).toContain('gpt-6-luna');
    expect(route.request().postData()).not.toContain(key);
    await route.fulfill({
      status: 400,
      json: { detail: 'UI-only test stopped before processing.' },
    });
  });
  await page.getByRole('button', { name: 'Submit invoice', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('UI-only test stopped');
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  await page.getByRole('link', { name: 'OpenAI connection', exact: true }).click();
  await page.getByRole('button', { name: 'Disconnect OpenAI', exact: true }).click();
  await expect(page.getByLabel('Your OpenAI API key')).toBeVisible();
  expect(disconnected).toBe(true);
});

test('a late connection response is revoked after leaving setup', async ({ page }) => {
  let release: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let received = false,
    revoked = false;
  await page.route('**/openai/sessions', async (route) => {
    received = true;
    await gate;
    await route.fulfill({ json: connection });
  });
  await page.route('**/openai/session', async (route) => {
    revoked = true;
    await route.fulfill({ status: 204 });
  });
  await page.getByLabel('Your OpenAI API key').fill(key);
  await page.getByRole('button', { name: 'Connect OpenAI', exact: true }).click();
  await expect.poll(() => received).toBe(true);
  await page.getByRole('link', { name: 'Invoice history', exact: true }).click();
  release?.();
  await expect.poll(() => revoked).toBe(true);
  await page.getByRole('link', { name: 'OpenAI connection', exact: true }).click();
  await expect(page.getByLabel('Your OpenAI API key')).toBeVisible();
  await expect(page.getByLabel('Invoice extraction model')).toHaveCount(0);
});

for (const mib of [4, 12]) {
  test(`upload note and file selection follow the ${mib} MiB workspace limit`, async ({ page }) => {
    const limit = mib * 1048576;
    await page.route('**/openai/config', (route) =>
      route.fulfill({
        json: { mode: 'server', supported_models: [], max_pdf_bytes: limit, max_pdf_pages: 5 },
      }),
    );
    await page.reload();
    await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    await expect(page.getByLabel('Extraction connection')).toHaveCount(0);
    await expect(page.getByRole('note', { name: 'Mock extraction' })).toHaveCount(0);
    await expect(page.getByLabel('Your OpenAI API key')).toHaveCount(0);
    await expect(page.locator('#upload-limits')).toContainText(`up to ${mib} MiB`);
    await expect(page.locator('#upload-limits')).toContainText('1–5 pages, unencrypted');
    const original = readFileSync(resolve(directory, 'H1.pdf'));
    const oversized = Buffer.alloc(limit + 1, 32);
    original.copy(oversized);
    await page
      .getByLabel('Invoice PDF')
      .setInputFiles({ name: 'over.pdf', mimeType: 'application/pdf', buffer: oversized });
    await expect(page.getByRole('alert')).toContainText(`at most ${mib} MiB`);
    await expect(page.getByRole('button', { name: 'Submit invoice', exact: true })).toBeDisabled();
    await page.getByLabel('Invoice PDF').setInputFiles({
      name: 'boundary.pdf',
      mimeType: 'application/pdf',
      buffer: oversized.subarray(0, limit),
    });
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Submit invoice', exact: true })).toBeEnabled();
    // Only selection is checked here; no POST, extraction or provider charge is started.
  });
}

for (const mockMode of [true, false, undefined]) {
  test(`mock instructions require explicit true metadata (${String(mockMode)})`, async ({
    page,
  }) => {
    await page.route('**/openai/config', (route) =>
      route.fulfill({
        json: {
          mode: 'server',
          supported_models: [],
          max_pdf_bytes: 12 * 1048576,
          max_pdf_pages: 5,
          ...(mockMode === undefined ? {} : { mock_mode: mockMode }),
        },
      }),
    );
    await page.reload();
    await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
    await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
    await expect(page.getByRole('note', { name: 'Mock extraction' })).toHaveCount(
      mockMode === true ? 1 : 0,
    );
    await expect(page.getByText(/configured worker/i)).toHaveCount(0);
    await page.getByLabel('Invoice PDF').setInputFiles(resolve(directory, 'H1.pdf'));
    await expect(page.getByRole('button', { name: 'Submit invoice', exact: true })).toBeEnabled();
    // Presentation-only metadata cases: do not submit a document or change the backend processor.
    if (mockMode === false)
      await page.screenshot({
        path: resolve('..', 'output', 'playwright', 'normal-upload-copy.png'),
        fullPage: true,
      });
  });
}

test('malformed mock metadata leaves upload configuration unavailable', async ({ page }) => {
  await page.route('**/openai/config', (route) =>
    route.fulfill({
      json: {
        mode: 'server',
        mock_mode: 'true',
        supported_models: [],
        max_pdf_bytes: 12 * 1048576,
        max_pdf_pages: 5,
      },
    }),
  );
  await page.reload();
  await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
  await page.getByRole('link', { name: 'Submit invoice', exact: true }).first().click();
  await expect(
    page.getByText('Upload configuration could not be loaded. Refresh to try again.'),
  ).toBeVisible();
  await expect(page.getByLabel('Invoice PDF')).toBeDisabled();
  await expect(page.getByRole('note', { name: 'Mock extraction' })).toHaveCount(0);
});
