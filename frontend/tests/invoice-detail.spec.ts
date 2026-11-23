import { test, expect, type Page, type Route } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Run, RunEvent, Review } from '../src/api';
import type { Field } from '../src/invoicePresentation';
import { relativeDifference } from '../src/invoicePresentation';

// Explicit UI-only API projections. These tests never submit an invoice, post an
// approval, change financial data or call a provider. Real execution is covered
// separately by workflow.spec.ts and roles.spec.ts using the durable mock worker.
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
const id = '10000000-0000-4000-8000-000000000001';
const reviewId = '10000000-0000-4000-8000-000000000002';
const at = '2026-11-20T08:00:00Z';
const shots = resolve('..', 'output', 'playwright', 'invoice-detail');
mkdirSync(shots, { recursive: true });

function field(name: string, value: string | null, extra: Partial<Field> = {}): Field {
  return {
    field: name,
    value,
    verification: value == null ? 'missing' : 'verified',
    pages: value == null ? [] : [1],
    required_for_approval: !['vendor_tax_id', 'sku', 'po_line_no'].includes(
      name.split('.').at(-1)!,
    ),
    origin: value == null ? null : 'printed',
    original_value: value,
    calculation: null,
    ...extra,
  };
}
function fixture(): Run {
  const lines = [
    ['Office paper', 'PAPER', '2', '500.0000', '1000.00', '180.00', '1180.00'],
    ['Storage boxes', 'BOX', '1', '750.0000', '750.00', '135.00', '885.00'],
    ['Printer cables', null, '4', '125.0000', '500.00', '90.00', '590.00'],
  ];
  const fields = [
    field('vendor_name', 'Synthetic Office Supplies'),
    field('vendor_tax_id', '27ABCDE1234F1Z5'),
    field('invoice_number', 'UI-INV-001'),
    field('invoice_date', '2026-11-20'),
    field('po_reference', 'PO-UI-001'),
    field('currency', 'INR'),
    field('subtotal_net', '2250.00'),
    field('tax_total', '405.00', {
      origin: 'derived',
      calculation: '180.00 + 135.00 + 90.00 = 405.00',
      original_value: null,
    }),
    field('total_gross', '2655.00'),
    field('tax_mode', 'EXCLUSIVE'),
    ...lines.flatMap((line, index) => {
      const p = 'lines.' + (index + 1) + '.';
      return [
        field(p + 'description', line[0]),
        field(p + 'sku', line[1]),
        field(p + 'po_line_no', null),
        field(p + 'quantity', line[2]),
        field(p + 'unit_price', line[3]),
        field(p + 'price_basis', 'NET'),
        field(p + 'tax_rate', '18'),
        field(p + 'net_amount', line[4]),
        field(p + 'tax_amount', line[5]),
        field(p + 'gross_amount', line[6]),
      ];
    }),
  ];
  return {
    run_id: id,
    thread_id: id,
    created_at: at,
    updated_at: at,
    replay_mode: false,
    implementation_notice: 'Explicit UI-test API projection, not an executed decision.',
    job_state: 'COMPLETED',
    decision: 'APPROVED',
    decision_reason: 'Recorded synthetic UI projection: approved for downstream processing.',
    source_mode: 'MOCK_OPENAI',
    policy_version: 'policy-1.1-demo',
    model_id: 'fixture-extraction',
    reason_code: 'VALIDATED',
    error_code: null,
    invoice_number: 'UI-INV-001',
    invoice_currency: 'INR',
    invoice_total: '2655.00',
    fields,
    verification_findings: [],
    vendor: { vendor_id: id, name: 'Synthetic Office Supplies', status: 'ACTIVE' },
    purchase_order: {
      po_id: id,
      po_number: 'PO-UI-001',
      status: 'OPEN',
      currency: 'INR',
      cap_gross: '10000.00',
      committed_gross: '2655.00',
      remaining_gross: '7345.00',
      relationship: 'APPROVED_ALLOCATION',
      balance_label: 'Current master',
    },
    decision_observations: null,
    approved_gross: '2655.00',
    review_request_id: null,
    stages: [
      'DOCUMENT_LOADING',
      'EXTRACTION',
      'EVIDENCE_VERIFICATION',
      'MATCHING',
      'FINALIZATION',
    ].map((name) => ({
      key: name,
      name,
      operation: name,
      status: 'finished',
      started_at: at,
      finished_at: at,
      elapsed_ms: 100,
    })),
    processing_ms: 500,
    processing_time_status: 'measured',
    usage: {
      recorded_attempts: 0,
      reserved_attempts: 1,
      input_tokens: null,
      output_tokens: null,
      estimated_cost_usd: null,
      actual_billed_cost_usd: null,
      cost_status: 'not_applicable',
      rate_sources: [],
    },
    checks: [
      ['REQUIRED_FIELDS', 'Essential invoice fields'],
      ['SOURCE_EVIDENCE', 'Fields supported by the PDF'],
      ['VENDOR_IDENTITY', 'Supplier identity matches the vendor record'],
      ['PO_PRICE', 'Unit prices match the PO'],
    ].map(([rule_id, title]) => ({
      rule_id,
      title,
      status: 'passed',
      description: 'Recorded result in a synthetic UI projection.',
      provenance: 'RECORDED_ASSESSMENT',
      finding_code: null,
      assessment_revision: 1,
      pages: [1],
    })),
    comparisons: [
      {
        field: 'vendor_tax_id',
        title: 'Supplier GSTIN',
        invoice_value: '27ABCDE1234F1Z5',
        expected_value: '27ABCDE1234F1Z5',
        expected_label: 'Registered supplier GSTIN',
        status: 'matches',
        source_verification: 'verified',
        pages: [1],
        difference: null,
        currency: null,
        provenance: 'CURRENT_MASTER',
        description: 'Source support and vendor agreement are independent.',
      },
    ],
  };
}

