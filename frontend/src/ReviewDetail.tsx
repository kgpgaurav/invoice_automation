import { dateTime, money, type Run, type RunEvent, type Review } from './api';
import { Badge, Icon, Link, Mode, fieldLabel, type Navigate } from './ui';
import DocumentPanel from './DocumentPanel';
import ReviewForm from './ReviewForm';
import InvoiceDecision from './InvoiceDecision';
import RuleChecklist from './RuleChecklist';
import BusinessTimeline from './BusinessTimeline';
import ReviewComparisons from './ReviewComparisons';

export default function ReviewDetail({
  run,
  runId,
  events,
  review,
  pdf,
  pdfError,
  error,
  refresh,
  submitted,
  notify,
  reviewerToken,
  navigate,
  connection,
}: {
  run: Run | null;
  runId: string;
  events: RunEvent[];
  review: Review | null;
  pdf: string;
  pdfError: string;
  error: string;
  refresh: () => void;
  submitted: () => void;
  notify: (s: string) => void;
  reviewerToken?: string;
  navigate: Navigate;
  connection: string;
}) {
  if (!run)
    return (
      <div className="empty-state" role={error ? 'alert' : 'status'}>
        {error || 'Loading invoice details…'}
        {error && (
          <button className="button quiet small" onClick={refresh}>
            Retry
          </button>
        )}
      </div>
    );
  const vendor = run.fields.find((f) => f.field === 'vendor_name')?.value ?? run.vendor?.name;
  const invoiceDate = run.fields.find((f) => f.field === 'invoice_date')?.value;
  return (
    <div className="review-detail-content">
      {error && (
        <div className="error" role="alert">
          {error}
          <button className="text-link" onClick={refresh}>
            Retry
          </button>
        </div>
      )}
      <div className="selected-invoice-heading">
        <div>
          <h2>{run.invoice_number ?? 'Invoice details'}</h2>
          <p>{vendor ?? 'Supplier not extracted'}</p>
        </div>
        <strong className="amount">{money(run.invoice_total, run.invoice_currency ?? '')}</strong>
      </div>
      <p className="invoice-dates">
        Invoice date: {invoiceDate ?? 'Not extracted'}
        <span>Received: {dateTime(run.created_at)}</span>
      </p>
      <div className="selected-provenance">
        <Mode value={run.source_mode} />
        {run.replay_mode && run.source_mode !== 'DEMO_REPLAY' && <Mode value="DEMO_REPLAY" />}
        {run.job_state !== 'WAITING_REVIEW' && <Badge value={run.decision ?? run.job_state} />}
      </div>
      {review?.kind === 'PO_SELECTION' ? (
        <div className="review-exception" role="note">
          <Icon name="alert" size={24} />
          <div>
            <h2>Purchase order required</h2>
            <p>Select the purchase order supported by this invoice.</p>
          </div>
        </div>
      ) : (
        <InvoiceDecision run={run} navigate={navigate} />
      )}
      <DocumentPanel url={pdf} error={pdfError} />
      <ReviewComparisons run={run} pdf={pdf} />
      {review ? (
        <ReviewForm
          key={review.review_request_id}
          review={review}
          reasonCode={run.reason_code}
          authorizedToken={reviewerToken}
          onRefresh={refresh}
          onSubmitted={submitted}
          notify={notify}
          compact
        />
      ) : (
        <div className="review-next-step">
          <h2>
            {run.job_state === 'QUEUED' || run.job_state === 'RUNNING'
              ? 'Validation in progress'
              : 'No open review action'}
          </h2>
          <p>
            {run.job_state === 'QUEUED' || run.job_state === 'RUNNING'
              ? 'Processing is queued or underway. Current requirements will be checked before a decision is recorded.'
              : 'This record has no review action available. See the current outcome and processing record.'}
          </p>
        </div>
      )}
      <RuleChecklist run={run} />
      <details className="review-evidence">
        <summary>Extracted fields & source evidence</summary>
        <dl className="review-field-list">
          {run.fields.map((field) => (
            <div key={field.field}>
              <dt>
                {fieldLabel(field.field)}
                {field.required_for_approval === false && ' · optional'}
              </dt>
              <dd>
                {field.value ??
                  (field.required_for_approval === false ? 'Not supplied' : 'Missing')}
                <small>
                  {field.origin === 'derived'
                    ? 'Calculated locally from printed values'
                    : field.verification === 'verified'
                      ? 'Matched to PDF text'
                      : field.verification === 'missing' && field.required_for_approval === false
                        ? 'Optional field'
                        : field.verification === 'missing'
                          ? 'Required information missing'
                          : 'Source needs verification'}
                  {field.pages.length > 0 && ' · page ' + field.pages.join(', ')}
                </small>
                {field.calculation && <small>{field.calculation}</small>}
              </dd>
            </div>
          ))}
        </dl>
      </details>
      <details className="review-evidence">
        <summary>Processing record</summary>
        <BusinessTimeline
          run={run}
          events={events}
          connection={connection}
          reconnect={refresh}
          technical={false}
        />
      </details>
      <Link to={'?run=' + runId} navigate={navigate} className="text-link full-record-link">
        Open full invoice record
        <Icon name="arrow" size={16} />
      </Link>
    </div>
  );
}
