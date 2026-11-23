import type { Run } from './api';
import { money } from './api';

export default function ReviewComparisons({
  run,
  pdf,
  showPage,
}: {
  run: Run;
  pdf: string;
  showPage?: (page: number, field: string) => void;
}) {
  const rows = run.comparisons ?? [];
  if (!rows.length) return null;
  const issues = rows.filter((row) => ['different', 'missing', 'unverified'].includes(row.status));
  const rest = rows.filter((row) => !issues.includes(row));
  const labels = {
    matches: 'Values agree',
    different: 'Different values',
    missing: 'Missing',
    unverified: 'Source unverified',
    information: 'Context only',
  };
  const render = (items: typeof rows) => (
    <div className="comparison-list">
      {items.map((row) => (
        <div key={row.field} className={'comparison-row ' + row.status}>
          <div className="comparison-heading">
            <strong>{row.title}</strong>
            <span>{labels[row.status]}</span>
          </div>
          <dl>
            <div>
              <dt>Invoice</dt>
              <dd>{row.invoice_value ?? 'Not supplied'}</dd>
            </div>
            <div>
              <dt>{row.expected_label}</dt>
              <dd>{row.expected_value ?? 'Not established'}</dd>
            </div>
          </dl>
          <small>
            {row.source_verification === 'verified'
              ? 'Source matched to PDF'
              : row.source_verification === 'missing'
                ? 'Source value missing'
                : 'PDF source needs verification'}
            {' · '}
            {row.provenance === 'RECORDED_ASSESSMENT'
              ? 'Recorded at assessment'
              : row.provenance === 'CURRENT_MASTER'
                ? 'Current records'
                : 'Source evidence'}
          </small>
          {row.difference != null && row.status === 'different' && (
            <p>Difference: {row.currency ? money(row.difference, row.currency) : row.difference}</p>
          )}
          <p>{row.description}</p>
          {row.pages.map((page) =>
            showPage ? (
              <button className="text-link" key={page} onClick={() => showPage(page, row.field)}>
                View {row.title} source, page {page}
              </button>
            ) : pdf ? (
              <a
                className="text-link"
                key={page}
                href={`${pdf}#page=${page}`}
                target="_blank"
                rel="noreferrer"
              >
                Open source page {page}
              </a>
            ) : null,
          )}
        </div>
      ))}
    </div>
  );
  return (
    <section className="panel comparison-panel" aria-label="Invoice and PO comparison">
      <div className="panel-heading">
        <div>
          <h2>What needs checking</h2>
          <p>
            Compare the PDF with the records below. These comparisons do not authorize approval.
          </p>
        </div>
      </div>
      {issues.length ? (
        render(issues)
      ) : (
        <p className="empty-inline">
          No differences in these available comparisons. See the recorded decision and checks.
        </p>
      )}
      {!!rest.length && (
        <details className="disclosure">
          <summary>Other field comparisons ({rest.length})</summary>
          {render(rest)}
        </details>
      )}
    </section>
  );
}
