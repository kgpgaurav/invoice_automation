import { type Run, type RunEvent, type Review } from './api';
import { Icon, Link, type Navigate } from './ui';
import InvoiceWorkspace from './InvoiceWorkspace';

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
  retryPDF,
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
  retryPDF?: () => void;
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
      <InvoiceWorkspace
        run={run}
        events={events}
        pdf={pdf}
        pdfError={pdfError}
        audience="finance"
        embedded
        connection={connection}
        reconnect={refresh}
        navigate={navigate}
        review={review}
        reviewerToken={reviewerToken}
        submitted={submitted}
        notify={notify}
        retryPDF={retryPDF}
      />
      <Link to={'?run=' + runId} navigate={navigate} className="text-link full-record-link">
        Open full invoice record <Icon name="arrow" size={16} />
      </Link>
    </div>
  );
}
