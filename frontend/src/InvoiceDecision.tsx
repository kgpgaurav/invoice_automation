import { money, type Run } from './api';
import { Icon, Link, reasonLabel, type Navigate } from './ui';

export default function InvoiceDecision({ run, navigate }: { run: Run; navigate: Navigate }) {
  const outcome = run.decision ?? run.job_state;
  const title =
    outcome === 'APPROVED'
      ? 'Approved for downstream processing'
      : outcome === 'NEEDS_REVIEW'
        ? 'Review required'
        : outcome === 'REJECTED'
          ? 'Invoice rejected'
          : outcome === 'FAILED'
            ? 'Processing could not complete'
            : outcome === 'INTERRUPTED'
              ? run.reason_code === 'REQUEST_INFO'
                ? 'Source information requested'
                : 'Processing stopped'
              : outcome === 'RUNNING'
                ? 'Invoice is processing'
                : 'Queued for processing';
  const explanation =
    run.processing_failure?.message ??
    run.decision_reason ??
    run.business_explanation ??
    (outcome === 'FAILED'
      ? 'A technical error stopped processing. This is not a financial rejection.'
      : outcome === 'QUEUED'
        ? 'The PDF is stored and waiting for the configured worker.'
        : outcome === 'RUNNING'
          ? 'Reading and checking the document. No approval has been recorded.'
          : outcome === 'INTERRUPTED'
            ? 'Processing stopped without an approval. Inspect the record for the next step.'
            : outcome === 'REJECTED'
              ? 'A financial rejection was recorded. Inspect the assessment and audit record for its reason.'
              : 'Critical evidence needs review before the invoice can move forward.');
  const observed = run.decision_observations;
  const matched = run.purchase_order && run.purchase_order.relationship !== 'PRINTED_REFERENCE';
  return (
    <section className={'decision-banner ' + outcome.toLowerCase()} aria-label="Financial decision">
      <div className="decision-title">
        <span className="decision-icon">
          <Icon
            name={
              outcome === 'APPROVED'
                ? 'check'
                : outcome === 'NEEDS_REVIEW' || outcome === 'FAILED' || outcome === 'REJECTED'
                  ? 'alert'
                  : 'clock'
            }
            size={24}
          />
        </span>
        <div>
          <p className="eyebrow">
            {outcome === 'FAILED'
              ? 'TECHNICAL FAILURE'
              : outcome === 'APPROVED'
                ? 'APPROVAL RECORDED'
                : outcome === 'REJECTED'
                  ? 'FINANCIAL DECISION'
                  : 'CURRENT POSITION'}
          </p>
          <h2>{title}</h2>
          <p>{explanation}</p>
        </div>
        {run.approved_gross && (
          <div className="approved-amount">
            <small>Authorized amount</small>
            <strong>{money(run.approved_gross, run.invoice_currency ?? '')}</strong>
            <small>No payment executed</small>
          </div>
        )}
      </div>
      {run.processing_failure && (
        <div className="processing-help">
          <strong>What to do next</strong>
          <p>{run.processing_failure.next_action}</p>
          <small>No invoice classification or financial decision was made.</small>
        </div>
      )}
      {run.reason_code === 'PO_CAP_EXCEEDED' && observed && observed.cap_gross && (
        <div className="balance-breakdown" aria-label="Balance at assessment">
          <p>
            Balance at assessment <span className="mono">{observed.po_number}</span>
          </p>
          <dl>
            <div>
              <dt>PO authorized</dt>
              <dd>{money(observed.cap_gross, observed.currency)}</dd>
            </div>
            <div>
              <dt>Previously approved</dt>
              <dd>−{money(observed.committed_gross, observed.currency)}</dd>
            </div>
            <div className="balance-subtotal">
              <dt>Remaining balance</dt>
              <dd>{money(observed.remaining_gross, observed.currency)}</dd>
            </div>
            <div>
              <dt>Current invoice</dt>
              <dd>{money(observed.requested_gross, observed.currency)}</dd>
            </div>
            {run.reason_code === 'PO_CAP_EXCEEDED' && (
              <div className="balance-excess">
                <dt>Amount exceeding balance</dt>
                <dd>{money(observed.excess_gross, observed.currency)}</dd>
              </div>
            )}
          </dl>
          <small>Recorded before this decision. Current master values may differ.</small>
        </div>
      )}
      <div className="decision-actions">
        {run.review_request_id && (
          <a href="#human-review" className="button small">
            Resolve exception <Icon name="arrow" size={15} />
          </a>
        )}
        {matched && (
          <Link to={'?po=' + run.purchase_order!.po_id} navigate={navigate} className="text-link">
            Inspect PO ledger →
          </Link>
        )}
        <span>
          {outcome === 'APPROVED'
            ? 'Allocated once; payment execution is outside this product.'
            : outcome === 'NEEDS_REVIEW'
              ? 'No funds posted or reserved.'
              : outcome === 'REJECTED'
                ? 'No new allocation posted.'
                : 'No approval is implied by a processing state.'}
        </span>
      </div>
      {run.reason_code && <span className="sr-only">{reasonLabel(run.reason_code)}</span>}
    </section>
  );
}
