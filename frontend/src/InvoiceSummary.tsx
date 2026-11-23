import { money, dateTime } from './api';
import { Badge, Mode, Icon, pretty } from './ui';
import {
  fieldValue,
  unresolved,
  financialIssue,
  type InvoiceRecord,
  type InvoiceTab,
} from './invoicePresentation';

export default function InvoiceSummary({
  run,
  embedded = false,
  inspect,
}: {
  run: InvoiceRecord;
  embedded?: boolean;
  inspect: (tab: InvoiceTab) => void;
}) {
  const Title = embedded ? 'h2' : 'h1';
  const finance = 'checks' in run ? run : null;
  const missing = run.fields.filter(
    (field) => field.required_for_approval && unresolved(field),
  ).length;
  const required = run.fields.filter((field) => field.required_for_approval);
  const sourceCheck = finance?.checks.find((check) => check.rule_id === 'SOURCE_EVIDENCE');
  const extractionCheck = finance?.checks.find((check) => check.rule_id === 'REQUIRED_FIELDS');
  const source =
    sourceCheck?.status === 'passed'
      ? 'Verified'
      : sourceCheck && financialIssue(sourceCheck.status)
        ? 'Needs review'
        : required.length && required.every((field) => field.verification === 'verified')
          ? 'Verified fields'
          : run.fields.length
            ? 'Unverified fields'
            : 'Pending';
  const extraction =
    missing > 0
      ? 'Incomplete'
      : extractionCheck?.status === 'passed'
        ? 'Complete'
        : extractionCheck && financialIssue(extractionCheck.status)
          ? 'Incomplete'
          : run.fields.length
            ? 'Saved'
            : 'Pending';
  const issues = finance?.checks.filter((check) => financialIssue(check.status)) ?? [];
  const printedPO = fieldValue(run, 'po_reference');
  const po = finance?.purchase_order;
  const selected = po && po.relationship !== 'PRINTED_REFERENCE';
  const poStatus = selected ? 'Matched' : printedPO ? 'Reference only' : 'Needs selection';
  return (
    <header className="invoice-summary" aria-label="Invoice summary">
      <div className="invoice-summary-main">
        <div>
          <div className="invoice-summary-ident">
            <Title>{run.invoice_number ?? 'Invoice details'}</Title>
            <Mode value={run.source_mode} />
          </div>
          <p>{fieldValue(run, 'vendor_name') ?? 'Supplier not extracted'}</p>
        </div>
        <div className="invoice-summary-total">
          <strong>{money(run.invoice_total, run.invoice_currency ?? '')}</strong>
          <div
            role="group"
            aria-label={`Processing: ${pretty(run.job_state)}. Decision: ${run.decision ? pretty(run.decision) : 'Not recorded'}.`}
          >
            <Badge value={run.job_state} />
            {run.decision && pretty(run.decision) !== pretty(run.job_state) && (
              <Badge value={run.decision} />
            )}
          </div>
        </div>
      </div>
      <dl className="invoice-summary-meta">
        <div>
          <dt>Invoice date</dt>
          <dd>{fieldValue(run, 'invoice_date') ?? 'Not extracted'}</dd>
        </div>
        <div>
          <dt>{printedPO ? 'Printed PO' : selected ? 'Selected PO' : 'PO reference'}</dt>
          <dd>{printedPO ?? (selected ? po.po_number : 'Not supplied')}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{dateTime(run.created_at)}</dd>
        </div>
        <div>
          <dt>Record</dt>
          <dd className="short-record" title={run.run_id}>
            {run.run_id.slice(0, 8)}
          </dd>
        </div>
      </dl>
      <div className="invoice-indicators" aria-label="Invoice verification summary">
        <button
          onClick={() => inspect('data')}
          title="Saved extraction and source verification are separate."
        >
          <Icon name="file" size={14} /> Extraction <strong>{extraction}</strong>
        </button>
        <button onClick={() => inspect('data')}>
          <Icon name="shield" size={14} /> Evidence <strong>{source}</strong>
        </button>
        <button onClick={() => inspect(finance ? 'comparison' : 'data')}>
          <Icon name="cart" size={14} /> PO{' '}
          <strong>{finance ? poStatus : printedPO ? 'Printed reference' : 'Not supplied'}</strong>
        </button>
        <button
          className={missing ? 'indicator-issue' : ''}
          onClick={() => inspect('data')}
          title="Counts unresolved required fields returned in the saved record; other requirements appear in the financial checks."
        >
          Missing required <strong>{run.fields.length ? missing : 'Not assessed'}</strong>
        </button>
        {finance && (
          <button
            className={issues.length ? 'indicator-issue' : ''}
            onClick={() => inspect('checks')}
          >
            Rule issues <strong>{finance.checks.length ? issues.length : 'Not assessed'}</strong>
          </button>
        )}
        {run.job_state === 'WAITING_REVIEW' && (
          <span className="review-needed">
            <Icon name="alert" size={14} /> Financial review required
          </span>
        )}
      </div>
    </header>
  );
}
