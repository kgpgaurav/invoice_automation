import { useEffect, useState } from 'react';
import { api, request, errorMessage, type SubmitterRun, type RunEvent } from './api';
import { Link, type Navigate } from './ui';
import InvoiceWorkspace from './InvoiceWorkspace';

export default function SubmitterRunView({
  runId,
  token,
  navigate,
}: {
  runId: string;
  token: string;
  navigate: Navigate;
}) {
  const [run, setRun] = useState<SubmitterRun | null>(null),
    [events, setEvents] = useState<RunEvent[]>([]),
    [error, setError] = useState(''),
    [pdf, setPdf] = useState(''),
    [pdfError, setPdfError] = useState('');
  const [pdfVersion, setPdfVersion] = useState(0);
  useEffect(() => {
    setRun(null);
    setEvents([]);
    setError('');
    const controller = new AbortController();
    let pending = false;
    async function refresh() {
      if (pending || !token) return;
      pending = true;
      try {
        const value = await api<SubmitterRun>(`/runs/${runId}`, token, {
          signal: controller.signal,
        });
        const rows = await api<RunEvent[]>(`/runs/${runId}/events?limit=500`, token, {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setRun(value);
          setEvents(rows);
          setError('');
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [runId, token]);
  useEffect(() => {
    setPdf('');
    setPdfError('');
    const controller = new AbortController();
    let url = '';
    request(`/runs/${runId}/document`, token, { signal: controller.signal })
      .then((r) => r.blob())
      .then((blob) => {
        if (!controller.signal.aborted) {
          url = URL.createObjectURL(blob);
          setPdf(url);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setPdfError(errorMessage(e));
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [runId, token, pdfVersion]);
  return (
    <>
      <div className="invoice-breadcrumb">
        <Link to="?view=history" navigate={navigate}>
          ← Back to My invoices
        </Link>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!run ? (
        <div className="panel empty-state" role="status">
          <h1>Invoice status</h1>
          <p>{error ? 'Invoice details could not be loaded.' : 'Reading invoice details…'}</p>
        </div>
      ) : (
        <InvoiceWorkspace
          run={run}
          events={events}
          pdf={pdf}
          pdfError={pdfError}
          audience="submitter"
          connection="Updates from saved processing records"
          reconnect={() => {}}
          navigate={navigate}
          retryPDF={() => setPdfVersion((value) => value + 1)}
        />
      )}
    </>
  );
}
