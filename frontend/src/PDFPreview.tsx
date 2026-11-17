import { useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { errorMessage } from './api';

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PDFPreview({
  url,
  target,
}: {
  url: string;
  target?: { page: number; revision: number };
}) {
  const container = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1),
    [width, setWidth] = useState(0),
    [error, setError] = useState('');
  const [rendered, setRendered] = useState(false);
  useEffect(() => {
    if (
      document &&
      target &&
      Number.isInteger(target.page) &&
      target.page >= 1 &&
      target.page <= document.numPages
    )
      setPage(target.page);
  }, [document, target]);
  useEffect(() => {
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(100, entries[0].contentRect.width - 32)),
    );
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    setDocument(null);
    setPage(1);
    setError('');
    const task = getDocument({ url });
    let active = true;
    task.promise
      .then((value) => {
        if (active) setDocument(value);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
      void task.destroy().catch(() => {});
    };
  }, [url]);
  useEffect(() => {
    if (!document || !width || !canvas.current) return;
    let active = true,
      task: ReturnType<Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']> | undefined;
    setRendered(false);
    document
      .getPage(page)
      .then((pdfPage) => {
        if (!active || !canvas.current) return;
        const scale = width / pdfPage.getViewport({ scale: 1 }).width;
        const viewport = pdfPage.getViewport({ scale: scale * Math.min(devicePixelRatio, 2) });
        const target = canvas.current;
        target.width = Math.ceil(viewport.width);
        target.height = Math.ceil(viewport.height);
        target.style.width = `${width}px`;
        target.style.height = `${viewport.height / Math.min(devicePixelRatio, 2)}px`;
        const context = target.getContext('2d');
        if (!context) throw new Error('PDF canvas unavailable. Use Open PDF to view the original.');
        task = pdfPage.render({ canvas: target, canvasContext: context, viewport });
        return task.promise;
      })
      .then(() => {
        if (active) setRendered(true);
      })
      .catch((e) => {
        if (active) setError(errorMessage(e));
      });
    return () => {
      active = false;
      task?.cancel();
    };
  }, [document, page, width]);
  return (
    <div className="pdf-preview" ref={container}>
      {document?.numPages !== 1 && (
        <div className="pdf-toolbar">
          <button
            className="button quiet small"
            disabled={!document || page <= 1}
            onClick={() => setPage((n) => n - 1)}
          >
            Previous page
          </button>
          <span>
            Page {page} / {document?.numPages ?? '—'}
          </span>
          <button
            className="button quiet small"
            disabled={!document || page >= document.numPages}
            onClick={() => setPage((n) => n + 1)}
          >
            Next page
          </button>
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <canvas
        ref={canvas}
        role="img"
        aria-label={`Invoice PDF preview, page ${page}`}
        data-rendered={rendered ? 'true' : 'false'}
      />
      {!rendered && !error && <p className="empty-inline">Rendering original PDF…</p>}
    </div>
  );
}
