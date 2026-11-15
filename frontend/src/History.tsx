import { useEffect, useState } from 'react';
import { api, dateTime, errorMessage, money, type RunPage } from './api';
import { Badge, Icon, Link, Mode, pretty, reasonLabel, type Navigate } from './ui';

export default function History({
  token,
  params,
  navigate,
  queue = false,
  ownOnly = false,
  canUpload = true,
}: {
  token: string;
  params: URLSearchParams;
  navigate: Navigate;
  queue?: boolean;
  ownOnly?: boolean;
  canUpload?: boolean;
}) {
  const [page, setPage] = useState<RunPage | null>(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [revision, setRevision] = useState(0),
    [previous, setPrevious] = useState<string[]>([]);
  const state = queue ? 'WAITING_REVIEW' : (params.get('state') ?? ''),
    decision = queue ? '' : (params.get('decision') ?? ''),
    cursor = params.get('cursor') ?? '',
    q = params.get('q') ?? '';
  const [search, setSearch] = useState(q);
  useEffect(() => setSearch(q), [q]);
  useEffect(() => {
    setPage(null);
    setError('');
    if (!token) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const query = new URLSearchParams({ limit: '10' });
    if (state) query.set('state', state);
    if (decision) query.set('decision', decision);
    if (cursor) query.set('cursor', cursor);
    if (q) query.set('q', q);
    api<RunPage>('/runs?' + query, token, { signal: controller.signal })
      .then((p) => {
        if (!controller.signal.aborted) setPage(p);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, state, decision, cursor, q, revision]);
  function filter(s: string, d: string, c = '', searchValue = q) {
    const query = new URLSearchParams({ view: queue ? 'review' : 'history' });
    if (!queue && s) query.set('state', s);
    if (d) query.set('decision', d);
    if (c) query.set('cursor', c);
    if (searchValue) query.set('q', searchValue);
    navigate('?' + query);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{queue ? 'EXCEPTION MANAGEMENT' : 'INVOICE REGISTER'}</p>
          <h1>{queue ? 'Review Queue' : ownOnly ? 'My Invoices' : 'Invoice History'}</h1>
          <p>
            {queue
              ? 'The invoices that need your judgment, with the reason and next action.'
              : ownOnly
                ? 'Your submitted invoices, processing status and decisions.'
                : 'Every invoice, its decision and the record behind it.'}
          </p>
        </div>
        {canUpload && (
          <Link to="?view=upload" navigate={navigate} className="button">
            <Icon name="upload" size={17} />
            Process Invoice
          </Link>
        )}
      </div>
      {queue && (
        <div className="queue-context">
          <span className="queue-number">{page?.total_count ?? '—'}</span>
          <div>
            <strong>invoices awaiting review</strong>
            <p>
              No funds are reserved while an invoice is held. Review does not permit a
              spending-limit override.
            </p>
          </div>
        </div>
      )}
      <section
        className="panel history-panel"
        aria-label={queue ? 'Review items' : 'Invoice history'}
      >
        <div className="panel-heading">
          <div>
            <h2>
              {queue ? 'Needs your attention' : ownOnly ? 'Your invoices' : 'All invoices'}{' '}
              <span className="count">{page?.total_count ?? '—'}</span>
            </h2>
            <p>
              {queue
                ? 'Open an exception to inspect its document and permitted actions.'
                : 'Dates reflect actual processing records. Amounts remain unknown until extracted.'}
            </p>
          </div>
          <button
            className="icon-button"
            onClick={() => setRevision((n) => n + 1)}
            aria-label="Refresh history"
          >
            <Icon name="refresh" size={17} />
          </button>
        </div>
        <div className="filters">
          <form
            className="search-form"
            onSubmit={(e) => {
              e.preventDefault();
              setPrevious([]);
              filter(state, decision, '', search.trim());
            }}
          >
            <label className="sr-only" htmlFor="invoice-search">
              Search invoices
            </label>
            <input
              id="invoice-search"
              type="search"
              value={search}
              maxLength={120}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Invoice, vendor or run ID"
            />
            <button className="button quiet small">Search</button>
          </form>
          {!queue && (
            <>
              <label>
                Status
                <select
                  aria-label="Status"
                  value={state}
                  onChange={(e) => {
                    setPrevious([]);
                    filter(e.target.value, decision);
                  }}
                >
                  <option value="">All statuses</option>
                  {[
                    'QUEUED',
                    'RUNNING',
                    'WAITING_REVIEW',
                    'COMPLETED',
                    'FAILED',
                    'INTERRUPTED',
                  ].map((s) => (
                    <option value={s} key={s}>
                      {pretty(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Decision
                <select
                  aria-label="Decision"
                  value={decision}
                  onChange={(e) => {
                    setPrevious([]);
                    filter(state, e.target.value);
                  }}
                >
                  <option value="">All decisions</option>
                  {['APPROVED', 'NEEDS_REVIEW', 'REJECTED'].map((s) => (
                    <option value={s} key={s}>
                      {pretty(s)}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
        </div>
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
            Loading invoice records…
          </div>
        ) : !page?.items.length ? (
          <div className="empty-state">
            <Icon name={queue ? 'check' : 'file'} size={30} />
            <h3>
              {!token
                ? 'Your workspace is private.'
                : error
                  ? 'Invoice records could not be loaded.'
                  : queue && !q
                    ? 'Your review queue is clear.'
                    : 'No matching invoices.'}
            </h3>
            <p>
              {!token
                ? 'Connect above to view invoices.'
                : q || state || decision
                  ? 'Change the search or filters to see more records.'
                  : canUpload
                    ? 'Process an invoice to start a document and decision record.'
                    : 'Submitted invoices will appear here.'}
            </p>
            {canUpload && (
              <Link to="?view=upload" navigate={navigate} className="text-link">
                Process Invoice <Icon name="arrow" size={16} />
              </Link>
            )}
          </div>
        ) : (
          <div className="table-scroll" tabIndex={0} aria-label="Scrollable invoice table">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Invoice / vendor</th>
                  <th className="amount">Amount</th>
                  <th>{queue ? 'Reason for review' : 'Decision & status'}</th>
                  <th>{queue ? 'Received' : 'Last updated'}</th>
                  {!queue && <th className="amount">Est. API cost</th>}
                  <th>
                    <span className="sr-only">Next action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((run) => (
                  <tr key={run.run_id}>
                    <td>
                      <Link to={'?run=' + run.run_id} navigate={navigate} className="invoice-link">
                        <span className="doc-icon">
                          <Icon name="file" size={18} />
                        </span>
                        <span>
                          <strong className="mono">
                            {run.invoice_number ?? 'Run ' + run.run_id.slice(0, 8)}
                          </strong>
                          <small>{run.vendor_name ?? 'Supplier not extracted'}</small>
                          <Mode value={run.source_mode} />
                        </span>
                      </Link>
                      <span className="run-reference">Run {run.run_id.slice(0, 8)}</span>
                    </td>
                    <td className="amount">{money(run.total_gross, run.currency ?? '')}</td>
                    <td>
                      {queue ? (
                        <>
                          <strong className="review-reason">{reasonLabel(run.reason_code)}</strong>
                          <Badge value={run.job_state} />
                        </>
                      ) : (
                        <>
                          <Badge value={run.decision ?? run.job_state} />
                          <small className="cell-detail">
                            {run.processing_failure?.message ??
                              (run.decision ? pretty(run.job_state) : 'No financial decision')}
                          </small>
                        </>
                      )}
                    </td>
                    <td className="date-cell">
                      {dateTime(queue ? run.created_at : (run.updated_at ?? run.created_at))}
                    </td>
                    {!queue && (
                      <td className="amount">
                        {run.source_mode === 'MOCK_OPENAI' ? (
                          <span className="muted">Mock · N/A</span>
                        ) : run.estimated_api_cost_usd != null ? (
                          'USD ' + run.estimated_api_cost_usd
                        ) : (
                          'Unknown'
                        )}
                      </td>
                    )}
                    <td>
                      <Link to={'?run=' + run.run_id} navigate={navigate} className="row-action">
                        {queue ? 'Review invoice' : 'View'}
                        <Icon name="chevron" size={14} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <span>
            {queue
              ? 'Only current open review items.'
              : 'Search covers invoice number, vendor and run ID. Original filenames are not retained.'}
          </span>
          <div>
            <button
              className="button quiet small"
              disabled={!previous.length || loading}
              onClick={() => {
                const p = previous.at(-1) ?? '';
                setPrevious((v) => v.slice(0, -1));
                filter(state, decision, p);
              }}
            >
              Previous
            </button>
            <button
              className="button quiet small"
              disabled={!page?.next_cursor || loading}
              onClick={() => {
                setPrevious((v) => [...v, cursor]);
                filter(state, decision, page?.next_cursor ?? '');
              }}
            >
              Next <Icon name="chevron" size={14} />
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