async function routes(
  page: Page,
  run: Run,
  options: {
    serveRun?: (route: Route) => Promise<void>;
    pdfUnavailable?: () => boolean;
    review?: Review;
  } = {},
) {
  await page.route(
    new RegExp('/api/v1/runs/' + id + '$'),
    options.serveRun ?? ((route) => route.fulfill({ json: run })),
  );
  await page.route('**/api/v1/runs/' + id + '/events?*', (route) =>
    route.fulfill({
      json:
        run.decision === 'APPROVED' || run.decision === 'REJECTED'
          ? ([
              {
                run_id: id,
                seq: 1,
                type: 'DECISION_RECORDED',
                stage: 'DECISION',
                occurred_at: at,
                payload: { decision: run.decision },
              },
            ] satisfies RunEvent[])
          : [],
    }),
  );
  await page.route('**/api/v1/runs/' + id + '/events/stream?*', (route) => route.abort());
  await page.route('**/api/v1/runs/' + id + '/document', (route) =>
    options.pdfUnavailable?.()
      ? route.fulfill({ status: 503, json: { detail: 'Original PDF temporarily unavailable.' } })
      : route.fulfill({
          contentType: 'application/pdf',
          body: readFileSync(resolve(directory, 'H1.pdf')),
        }),
  );
  if (options.review)
    await page.route('**/api/v1/runs/' + id + '/review', (route) =>
      route.fulfill({ json: options.review }),
    );
}
async function connect(page: Page) {
  await page.goto('/?run=' + id);
  await page.getByLabel('Workspace access token').fill(values.APP_API_TOKEN);
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
}

