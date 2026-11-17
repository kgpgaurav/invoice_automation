import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Icon } from './ui';
const PDFPreview = lazy(() => import('./PDFPreview'));

export default function DocumentPanel({ url, error }: { url: string; error: string }) {
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
      <PDFPreview url={url} />
    </Suspense>
  );
  return (
    <section className="review-document" aria-label="Source document">
      <div className="review-document-heading">
        <h2>Original invoice</h2>
        <button className="text-link" disabled={!url} onClick={() => setExpanded(true)}>
          <Icon name="expand" size={16} />
          Expand PDF
        </button>
      </div>
      <div className="document-viewport" tabIndex={0} aria-label="Scrollable original invoice">
        {url ? (
          viewer()
        ) : (
          <p className="empty-inline" role={error ? 'alert' : 'status'}>
            {error || 'Loading private PDF…'}
          </p>
        )}
      </div>
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
