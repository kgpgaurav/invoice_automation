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
  const [zoom, setZoom] = useState(100);
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
    setZoom(100);
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
        const displayWidth = (width * zoom) / 100;
        const scale = displayWidth / pdfPage.getViewport({ scale: 1 }).width;
        const viewport = pdfPage.getViewport({ scale: scale * Math.min(devicePixelRatio, 2) });
        const target = canvas.current;
        target.width = Math.ceil(viewport.width);
        target.height = Math.ceil(viewport.height);
        target.style.width = `${displayWidth}px`;
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
  }, [document, page, width, zoom]);
  return (
    <div className="pdf-preview" ref={container}>
      <div className="pdf-toolbar" aria-label="PDF controls">
        <div className="pdf-page-controls">
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
        <div className="pdf-zoom-controls">
          <button
            className="button quiet small"
            aria-label="Zoom out"
            disabled={zoom <= 50}
            onClick={() => setZoom((value) => Math.max(50, value - 25))}
          >
            −
          </button>
          <output aria-label="PDF zoom">{zoom}%</output>
          <button
            className="button quiet small"
            aria-label="Zoom in"
            disabled={zoom >= 200}
            onClick={() => setZoom((value) => Math.min(200, value + 25))}
          >
            +
          </button>
          <button className="text-link" onClick={() => setZoom(100)}>
            Fit width
          </button>
        </div>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="pdf-canvas-viewport">
        <canvas
          ref={canvas}
          role="img"
          aria-label={`Invoice PDF preview, page ${page}`}
          data-rendered={rendered ? 'true' : 'false'}
        />
      </div>
      {!rendered && !error && <p className="empty-inline">Rendering original PDF…</p>}
    </div>
  );
}
