import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, errorMessage, money } from './api';
import type { components } from './api.generated';
import { vendorStatusLabel } from './ui';

type Creation = components['schemas']['POCreated'];
type Vendors = components['schemas']['VendorChoices'];
type Totals = components['schemas']['POTotals'];
type Line = {
  id: string;
  sku: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
};
const newLine = (): Line => ({
  id: crypto.randomUUID(),
  sku: '',
  description: '',
  quantity: '',
  unit_price: '',
  tax_rate: '',
});

export default function CreatePurchaseOrder({
  token,
  onCreated,
  onCancel,
}: {
  token: string;
  onCreated: (receipt: Creation) => void;
  onCancel: () => void;
}) {
  const [vendors, setVendors] = useState<Vendors | null>(null);
  const [vendorSearch, setVendorSearch] = useState('');
  const [query, setQuery] = useState('');
  const [vendor, setVendor] = useState('');
  const [vendorError, setVendorError] = useState('');
  const [vendorRevision, setVendorRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [number, setNumber] = useState('');
  const [issued, setIssued] = useState('');
  const [expires, setExpires] = useState('');
  const [cap, setCap] = useState('');
  const [reason, setReason] = useState('');
  const [lines, setLines] = useState<Line[]>([newLine()]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [calculationError, setCalculationError] = useState('');
  const previewController = useRef<AbortController | null>(null);
  const selectedVendor = vendors?.items.find((item) => item.vendor_id === vendor);
  const allowedVendor = selectedVendor?.status === 'ACTIVE';
  const pending = useRef(false);
  const mounted = useRef(true);
  const requestController = useRef<AbortController | null>(null);
  const requestKey = useRef({ fingerprint: '', key: crypto.randomUUID() });
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    mounted.current = true;
    heading.current?.focus();
    return () => {
      mounted.current = false;
      requestController.current?.abort();
      previewController.current?.abort();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setVendorError('');
    setVendors(null);
    void api<Vendors>(
      '/vendors?' + new URLSearchParams({ q: query, limit: '50', include_unavailable: 'true' }),
      token,
      {
        signal: controller.signal,
      },
    )
      .then((result) => {
        if (!controller.signal.aborted) setVendors(result);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setVendorError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, query, vendorRevision]);
  function changeLine(id: string, field: keyof Omit<Line, 'id'>, value: string) {
    invalidatePreview();
    setLines((items) => items.map((line) => (line.id === id ? { ...line, [field]: value } : line)));
  }
  function invalidatePreview() {
    previewController.current?.abort();
    setTotals(null);
    setCalculationError('');
    setCalculating(false);
  }
  function lineBody() {
    return lines.map(({ id: _id, ...line }) => ({
      ...line,
      sku: line.sku.trim() || null,
      description: line.description.trim(),
      quantity: line.quantity.trim(),
      unit_price: line.unit_price.trim(),
      tax_rate: line.tax_rate.trim(),
    }));
  }
  async function calculate() {
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    setCalculating(true);
    setCalculationError('');
    setTotals(null);
    try {
      const result = await api<Totals>('/purchase-orders/preview', token, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines: lineBody() }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted && mounted.current) setTotals(result);
    } catch (e) {
      if (!controller.signal.aborted && mounted.current) setCalculationError(errorMessage(e));
    } finally {
      if (!controller.signal.aborted && mounted.current) setCalculating(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current || loading || !vendor || !allowedVendor) return;
    const body = {
      po_number: number.trim(),
      vendor_id: vendor,
      currency: 'INR',
      issued_at: issued,
      expires_at: expires || null,
      cap_gross: cap.trim(),
      reason: reason.trim(),
      lines: lineBody(),
    };
    const fingerprint = JSON.stringify(body);
    if (requestKey.current.fingerprint !== fingerprint)
      requestKey.current = { fingerprint, key: crypto.randomUUID() };
    pending.current = true;
    setBusy(true);
    setError('');
    const controller = new AbortController();
    requestController.current = controller;
    try {
      const receipt = await api<Creation>('/purchase-orders', token, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Key': requestKey.current.key,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (mounted.current) onCreated(receipt);
    } catch (e) {
      if (mounted.current) setError(errorMessage(e));
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <section className="panel po-create" aria-label="Create purchase order">
      <h2 ref={heading} tabIndex={-1}>
        Create purchase order
      </h2>
      <p>
        Create an open INR order for an approved vendor. This authorizes a new spending limit; only
        create orders you are authorized to issue.
      </p>
      <form onSubmit={(event) => void submit(event)}>
        <fieldset disabled={busy}>
          <legend>Vendor and order details</legend>
          <div className="po-form-grid">
            <label>
              Find a vendor
              <input
                type="search"
                maxLength={120}
                value={vendorSearch}
                onChange={(event) => setVendorSearch(event.target.value)}
              />
            </label>
            <button
              className="button quiet po-vendor-search"
              type="button"
              disabled={loading}
              onClick={() => {
                setVendor('');
                setQuery(vendorSearch.trim());
                setVendorRevision((n) => n + 1);
              }}
            >
              Search vendors
            </button>
            <div className="po-wide">
              <label htmlFor="po-create-vendor">Vendor</label>
              <select
                id="po-create-vendor"
                required
                value={vendor}
                disabled={loading || !vendors?.items.length}
                onChange={(event) => setVendor(event.target.value)}
              >
                <option value="">{loading ? 'Loading vendors…' : 'Select a vendor'}</option>
                {vendors?.items.map((item) => (
                  <option key={item.vendor_id} value={item.vendor_id}>
                    {item.legal_name}
                    {' · ' + vendorStatusLabel(item.status)}
                    {item.tax_id ? ' · ' + item.tax_id : ''}
                  </option>
                ))}
              </select>
              {selectedVendor && !allowedVendor && (
                <p className="vendor-restriction" role="alert">
                  {selectedVendor.status === 'BLACKLISTED'
                    ? 'Purchase orders cannot be created for a blacklisted vendor. Choose an approved vendor.'
                    : 'This vendor is inactive. Choose an approved vendor.'}
                </p>
              )}
            </div>
            <label>
              PO reference
              <input
                required
                maxLength={100}
                value={number}
                onChange={(event) => setNumber(event.target.value)}
                autoCapitalize="none"
                spellCheck={false}
              />
            </label>
            <label>
              Gross spending cap (INR)
              <input
                required
                type="text"
                inputMode="decimal"
                maxLength={64}
                value={cap}
                onChange={(event) => setCap(event.target.value)}
                aria-describedby="po-cap-help"
              />
            </label>
            <label>
              PO issue date
              <input
                required
                type="date"
                value={issued}
                onChange={(event) => setIssued(event.target.value)}
              />
            </label>
            <label>
              Expiry date (optional)
              <input
                type="date"
                value={expires}
                min={issued || undefined}
                onChange={(event) => setExpires(event.target.value)}
              />
            </label>
          </div>
          {vendors && (
            <p>
              {vendors.items.length} of {vendors.total_count} vendor matches shown. Refine your
              search if needed.
            </p>
          )}
          {vendorError && (
            <div className="error" role="alert">
              {vendorError}{' '}
              <button type="button" onClick={() => setVendorRevision((n) => n + 1)}>
                Retry vendors
              </button>
            </div>
          )}
          {!loading && vendors && !vendors.total_count && (
            <p>No vendors match. Use Manage vendors in Purchase orders to register a vendor.</p>
          )}
          <p id="po-cap-help">
            Use the exact PO reference the invoice will quote. The gross cap must be at or below the
            line total including tax. Both quantities and the cap limit approval. Invoice dates must
            satisfy the PO issue date.
          </p>
        </fieldset>
        <fieldset disabled={busy}>
          <legend>Line items</legend>
          <p>Enter net unit prices and explicit tax rates. Use 0 for a confirmed zero-tax line.</p>
          {lines.map((line, index) => (
            <section className="po-line-form" key={line.id} aria-label={`PO line ${index + 1}`}>
              <h3>Line {index + 1}</h3>
              <div className="po-form-grid">
                <label>
                  SKU (optional)
                  <input
                    maxLength={100}
                    value={line.sku}
                    onChange={(event) => changeLine(line.id, 'sku', event.target.value)}
                  />
                </label>
                <label>
                  Description
                  <input
                    required
                    maxLength={500}
                    value={line.description}
                    onChange={(event) => changeLine(line.id, 'description', event.target.value)}
                  />
                </label>
                <label>
                  Quantity
                  <input
                    required
                    type="text"
                    inputMode="decimal"
                    maxLength={64}
                    value={line.quantity}
                    onChange={(event) => changeLine(line.id, 'quantity', event.target.value)}
                  />
                </label>
                <label>
                  Net unit price (INR)
                  <input
                    required
                    type="text"
                    inputMode="decimal"
                    maxLength={64}
                    value={line.unit_price}
                    onChange={(event) => changeLine(line.id, 'unit_price', event.target.value)}
                  />
                </label>
                <label>
                  Tax rate (%)
                  <input
                    required
                    type="text"
                    inputMode="decimal"
                    maxLength={64}
                    value={line.tax_rate}
                    onChange={(event) => changeLine(line.id, 'tax_rate', event.target.value)}
                  />
                </label>
              </div>
              <button
                className="button quiet small"
                type="button"
                disabled={lines.length === 1}
                onClick={() => {
                  invalidatePreview();
                  setLines((items) => items.filter((item) => item.id !== line.id));
                }}
              >
                Remove line {index + 1}
              </button>
            </section>
          ))}
          <button
            className="button quiet small"
            type="button"
            disabled={lines.length >= 50}
            onClick={() => {
              invalidatePreview();
              setLines((items) => [...items, newLine()]);
            }}
          >
            Add line
          </button>
          <section className="po-totals" aria-label="Calculated order totals">
            <h3>Order totals</h3>
            <p>
              Calculate after entering all lines. Tax is added to net prices; each line is rounded
              to two decimals.
            </p>
            <button
              className="button quiet"
              type="button"
              disabled={calculating}
              onClick={() => void calculate()}
            >
              {calculating ? 'Calculating…' : 'Calculate totals'}
            </button>
            {calculationError && (
              <div className="error" role="alert">
                {calculationError}
              </div>
            )}
            {totals ? (
              <>
                <dl className="po-totals-list">
                  <div>
                    <dt>Subtotal before tax</dt>
                    <dd>{money(totals.subtotal_net, totals.currency)}</dd>
                  </div>
                  <div>
                    <dt>Tax</dt>
                    <dd>{money(totals.tax_total, totals.currency)}</dd>
                  </div>
                  <div>
                    <dt>Total including tax</dt>
                    <dd>{money(totals.total_gross, totals.currency)}</dd>
                  </div>
                </dl>
                <button
                  className="button quiet small"
                  type="button"
                  onClick={() => setCap(totals.total_gross)}
                >
                  Use total as spending cap
                </button>
                <p>The cap can be lower than this total. Saving rechecks all amounts.</p>
              </>
            ) : (
              <p>Totals need recalculating whenever a line changes.</p>
            )}
          </section>
          <label className="po-reason">
            Authorization rationale
            <textarea
              required
              minLength={5}
              maxLength={500}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        </fieldset>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <p>
          Existing orders cannot be edited here. Creating a PO does not approve or pay an invoice.
        </p>
        <div className="po-form-actions">
          <button className="button" disabled={busy || loading || !vendor || !allowedVendor}>
            {busy ? 'Creating purchase order…' : 'Create purchase order'}
          </button>
          <button className="button quiet" type="button" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}
