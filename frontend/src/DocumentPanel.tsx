import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Icon } from './ui';
const PDFPreview = lazy(() => import('./PDFPreview'));

export default function DocumentPanel({
  url,
  error,
  target,
  notice = '',
  onRetry,
}: {
  url: string;
  error: string;
  target?: { page: number; revision: number };
  notice?: string;
  onRetry?: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (expanded) {
      dialog.current?.showModal();
      closeButton.current?.focus();
    } else dialog.current?.close();
  }, [expanded]);
  const viewer = () => (
    <Suspense
      fallback={
        <p className="empty-inline" role="status">
          Loading PDF viewer…
        </p>
      }
    >
      <PDFPreview url={url} target={target} />
    </Suspense>
  );
  return (
    <section className="review-document" aria-label="Source document">
      <div className="review-document-heading">
        <h2>Original invoice</h2>
        <div>
          {url && (
            <a className="text-link" href={url} target="_blank" rel="noreferrer">
              Open PDF
            </a>
          )}
          <button className="text-link" disabled={!url} onClick={() => setExpanded(true)}>
            <Icon name="expand" size={16} />
            Expand PDF
          </button>
        </div>
      </div>
      <div className="document-viewport" tabIndex={0} aria-label="Scrollable original invoice">
        {url ? (
          viewer()
        ) : (
          <p className="empty-inline" role={error ? 'alert' : 'status'}>
            {error || 'Loading private PDF…'}
            {error && onRetry && (
              <button className="button quiet small" onClick={onRetry}>
                Retry PDF
              </button>
            )}
          </p>
        )}
      </div>
      <p className="document-caption" role="status">
        {notice ||
          'Inspect page references from a field’s evidence. Exact source highlighting is unavailable.'}
      </p>
      <dialog
        className="document-dialog"
        ref={dialog}
        aria-label="Expanded invoice PDF"
        onClose={() => setExpanded(false)}
      >
        <div className="review-document-heading">
          <h2>Original invoice</h2>
          <div>
            <a href={url} target="_blank" rel="noreferrer" className="text-link">
              Open PDF in new tab
            </a>
            <button
              className="icon-button"
              aria-label="Close expanded PDF"
              ref={closeButton}
              onClick={() => setExpanded(false)}
            >
              <Icon name="close" />
            </button>
          </div>
        </div>
        {expanded && <div className="expanded-document">{viewer()}</div>}
      </dialog>
    </section>
  );
}
