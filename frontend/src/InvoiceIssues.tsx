import type { Run } from './api';
import { money } from './api';
import { Icon } from './ui';
import { financialIssue, type InvoiceTab } from './invoicePresentation';

export default function InvoiceIssues({
  run,
  inspect,
}: {
  run: Run;
  inspect: (tab: InvoiceTab) => void;
}) {
  const issues = run.checks.filter((check) => financialIssue(check.status));
  if (!issues.length) return null;
  const comparisons = run.comparisons ?? [];
  return (
    <section className="invoice-issues" aria-label="Issues requiring attention">
      <div className="invoice-section-heading">
        <h2>
          <Icon name="alert" size={17} /> Issues requiring attention{' '}
          <span className="item-count">{issues.length}</span>
        </h2>
        <button className="text-link" onClick={() => inspect('checks')}>
          Inspect checks
        </button>
      </div>
      <ul>
        {issues.slice(0, 3).map((check) => {
          const relevant = comparisons.find(
            (row) =>
              row.status === 'different' &&
              (check.rule_id.includes('VENDOR')
                ? row.field.startsWith('vendor_')
                : check.rule_id === 'PO_BALANCE'
                  ? row.field === 'total_gross'
                  : check.rule_id.includes('PRICE')
                    ? row.field.endsWith('.unit_price')
                    : check.rule_id.includes('TAX')
                      ? row.field.includes('tax')
                      : check.rule_id.includes('QUANTITY')
                        ? row.field.endsWith('.quantity')
                        : false),
          );
          return (
            <li key={check.rule_id}>
              <div>
                <strong>{check.title}</strong>
                <span className="issue-severity">
                  {check.status === 'failed' ? 'Failed check' : 'Review required'}
                </span>
              </div>
              <p>{check.description}</p>
              {relevant && (
                <p className="issue-values">
                  Invoice: <strong>{relevant.invoice_value ?? 'Missing'}</strong>
                  <span>
                    {relevant.expected_label}:{' '}
                    <strong>{relevant.expected_value ?? 'Unavailable'}</strong>
                  </span>
                  {relevant.difference != null && (
                    <span>
                      Difference:{' '}
                      <strong>
                        {relevant.currency
                          ? money(relevant.difference, relevant.currency)
                          : relevant.difference}
                      </strong>
                    </span>
                  )}
                  <button className="text-link" onClick={() => inspect('comparison')}>
                    Compare values
                  </button>
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {issues.length > 3 && (
        <button className="text-link remaining-issues" onClick={() => inspect('checks')}>
          Inspect {issues.length - 3} more recorded issues
        </button>
      )}
    </section>
  );
}
