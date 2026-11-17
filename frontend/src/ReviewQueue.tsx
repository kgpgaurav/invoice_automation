import { useEffect, useState } from 'react';
import { api, dateTime, errorMessage, money, type RunPage } from './api';
import { Icon, Link, Mode, reasonLabel, type Navigate } from './ui';
import RunView from './RunView';

function receivedAge(value: string) {
  const elapsed = Date.now() - Date.parse(value);
  if (!Number.isFinite(elapsed)) return 'Unknown';
  if (elapsed < 60000) return 'Just now';
  if (elapsed < 3600000) return Math.floor(elapsed / 60000) + 'm';
  if (elapsed < 86400000) return Math.floor(elapsed / 3600000) + 'h';
  return Math.floor(elapsed / 86400000) + 'd';
}

export default function ReviewQueue({
  token,
  params,
  navigate,
  notify,
  reviewerToken,
}: {
  token: string;
  params: URLSearchParams;
  navigate: Navigate;
  notify: (s: string) => void;
  reviewerToken?: string;
}) {
  const q = params.get('q') ?? '',
    cursor = params.get('cursor') ?? '';
  const selected = params.get('selected');
  const [page, setPage] = useState<RunPage | null>(null);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  const [search, setSearch] = useState(q),
    [revision, setRevision] = useState(0);
  const [previous, setPrevious] = useState<string[]>([]);
  const [wide, setWide] = useState(() => matchMedia('(min-width: 1100px)').matches);
  useEffect(() => {
    const media = matchMedia('(min-width: 1100px)');
    const change = () => setWide(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => setSearch(q), [q]);
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    setPage(null);
    setLoading(true);
    setError('');
    const refresh = async () => {
      if (pending) return;
      pending = true;
      const query = new URLSearchParams({ state: 'WAITING_REVIEW', limit: '10' });
      if (q) query.set('q', q);
      if (cursor) query.set('cursor', cursor);
      try {
        const value = await api<RunPage>('/runs?' + query, token, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setPage(value);
          setError('');
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      } finally {
        pending = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    const refreshEvent = () => void refresh();
    void refresh();
    const timer = setInterval(refreshEvent, 10000);
    addEventListener('ps1:record-updated', refreshEvent);
    return () => {
      controller.abort();
      clearInterval(timer);
      removeEventListener('ps1:record-updated', refreshEvent);
    };
  }, [token, q, cursor, revision]);
  function locationFor(selection: string | null, nextCursor = cursor, nextQ = q) {
    const query = new URLSearchParams({ view: 'review' });
    if (selection) query.set('selected', selection);
    if (nextQ) query.set('q', nextQ);
    if (nextCursor) query.set('cursor', nextCursor);
    return '?' + query;
  }
  const active = selected ?? (wide ? page?.items[0]?.run_id : null);
  return (
    <>
      <div className="page-heading queue-heading">
        <div>
          <h1>Review queue</h1>
          <p role="status">
            {loading
              ? 'Loading review queue…'
              : error
                ? 'Queue could not be refreshed'
                : q
                  ? `${page?.total_count ?? 0} matching invoices`
                  : `${page?.total_count ?? 0} ${(page?.total_count ?? 0) === 1 ? 'invoice needs' : 'invoices need'} attention`}
          </p>
        </div>
        <div className="queue-heading-actions">
          <form
            className="queue-search"
            onSubmit={(e) => {
              e.preventDefault();
              setPrevious([]);
              navigate(locationFor(null, '', search.trim()));
            }}
          >
            <label className="sr-only" htmlFor="queue-search">
              Search invoices
            </label>
            <input
              type="search"
              id="queue-search"
              value={search}
              maxLength={120}
              placeholder="Search vendor or invoice"
              onChange={(e) => setSearch(e.target.value)}
            />
            <button className="button quiet small">Search</button>
          </form>
          <button
            className="icon-button"
            aria-label="Refresh review queue"
            onClick={() => setRevision((n) => n + 1)}
          >
            <Icon name="refresh" size={18} />
          </button>
        </div>
      </div>
      <div className={'review-workspace' + (selected ? ' has-selection' : '')}>
        <section className="panel queue-list" aria-label="Review items">
          {error && (
            <div className="error" role="alert">
              {error}
              <button className="text-link" onClick={() => setRevision((n) => n + 1)}>
                Retry
              </button>
            </div>
          )}
          {loading ? (
            <div className="empty-state" role="status">
              Loading review items…
            </div>
          ) : !page?.items.length ? (
            <div className="empty-state">
              <Icon name={error ? 'alert' : q ? 'file' : 'check'} size={30} />
              <h2>
                {error
                  ? 'Review items unavailable'
                  : q
                    ? 'No matching invoices'
                    : 'Your review queue is clear'}
              </h2>
              <p>
                {error
                  ? 'Try again to load the current queue.'
                  : q
                    ? 'Try a different invoice number or vendor.'
                    : 'Invoices that need a financial reviewer will appear here.'}
              </p>
              {q && (
                <Link to="?view=review" navigate={navigate} className="text-link">
                  Clear search
                </Link>
              )}
              {!q && !error && (
                <Link to="?view=history" navigate={navigate} className="text-link">
                  View invoice history
                  <Icon name="arrow" size={16} />
                </Link>
              )}
            </div>
          ) : (
            <div className="queue-table-wrap">
              <table className="queue-table">
                <thead>
                  <tr>
                    <th>Vendor / invoice</th>
                    <th className="amount">Amount</th>
                    <th>Reason</th>
                    <th className="amount">
                      Age<span className="sr-only"> since receipt</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((run) => (
                    <tr key={run.run_id} className={active === run.run_id ? 'selected' : ''}>
                      <td>
                        <Link
                          to={locationFor(run.run_id)}
                          navigate={navigate}
                          className="queue-invoice"
                        >
                          <strong>{run.vendor_name ?? 'Supplier not extracted'}</strong>
                          <span>{run.invoice_number ?? 'Run ' + run.run_id.slice(0, 8)}</span>
                          <Mode value={run.source_mode} />
                          <span className="sr-only">
                            {active === run.run_id ? 'Selected invoice. ' : ''}Review invoice
                          </span>
                        </Link>
                      </td>
                      <td className="amount">{money(run.total_gross, run.currency ?? '')}</td>
                      <td>
                        <span className="queue-reason" title={reasonLabel(run.reason_code)}>
                          {run.reason_code === 'PO_AMBIGUOUS' || run.reason_code === 'PO_MISSING'
                            ? 'Missing PO'
                            : run.reason_code === 'PO_CAP_EXCEEDED'
                              ? 'Over PO balance'
                              : run.reason_code === 'BANK_MISMATCH'
                                ? 'Bank details'
                                : 'Needs review'}
                        </span>
                      </td>
                      <td className="queue-age amount">
                        <time
                          dateTime={run.created_at}
                          title={'Received ' + dateTime(run.created_at)}
                        >
                          {receivedAge(run.created_at)}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination queue-pagination">
            <span>Age is time since receipt.</span>
            <div>
              <button
                className="button quiet small"
                disabled={!cursor || loading}
                onClick={() => {
                  const value = previous.at(-1) ?? '';
                  setPrevious((old) => old.slice(0, -1));
                  navigate(locationFor(null, value));
                }}
              >
                Previous
              </button>
              <button
                className="button quiet small"
                disabled={!page?.next_cursor || loading}
                onClick={() => {
                  setPrevious((old) => [...old, cursor]);
                  navigate(locationFor(null, page?.next_cursor ?? ''));
                }}
              >
                Next
              </button>
            </div>
          </div>
        </section>
        <section className="panel queue-detail" aria-label="Selected invoice">
          {active ? (
            <>
              <Link to={locationFor(null)} navigate={navigate} className="queue-back text-link">
                <Icon name="back" size={18} />
                Back to review queue
              </Link>
              <RunView
                key={token + ':' + active}
                runId={active}
                token={token}
                navigate={navigate}
                notify={notify}
                reviewerToken={reviewerToken}
                embedded
              />
            </>
          ) : (
            <div className="empty-state queue-select-prompt">
              <Icon name="invoice" size={32} />
              <h2>Select an invoice</h2>
              <p>Read the document and review its next action here.</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