test.describe('Invoice detail presentation with explicit mocked read responses', () => {
  test.skip(
    process.env.PS1_BROWSER_ROLES === '1' || process.env.PS1_BROWSER_LIVE === '1',
    'Run with the isolated shared MOCK browser suite',
  );
  test('multiple lines, calculated provenance, PDF controls and keyboard layout keep their meaning', async ({
    page,
  }) => {
    const run = fixture();
    await routes(page, run);
    await connect(page);
    await expect(page.getByRole('heading', { name: 'UI-INV-001', exact: true })).toBeVisible();
    const lines = page.getByRole('region', { name: 'Invoice line items', exact: true });
    await expect(lines.locator('tbody > tr')).toHaveCount(3);
    await expect(lines).toContainText('Storage boxes');
    await expect(page.getByLabel('Invoice summary')).toContainText('₹2,655.00');
    await page.getByLabel('Evidence for Total tax', { exact: true }).click();
    await expect(page.getByText('180.00 + 135.00 + 90.00 = 405.00', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Evidence for Total tax', { exact: true })).toContainText(
      'Calculated',
    );
    await page.getByLabel('Evidence for Invoice number', { exact: true }).click();
    await page
      .getByRole('button', { name: 'View Invoice number source, page 1', exact: true })
      .click();
    await expect(page.locator('.document-caption')).toContainText('Showing page 1');
    const image = page.getByRole('img', { name: 'Invoice PDF preview, page 1' });
    await expect(image).toHaveAttribute('data-rendered', 'true');
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
    await expect(page.getByLabel('PDF zoom')).toHaveText('125%');
    await expect(image).toHaveAttribute('data-rendered', 'true');
    await page.getByRole('button', { name: 'Fit width', exact: true }).click();
    await expect(page.getByLabel('PDF zoom')).toHaveText('100%');
    const divider = page.getByRole('separator', { name: 'Resize PDF and invoice data' });
    await divider.focus();
    await page.keyboard.press('ArrowRight');
    await expect(divider).toHaveAttribute('aria-valuenow', '43');
    await page.getByRole('button', { name: 'Hide PDF', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Source document', exact: true })).toBeHidden();
    await page.getByRole('button', { name: 'Show PDF', exact: true }).click();
    await expect(image).toHaveAttribute('data-rendered', 'true');
    await page.getByRole('tab', { name: 'Financial checks', exact: true }).click();
    await page.keyboard.press('Home');
    await expect(page.getByRole('tab', { name: 'Invoice data', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'PO comparison', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(page.getByRole('region', { name: 'Invoice and PO comparison' })).toContainText(
      'Current record',
    );
    await expect(page.getByRole('button', { name: /^Approve invoice$/ })).toHaveCount(0);
  });
  for (const width of [1440, 768, 390])
    test(`grouped invoice data uses available width at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await routes(page, fixture());
      await connect(page);
      await expect(
        page.getByRole('region', { name: 'Invoice line items', exact: true }),
      ).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      if (width === 1440) {
        const pdf = await page.locator('.invoice-document-pane').boundingBox();
        const data = await page.locator('.invoice-data-pane').boundingBox();
        expect(pdf!.x + pdf!.width).toBeLessThan(data!.x);
        const ratio = pdf!.width / (pdf!.width + data!.width);
        expect(ratio).toBeGreaterThanOrEqual(0.4);
        expect(ratio).toBeLessThanOrEqual(0.45);
      }
      await expect(page.getByRole('img', { name: 'Invoice PDF preview, page 1' })).toHaveAttribute(
        'data-rendered',
        'true',
      );
      await page.screenshot({ path: resolve(shots, `invoice-data-${width}.png`), fullPage: true });
    });
  test('missing required fields stay separate from optional values and source-verified vendor conflicts', async ({
    page,
  }) => {
    const run = fixture();
    run.job_state = 'WAITING_REVIEW';
    run.decision = 'NEEDS_REVIEW';
    run.approved_gross = null;
    run.reason_code = 'CRITICAL_FIELD_MISSING';
    run.decision_reason = 'Invoice date is missing; supplier identity also needs review.';
    run.fields = run.fields.map((f) =>
      f.field === 'invoice_date'
        ? field(f.field, null)
        : f.field === 'vendor_tax_id'
          ? field(f.field, '27AAAAA0000A1Z5')
          : f,
    );
    run.checks[0] = {
      ...run.checks[0],
      status: 'requires_review',
      description: 'Invoice date is missing.',
    };
    run.checks[2] = {
      ...run.checks[2],
      status: 'requires_review',
      description: 'Printed supplier GSTIN differs from the vendor record.',
    };
    run.comparisons[0] = {
      ...run.comparisons[0],
      invoice_value: '27AAAAA0000A1Z5',
      status: 'different',
    };
    await routes(page, run);
    await connect(page);
    const issues = page.getByRole('region', { name: 'Issues requiring attention' });
    await expect(issues).toContainText('Invoice date is missing');
    await expect(issues).toContainText('27AAAAA0000A1Z5');
    await expect(issues).toContainText('27ABCDE1234F1Z5');
    await expect(
      page.getByRole('button', { name: 'Missing required 1', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByLabel('Evidence for Supplier GSTIN / tax ID', { exact: true }),
    ).toContainText('Verified');
    await page.getByRole('tab', { name: 'PO comparison', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Invoice and PO comparison' })).toContainText(
      'PDF verified; values differ',
    );
    await page.locator('.comparison-evidence summary').first().click();
    await page
      .getByRole('button', { name: 'Inspect extracted field', exact: true })
      .first()
      .click();
    await expect(page.locator('#invoice-field-vendor_tax_id')).toBeFocused();
    await expect(page.getByRole('button', { name: /^Approve invoice$/ })).toHaveCount(0);
    await page.screenshot({ path: resolve(shots, 'missing-and-gst-conflict.png'), fullPage: true });
  });
  test('source diagnostics distinguish ambiguous values from failed local association', async ({
    page,
  }) => {
    const run = fixture();
    run.decision = 'NEEDS_REVIEW';
    run.job_state = 'WAITING_REVIEW';
    run.approved_gross = null;
    run.fields = run.fields.map((f) =>
      f.field === 'invoice_date'
        ? {
            ...f,
            verification: 'unverified',
            extraction_state: 'AMBIGUOUS',
            source_reason: 'Local source values conflict; human review is required.',
          }
        : f.field === 'total_gross'
          ? {
              ...f,
              verification: 'unverified',
              extraction_state: 'UNVERIFIED',
              source_reason:
                'A value was extracted, but local verification could not associate it with this field.',
            }
          : f,
    );
    await routes(page, run);
    await connect(page);
    const date = page.getByLabel('Evidence for Invoice date', { exact: true });
    await expect(date).toContainText('Ambiguous');
    await date.click();
    await expect(
      page.getByText('Local source values conflict; human review is required.', { exact: true }),
    ).toBeVisible();
    const total = page.getByLabel('Evidence for Invoice total', { exact: true });
    await total.click();
    await expect(
      page.getByText(
        'A value was extracted, but local verification could not associate it with this field.',
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.locator('#invoice-field-total_gross')).toContainText('₹2,655.00');
  });
  test('expanded buyer, tax and charge fields retain provenance and optional states', async ({
    page,
  }) => {
    const run = fixture();
    run.fields.push(
      field('buyer_name', 'Synthetic Buyer Ltd', { required_for_approval: false }),
      field('due_date', '2026-12-20', { required_for_approval: false }),
      field('payment_terms', 'Net 30 days', { required_for_approval: false }),
      field('cgst_amount', '202.50', {
        origin: 'derived',
        original_value: null,
        calculation: '405.00 / 2 = 202.50',
        extraction_state: 'DERIVED',
      }),
      field('shipping_amount', null, { required_for_approval: false, extraction_state: 'MISSING' }),
      field('lines.1.hsn_sac', '4802', { required_for_approval: false }),
    );
    await routes(page, run);
    await connect(page);
    await expect(
      page.getByRole('heading', { name: 'Buyer and delivery', exact: true }),
    ).toBeVisible();
    await expect(page.locator('#invoice-field-buyer_name')).toContainText('Synthetic Buyer Ltd');
    await expect(page.locator('#invoice-field-payment_terms')).toContainText('Net 30 days');
    await page.getByLabel('Evidence for CGST amount', { exact: true }).click();
    await expect(page.getByText('405.00 / 2 = 202.50', { exact: true })).toBeVisible();
    await expect(page.locator('#invoice-field-shipping_amount')).toContainText('Optional');
    await page.getByRole('button', { name: /Office paper/ }).click();
    await expect(page.locator('#invoice-field-lines-1-hsn_sac')).toContainText('4802');
  });
  test('loading and API/PDF failures have recovery without fabricating data', async ({ page }) => {
    const run = fixture();
    let runReady = false,
      pdfReady = false,
      release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await routes(page, run, {
      serveRun: async (route) => {
        await gate;
        return runReady
          ? route.fulfill({ json: run })
          : route.fulfill({
              status: 503,
              json: { detail: 'Invoice details temporarily unavailable.' },
            });
      },
      pdfUnavailable: () => !pdfReady,
    });
    await connect(page);
    await expect(page.getByText('Reading invoice details…', { exact: true })).toBeVisible();
    release();
    await expect(page.getByRole('alert')).toContainText('Invoice details temporarily unavailable');
    runReady = true;
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'UI-INV-001', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Source document', exact: true })).toContainText(
      'Original PDF temporarily unavailable',
    );
    pdfReady = true;
    await page.getByRole('button', { name: 'Retry PDF', exact: true }).click();
    await expect(page.getByRole('img', { name: 'Invoice PDF preview, page 1' })).toHaveAttribute(
      'data-rendered',
      'true',
    );
  });
  test('queued or failed processing does not imply completed financial validation', async ({
    page,
  }) => {
    const run = fixture();
    run.job_state = 'QUEUED';
    run.decision = null;
    run.decision_reason = null;
    run.approved_gross = null;
    run.fields = [];
    run.stages = [];
    run.checks = [];
    run.comparisons = [];
    run.invoice_number = null;
    run.invoice_total = null;
    run.purchase_order = null;
    await routes(page, run);
    await connect(page);
    await expect(
      page.getByRole('heading', { name: 'Queued for processing', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Missing required Not assessed', exact: true }),
    ).toBeVisible();
    await expect(page.locator('.business-stage .stage-heading > span')).toHaveText(
      Array(6).fill('Pending'),
    );
    await expect(page.locator('.rule-check.passed')).toHaveCount(0);
    run.job_state = 'FAILED';
    run.reason_code = 'EXTRACTION_ERROR';
    run.error_code = 'EXTRACTION_ERROR';
    run.decision_reason = 'Extraction failed; no financial decision was recorded.';
    run.stages = [
      {
        key: 'extraction',
        name: 'EXTRACTION',
        operation: 'EXTRACTION',
        status: 'failed',
        started_at: at,
        finished_at: at,
        elapsed_ms: 100,
      },
    ];
    await expect(
      page.getByRole('heading', { name: 'Processing could not complete', exact: true }),
    ).toBeVisible();
    await expect(page.locator('[data-stage=EXTRACTION] .stage-heading')).toContainText('Failed');
    await expect(page.getByRole('heading', { name: 'Invoice rejected', exact: true })).toHaveCount(
      0,
    );
  });
  test('rejected invoice remains rejected with its recorded reason', async ({ page }) => {
    const run = fixture();
    run.decision = 'REJECTED';
    run.approved_gross = null;
    run.reason_code = 'DUPLICATE_APPROVED';
    run.decision_reason =
      'This supplier invoice identity was already approved. No new allocation was posted.';
    run.checks.push({
      rule_id: 'DUPLICATE_IDENTITY',
      title: 'Invoice identity was already approved',
      status: 'failed',
      description: run.decision_reason,
      provenance: 'RECORDED_ASSESSMENT',
      finding_code: 'DUPLICATE_APPROVED',
      assessment_revision: 1,
      pages: [1],
    });
    await routes(page, run);
    await connect(page);
    await expect(
      page.getByRole('heading', { name: 'Invoice rejected', exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel('Financial decision')).toContainText('already approved');
    await expect(page.getByRole('button', { name: /^Approve invoice$/ })).toHaveCount(0);
  });
  test('review uses only offered actions and keeps rationale through tabs and a rejected request', async ({
    page,
  }) => {
    const run = fixture();
    run.job_state = 'WAITING_REVIEW';
    run.decision = 'NEEDS_REVIEW';
    run.approved_gross = null;
    run.reason_code = 'TAX_UNCLEAR';
    run.review_request_id = reviewId;
    run.decision_reason = 'Tax evidence requires review.';
    const review: Review = {
      review_request_id: reviewId,
      run_id: id,
      generation: 1,
      kind: 'FINANCIAL_EXCEPTION',
      question: 'Request corrected tax evidence or reject.',
      options: [],
      allowed_actions: ['REQUEST_INFO', 'REJECT'],
      status: 'OPEN',
    };
    await routes(page, run, { review });
    const keys: string[] = [];
    await page.route('**/reviews/' + reviewId + '/respond', (route) => {
      keys.push(route.request().headers()['x-idempotency-key']);
      return route.fulfill({
        status: 409,
        json: { detail: { code: 'REVIEW_CONFLICT', message: 'Review state changed.' } },
      });
    });
    await connect(page);
    await expect(page.getByRole('tab', { name: 'Review response', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await page.getByLabel('Action', { exact: true }).selectOption('REQUEST_INFO');
    await page.getByLabel('Reviewer access token', { exact: true }).fill(values.REVIEWER_API_TOKEN);
    await page
      .getByLabel('Review rationale', { exact: true })
      .fill('Request the original itemised tax breakdown.');
    await page.getByRole('tab', { name: 'Invoice data', exact: true }).click();
    await page.getByRole('tab', { name: 'Review response', exact: true }).click();
    await expect(page.getByLabel('Review rationale', { exact: true })).toHaveValue(
      'Request the original itemised tax breakdown.',
    );
    await expect(page.getByRole('option', { name: 'Select PO & resume', exact: true })).toHaveCount(
      0,
    );
    await page.getByRole('button', { name: 'Submit review response', exact: true }).click();
    await expect(
      page.getByRole('alert').filter({ hasText: 'record changed' }).first(),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Review required', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Submit review response', exact: true }).click();
    await expect.poll(() => keys.length).toBe(2);
    expect(keys[1]).toBe(keys[0]);
  });
  test('late review metadata respects an explicitly chosen detail tab', async ({ page }) => {
    const run = fixture();
    run.job_state = 'WAITING_REVIEW';
    run.decision = 'NEEDS_REVIEW';
    run.approved_gross = null;
    run.reason_code = 'BANK_MISMATCH';
    run.review_request_id = reviewId;
    run.decision_reason = 'Bank details require independent verification.';
    const review: Review = {
      review_request_id: reviewId,
      run_id: id,
      generation: 1,
      kind: 'FINANCIAL_EXCEPTION',
      question: 'Request independent verification.',
      options: [],
      allowed_actions: ['REQUEST_INFO', 'REJECT'],
      status: 'OPEN',
    };
    await routes(page, run);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route('**/api/v1/runs/' + id + '/review', async (route) => {
      await gate;
      await route.fulfill({ json: review });
    });
    await connect(page);
    await page.getByRole('tab', { name: 'Financial checks', exact: true }).click();
    release();
    await expect(page.getByRole('tab', { name: 'Review response', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Financial checks', exact: true })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await expect(
      page.getByRole('heading', { name: 'Financial rule checklist', exact: true }),
    ).toBeVisible();
    await page.getByRole('tab', { name: 'Review response', exact: true }).click();
    await expect(page.getByLabel('Review rationale', { exact: true })).toBeVisible();
  });
  test('relative price display uses exact decimals and has no result for invalid or zero bases', () => {
    expect(relativeDifference('2.5000', '500.0000')).toBe('0.50%');
    expect(relativeDifference('-2.5000', '500.0000')).toBe('−0.50%');
    expect(relativeDifference('0.00005', '1')).toBe('0.01%');
    expect(relativeDifference('1', '0')).toBeNull();
    expect(relativeDifference('Infinity', '1')).toBeNull();
    expect(relativeDifference('1', null)).toBeNull();
  });
});
