import type { Run } from './api';
import { money } from './api';
import { pretty, vendorStatusLabel } from './ui';
import { fieldId, relativeDifference } from './invoicePresentation';

export default function ReviewComparisons({
  run,
  pdf,
  showPage,
  inspectField,
}: {
  run: Run;
  pdf: string;
  showPage?: (page: number, field: string) => void;
  inspectField?: (field: string) => void;
}) {
  const rows = run.comparisons ?? [];
  const issues = rows.filter((row) => ['different', 'missing', 'unverified'].includes(row.status));
  const rest = rows.filter((row) => !issues.includes(row));
  const labels = {
    matches: 'Consistent',
    different: 'Different values',
    missing: 'Missing',
    unverified: 'Source unverified',
    information: 'Context only',
  };
  const render = (items: typeof rows) => (
    <div
      className="invoice-table-scroll"
      role="region"
      aria-label="Scrollable purchase-order comparison"
      tabIndex={0}
    >
      <table className="invoice-comparison-table">
        <caption className="sr-only">
          Invoice values compared with purchase-order and registered vendor data
        </caption>
        <thead>
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Invoice</th>
            <th scope="col">PO / registered record</th>
            <th scope="col">Difference</th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr
              key={row.field}
              id={'comparison-' + fieldId(row.field)}
              className={'comparison-row ' + row.status}
            >
              <th scope="row">
                <strong>{row.title}</strong>
                <details className="comparison-evidence">
                  <summary>Evidence & explanation</summary>
                  <p>{row.description}</p>
                  <p>
                    PDF evidence:{' '}
                    {row.source_verification === 'verified'
                      ? 'Verified'
                      : row.source_verification === 'missing'
                        ? 'Missing'
                        : 'Unverified'}
                    .
                  </p>
                  <p>
                    {row.provenance === 'RECORDED_ASSESSMENT'
                      ? 'Recorded at assessment.'
                      : row.provenance === 'CURRENT_MASTER'
                        ? 'Current records; may differ from assessment-time data.'
                        : 'Source evidence only.'}
                  </p>
                  {inspectField && (
                    <button className="text-link" onClick={() => inspectField(row.field)}>
                      Inspect extracted field
                    </button>
                  )}
                  {row.pages.map((page) =>
                    showPage ? (
                      <button
                        className="text-link"
                        key={page}
                        onClick={() => showPage(page, row.field)}
                      >
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
                </details>
              </th>
              <td>{row.invoice_value ?? <span className="empty-value">Not supplied</span>}</td>
              <td>
                {row.expected_value ?? <span className="empty-value">Unavailable</span>}
                <small>{row.expected_label}</small>
                <span className="comparison-context">
                  {row.provenance === 'RECORDED_ASSESSMENT'
                    ? 'At assessment'
                    : row.provenance === 'CURRENT_MASTER'
                      ? 'Current record'
                      : 'Source only'}
                </span>
              </td>
              <td className="amount">
                {row.difference == null
                  ? '—'
                  : row.currency
                    ? money(row.difference, row.currency)
                    : row.difference}
                {row.field.endsWith('.unit_price') &&
                  row.difference != null &&
                  relativeDifference(row.difference, row.expected_value) && (
                    <small title="Relative difference for display only; the recorded policy result is unchanged.">
                      {relativeDifference(row.difference, row.expected_value)} relative
                    </small>
                  )}
              </td>
              <td>
                <span className={'comparison-result ' + row.status}>{labels[row.status]}</span>
                {row.status === 'different' && row.source_verification === 'verified' && (
                  <small>PDF verified; values differ</small>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <section className="comparison-panel" aria-label="Invoice and PO comparison">
      <div className="panel-heading">
        <div>
          <h2>What needs checking</h2>
          <p>Source verification and agreement with procurement records are separate checks.</p>
        </div>
      </div>
      <div className="po-context-strip">
        <strong>{run.purchase_order?.po_number ?? 'No supporting PO established'}</strong>
        <small>
          {run.purchase_order?.relationship === 'PRINTED_REFERENCE'
            ? 'Printed reference only; not a verified match'
            : run.purchase_order
              ? 'See each row for recorded or current context'
              : 'Use an offered review action to resolve missing PO information'}
        </small>
      </div>
      <dl className="comparison-master-context">
        <div>
          <dt>Matched supplier</dt>
          <dd>{run.vendor?.name ?? 'Not established'}</dd>
        </div>
        <div>
          <dt>Supplier status now</dt>
          <dd>{run.vendor ? vendorStatusLabel(run.vendor.status) : 'Unavailable'}</dd>
        </div>
        <div>
          <dt>PO status now</dt>
          <dd>{run.purchase_order ? pretty(run.purchase_order.status) : 'Unavailable'}</dd>
        </div>
      </dl>
      {issues.length ? (
        render(issues)
      ) : (
        <p className="empty-inline">
          {rows.length
            ? 'No issues in these available comparisons. See the recorded decision and checks.'
            : 'No comparable purchase-order data is available in this record.'}
        </p>
      )}
      {!!rest.length && (
        <details className="disclosure comparison-other" open={!issues.length}>
          <summary>Other field comparisons ({rest.length})</summary>
          {render(rest)}
        </details>
      )}
      <p className="invoice-source-note">
        Unavailable information is not a mismatch. Context-only rows do not establish that a
        financial check passed.
      </p>
    </section>
  );
}
