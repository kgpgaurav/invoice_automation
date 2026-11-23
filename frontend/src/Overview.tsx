import { useEffect, useState } from 'react';
import { api, duration, errorMessage, money, type Summary } from './api';
import { Link, type Navigate } from './ui';
import DemoReset from './DemoReset';
export default function Overview({
  token,
  navigate,
  canReset = false,
}: {
  token: string;
  navigate: Navigate;
  canReset?: boolean;
}) {
  const [data, setData] = useState<Summary | null>(null),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    setData(null);
    setError('');
    if (!token) return;
    const controller = new AbortController();
    api<Summary>('/dashboard/summary', token, { signal: controller.signal })
      .then((s) => {
        if (!controller.signal.aborted) setData(s);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorMessage(e));
      });
    return () => controller.abort();
  }, [token, revision]);
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Overview</h1>
          <p>
            Routine invoices move forward. Exceptions arrive with the reason and supporting numbers.
          </p>
        </div>
        <button className="button quiet" onClick={() => setRevision((n) => n + 1)}>
          Refresh overview
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!token ? (
        <div className="panel empty-state">
          Connect your workspace to see recorded operational measures.
        </div>
      ) : !data ? (
        <div className="panel empty-state" role="status">
          {error ? 'Overview unavailable. Retry above.' : 'Loading operational measures…'}
        </div>
      ) : (
        <>
          {(data.mock_runs > 0 || data.replay_runs > 0) && (
            <div className="mode-banner">
              <strong>DEMO DATA INCLUDED</strong> {data.mock_runs} mocked-extraction runs ·{' '}
              {data.replay_runs} replay runs · {data.live_runs} live-extraction runs. These measures
              include fixture activity.
            </div>
          )}
          <div className="metric-strip">
            {[
              ['Total processed', data.total_processed, 'Approved + rejected'],
              ['Approved', data.approved, 'Authorized, never paid'],
              ['Needs review', data.awaiting_review, 'No funds reserved'],
              ['Rejected', data.rejected, 'No new allocation'],
            ].map(([label, count, detail]) => (
              <section key={label}>
                <span>{label}</span>
                <strong>{count}</strong>
                <small>{detail}</small>
              </section>
            ))}
          </div>
          <section className="panel operational-summary">
            <div className="panel-heading">
              <div>
                <h2>How invoices move through</h2>
                <p>Recorded runs, with explicit measurement coverage.</p>
              </div>
              <Link to="?view=review" navigate={navigate} className="text-link">
                Open Review queue →
              </Link>
            </div>
            <dl className="overview-measures">
              <div>
                <dt>Straight-through processing rate</dt>
                <dd>
                  {data.straight_through_rate_pct == null
                    ? 'Not measured'
                    : data.straight_through_rate_pct + '%'}
                  <small>
                    {data.straight_through_approved} approved without any review /{' '}
                    {data.automation_eligible_runs} eligible runs
                  </small>
                </dd>
              </div>
              <div>
                <dt>Average processing time</dt>
                <dd>
                  {duration(data.average_processing_ms)}
                  <small>
                    {data.processing_time_sample_count} measured runs · queue and review wait
                    excluded
                  </small>
                </dd>
              </div>
              <div>
                <dt>Estimated API cost</dt>
                <dd>
                  {data.estimated_api_cost_usd == null
                    ? 'Unknown'
                    : 'USD ' + data.estimated_api_cost_usd}
                  <small>
                    {data.estimated_cost_known_runs} costed · {data.estimated_cost_unknown_runs}{' '}
                    unknown · actual billing unavailable
                  </small>
                </dd>
              </div>
              <div>
                <dt>Potential PO overrun flagged</dt>
                <dd className="review-text">
                  {money(data.potential_po_overrun_inr)}
                  <small>
                    {data.overrun_known_identities} distinct current holds ·{' '}
                    {data.overrun_unknown_identities} unknown amounts · not realized savings
                  </small>
                </dd>
              </div>
            </dl>
            <details className="disclosure">
              <summary>Metric definitions & coverage</summary>
              <p>
                Straight-through rate uses workflow runs with a final approved/rejected decision or
                a current review hold. The numerator excludes every run with a recorded review
                request, including resolved reviews. Unstarted, failed, stopped and unknown workflow
                records are excluded. This is a run-level measure, not a deduplicated invoice or
                labor-savings measure.
              </p>
              <p>{data.metrics_notice}</p>
              <p>
                {data.total_runs} total runs · {data.active} active · {data.failed} processing
                failures. Mock activity has no live API cost; missing live costs remain unknown.
              </p>
            </details>
          </section>
        </>
      )}
      {canReset && <DemoReset token={token} onReset={() => setRevision((n) => n + 1)} />}
    </>
  );
}
