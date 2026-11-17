import { useEffect, useState } from 'react';
import { api, dateTime, errorMessage, money, type POPage, type POLedger } from './api';
import { Badge, Icon, Link, type Navigate } from './ui';
export default function PurchaseOrders({
  token,
  poId,
  navigate,
}: {
  token: string;
  poId: string | null;
  navigate: Navigate;
}) {
  const [page, setPage] = useState<POPage | null>(null),
    [po, setPo] = useState<POLedger | null>(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [search, setSearch] = useState(''),
    [query, setQuery] = useState(''),
    [after, setAfter] = useState(''),
    [previous, setPrevious] = useState<string[]>([]),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    setPage(null);
    setPo(null);
    setError('');
    if (!token) return;
    const controller = new AbortController();
    setLoading(true);
    const path = poId
      ? '/purchase-orders/' + poId
      : '/purchase-orders?' + new URLSearchParams({ q: query, after, limit: '20' });
    api<POPage | POLedger>(path, token, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (poId) setPo(data as POLedger);
        else setPage(data as POPage);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, poId, query, after, revision]);
  return (
    <>
      <div className="page-heading">
        <div>
          {poId && (
            <Link to="?view=purchase-orders" navigate={navigate} className="back-link">
              ← All Purchase orders
            </Link>
          )}
          <h1 className={po ? 'mono' : ''}>
            {po?.po_number ?? (poId ? 'Purchase order ledger' : 'Purchase orders')}
          </h1>
          <p>
            {po?.vendor_name ?? 'Inspect authorized funds and their immutable invoice allocations.'}
          </p>
        </div>
        <button className="button quiet" onClick={() => setRevision((n) => n + 1)}>
          <Icon name="refresh" size={16} />
          Refresh purchase orders
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!token ? (
        <div className="panel empty-state">Connect your workspace to inspect purchase orders.</div>
      ) : loading ? (
        <div className="panel empty-state" role="status">
          Loading purchase orders…
        </div>
      ) : po ? (
        <>
          <div className="po-ledger-head">
            <Badge value={po.status} />
            <span>
              Issued {po.issued_at}
              {po.expires_at ? ' · expires ' + po.expires_at : ''}
            </span>
            <span>Current master and immutable ledger snapshot</span>
          </div>
          {!po.balance_reconciled && (
            <div className="error" role="alert">
              Committed counters disagree with immutable allocations. Available balance is unknown;
              this page cannot authorize posting.
            </div>
          )}
          <div className="metric-strip">
            <section>
              <span>PO authorized now</span>
              <strong>{money(po.cap_gross, po.currency)}</strong>
              <small>Current master, not historical cap</small>
            </section>
            <section>
              <span>Recorded approvals</span>
              <strong>{money(po.ledger_committed_gross, po.currency)}</strong>
              <small>{po.allocation_count} immutable ledger entries</small>
            </section>
            <section>
              <span>Current committed amount</span>
              <strong>{money(po.committed_gross, po.currency)}</strong>
              <small>
                PO counter {po.balance_reconciled ? 'reconciled' : 'does not reconcile'}
              </small>
            </section>
            <section>
              <span>Remaining available</span>
              <strong>{money(po.available_gross, po.currency)}</strong>
              <small>Held invoices reserve nothing</small>
            </section>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Approved invoice allocations</h2>
                <p>Only committed approvals appear. An approval is not a payment.</p>
              </div>
            </div>
            {!po.allocations.length ? (
              <div className="empty-state">No approved invoice has consumed this PO.</div>
            ) : (
              <div className="table-scroll" tabIndex={0} aria-label="Scrollable approval ledger">
                <table>
                  <thead>
                    <tr>
                      <th>Invoice Number</th>
                      <th>Invoice Date</th>
                      <th>Approved at</th>
                      <th className="amount">Allocated amount</th>
                      <th>
                        <span className="sr-only">Open invoice</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {po.allocations.map((entry) => (
                      <tr key={entry.ledger_id}>
                        <td className="mono">
                          <Link
                            to={'?run=' + entry.run_id}
                            navigate={navigate}
                            className="text-link"
                          >
                            {entry.invoice_number}
                          </Link>
                        </td>
                        <td>{entry.invoice_date}</td>
                        <td>{dateTime(entry.approved_at)}</td>
                        <td className="amount">{money(entry.gross, po.currency)}</td>
                        <td>
                          <Link
                            to={'?run=' + entry.run_id}
                            navigate={navigate}
                            className="row-action"
                          >
                            View invoice →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="table-note">
              {po.allocations_truncated
                ? 'Showing the first 100 allocations; the total includes all entries. '
                : ''}
              Historical balances are not inferred from the current PO cap. Invoice decisions retain
              assessment-time observations where recorded.
            </p>
          </section>
        </>
      ) : !poId && page ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>
              Purchase order register <span className="count">{page.total_count}</span>
            </h2>
          </div>
          <form
            className="filters search-form"
            onSubmit={(e) => {
              e.preventDefault();
              setAfter('');
              setPrevious([]);
              setQuery(search.trim());
            }}
          >
            <label className="sr-only" htmlFor="po-search">
              Search purchase orders
            </label>
            <input
              id="po-search"
              type="search"
              maxLength={120}
              placeholder="PO number or vendor"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button className="button quiet small">Search</button>
          </form>
          {!page.items.length ? (
            <div className="empty-state">No matching purchase orders.</div>
          ) : (
            <div className="table-scroll" tabIndex={0} aria-label="Scrollable purchase orders">
              <table>
                <thead>
                  <tr>
                    <th>PO / vendor</th>
                    <th>Status</th>
                    <th className="amount">Authorized</th>
                    <th className="amount">Currently committed</th>
                    <th>
                      <span className="sr-only">Inspect</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((item) => (
                    <tr key={item.po_id}>
                      <td>
                        <Link
                          to={'?po=' + item.po_id}
                          navigate={navigate}
                          className="text-link mono"
                        >
                          {item.po_number}
                        </Link>
                        <small className="cell-detail">{item.vendor_name}</small>
                      </td>
                      <td>
                        <Badge value={item.status} />
                      </td>
                      <td className="amount">{money(item.cap_gross, item.currency)}</td>
                      <td className="amount">{money(item.committed_gross, item.currency)}</td>
                      <td>
                        <Link to={'?po=' + item.po_id} navigate={navigate} className="row-action">
                          View ledger →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination">
            <span>Read-only. No PO amendment or financial posting is available.</span>
            <div>
              <button
                className="button quiet small"
                disabled={!previous.length}
                onClick={() => {
                  setAfter(previous.at(-1) ?? '');
                  setPrevious((v) => v.slice(0, -1));
                }}
              >
                Previous
              </button>
              <button
                className="button quiet small"
                disabled={!page.next_after}
                onClick={() => {
                  setPrevious((v) => [...v, after]);
                  setAfter(page.next_after ?? '');
                }}
              >
                Next
              </button>
            </div>
          </div>
        </section>
      ) : (
        <div className="panel empty-state">
          {error ? 'Unable to load this record. Retry above.' : 'Reading purchase order…'}
        </div>
      )}
    </>
  );
}
