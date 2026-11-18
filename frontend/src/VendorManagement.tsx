import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, errorMessage } from './api';
import type { components } from './api.generated';
import { vendorStatusLabel } from './ui';

type Choices = components['schemas']['VendorChoices'];
type Vendor = components['schemas']['VendorChoice'];
type Recorded = components['schemas']['VendorRecorded'];

export default function VendorManagement({
  token,
  onClose,
}: {
  token: string;
  onClose: () => void;
}) {
  const [vendors, setVendors] = useState<Choices | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [editing, setEditing] = useState<Vendor | 'new' | null>(null);
  const [name, setName] = useState('');
  const [tax, setTax] = useState('');
  const [bank, setBank] = useState('');
  const [status, setStatus] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const commandKey = useRef({ fingerprint: '', key: crypto.randomUUID() });
  const heading = useRef<HTMLHeadingElement>(null);
  const editor = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    mounted.current = true;
    heading.current?.focus();
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (editing) editor.current?.focus();
  }, [editing]);
  useEffect(() => {
    const request = new AbortController();
    setLoading(true);
    setListError('');
    void api<Choices>(
      '/vendors?' + new URLSearchParams({ q: query, limit: '50', include_unavailable: 'true' }),
      token,
      { signal: request.signal },
    )
      .then((data) => {
        if (!request.signal.aborted) setVendors(data);
      })
      .catch((e) => {
        if (!request.signal.aborted) setListError(errorMessage(e));
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [token, query, revision]);
  function edit(vendor: Vendor | 'new') {
    setEditing(vendor);
    setName('');
    setTax('');
    setBank('');
    setStatus(vendor === 'new' ? '' : vendor.status);
    setReason('');
    setError('');
    setMessage('');
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (pending.current || !editing || !status) return;
    const creating = editing === 'new';
    const path = creating ? '/vendors' : `/vendors/${editing.vendor_id}/status`;
    const body = creating
      ? {
          legal_name: name.trim(),
          status,
          tax_id: tax.trim() || null,
          bank_last4: bank.trim() || null,
          reason: reason.trim(),
        }
      : { status, reason: reason.trim() };
    const fingerprint = JSON.stringify({ path, body });
    if (commandKey.current.fingerprint !== fingerprint)
      commandKey.current = { fingerprint, key: crypto.randomUUID() };
    pending.current = true;
    setBusy(true);
    setError('');
    const request = new AbortController();
    controller.current = request;
    try {
      await api<Recorded>(path, token, {
        method: creating ? 'POST' : 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Key': commandKey.current.key,
        },
        body: JSON.stringify(body),
        signal: request.signal,
      });
      if (mounted.current) {
        setMessage(
          creating
            ? 'Vendor added. Its selected status applies to new orders and invoice checks.'
            : 'Vendor status recorded. Existing approvals remain in the ledger.',
        );
        setEditing(null);
        setRevision((n) => n + 1);
        heading.current?.focus();
      }
    } catch (e) {
      if (mounted.current) setError(errorMessage(e));
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <section className="panel po-create" aria-label="Manage vendors">
      <div className="vendor-heading">
        <div>
          <h2 ref={heading} tabIndex={-1}>
            Manage vendors
          </h2>
          <p>
            Register a vendor or change its authorization status. Only approved vendors can receive
            new purchase orders.
          </p>
        </div>
        <button className="button quiet" disabled={busy} onClick={onClose}>
          Back to purchase orders
        </button>
      </div>
      {message && (
        <p className="toast" role="status">
          {message}
        </p>
      )}
      <form
        className="po-form-grid"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
          setRevision((n) => n + 1);
        }}
      >
        <label>
          Find a vendor
          <input
            type="search"
            maxLength={120}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <button className="button quiet po-vendor-search" disabled={loading || busy}>
          Search vendors
        </button>
      </form>
      {listError && (
        <div className="error" role="alert">
          {listError}{' '}
          <button type="button" onClick={() => setRevision((n) => n + 1)}>
            Retry vendors
          </button>
        </div>
      )}
      {loading ? (
        <p role="status">Loading vendors…</p>
      ) : (
        !listError &&
        vendors && (
          <>
            <p>
              {vendors.items.length} of {vendors.total_count} vendors shown. Search by name to
              narrow the list.
            </p>
            {vendors.items.length ? (
              <div className="vendor-list" aria-label="Vendor directory">
                {vendors.items.map((vendor) => (
                  <div className="vendor-row" key={vendor.vendor_id}>
                    <div>
                      <strong>{vendor.legal_name}</strong>
                      <small>{vendor.tax_id ?? 'No tax ID recorded'}</small>
                    </div>
                    <span className={`vendor-status vendor-${vendor.status.toLowerCase()}`}>
                      {vendorStatusLabel(vendor.status)}
                    </span>
                    <button
                      className="button quiet small"
                      disabled={busy}
                      onClick={() => edit(vendor)}
                      aria-label={`Change status for ${vendor.legal_name}`}
                    >
                      Change status
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p>No vendors match this search.</p>
            )}
          </>
        )
      )}
      {!editing && (
        <button className="button" onClick={() => edit('new')}>
          Add vendor
        </button>
      )}
      {editing && (
        <form
          aria-label={editing === 'new' ? 'Add vendor' : 'Change vendor status'}
          onSubmit={(event) => void save(event)}
        >
          <fieldset disabled={busy}>
            <h3 ref={editor} tabIndex={-1}>
              {editing === 'new' ? 'Add vendor' : `Change status: ${editing.legal_name}`}
            </h3>
            <p>
              Use the vendor’s legal name as it appears on invoices. Approving a vendor authorizes
              it for matching; every invoice still undergoes financial validation.
            </p>
            <div className="po-form-grid">
              {editing === 'new' && (
                <>
                  <label className="po-wide">
                    Legal vendor name
                    <input
                      required
                      maxLength={200}
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                    />
                  </label>
                  <label>
                    Tax ID (optional)
                    <input
                      maxLength={100}
                      value={tax}
                      onChange={(event) => setTax(event.target.value)}
                    />
                  </label>
                  <label>
                    Bank account last four (optional)
                    <input
                      inputMode="numeric"
                      pattern="[0-9]{4}"
                      maxLength={4}
                      value={bank}
                      onChange={(event) => setBank(event.target.value)}
                    />
                  </label>
                </>
              )}
              <div className="po-wide">
                <label htmlFor="vendor-management-status">Vendor status</label>
                <select
                  id="vendor-management-status"
                  required
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="">Select a status</option>
                  <option value="ACTIVE">Approved</option>
                  <option value="INACTIVE">Inactive</option>
                  <option value="BLACKLISTED">Blacklisted</option>
                </select>
              </div>
              <label className="po-wide po-reason">
                Vendor authorization rationale
                <textarea
                  required
                  minLength={5}
                  maxLength={500}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </label>
            </div>
            {status === 'BLACKLISTED' && (
              <p className="vendor-restriction">
                Blacklisted vendors cannot receive new POs or invoice approvals. Existing approval
                history is retained.
              </p>
            )}
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <div className="po-form-actions">
              <button className="button">
                {busy ? 'Saving vendor…' : editing === 'new' ? 'Save vendor' : 'Save status'}
              </button>
              <button
                className="button quiet"
                type="button"
                onClick={() => {
                  setEditing(null);
                  setError('');
                  heading.current?.focus();
                }}
              >
                Cancel vendor changes
              </button>
            </div>
          </fieldset>
        </form>
      )}
    </section>
  );
}
