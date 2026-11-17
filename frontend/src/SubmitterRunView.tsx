import { lazy, Suspense, useEffect, useState } from 'react';
import {
  api,
  request,
  errorMessage,
  money,
  dateTime,
  type SubmitterRun,
  type RunEvent,
} from './api';
import { Badge, Link, Mode, pretty, type Navigate } from './ui';
import BusinessTimeline from './BusinessTimeline';
const PDFPreview = lazy(() => import('./PDFPreview'));

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
  }, [runId, token]);
  return (
    <>
      <Link to="?view=history" navigate={navigate}>
        ← Back to My invoices
      </Link>
      <div className="page-heading">
        <div>
          <h1>{run?.invoice_number ?? 'Invoice status'}</h1>
          <p>Run {runId.slice(0, 8)}</p>
        </div>
        {run && <Badge value={run.decision ?? run.job_state} />}
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {run && (
        <>
          <section className="panel provider-panel">
            <h2>{pretty(run.decision ?? run.job_state)}</h2>
            <p>{run.decision_reason ?? 'Your invoice is waiting for processing.'}</p>
            <Mode value={run.source_mode} />
            <p>
              Invoice amount:{' '}
              <strong>{money(run.invoice_total, run.invoice_currency ?? '')}</strong>
            </p>
            {run.processing_failure && (
              <div className="error">
                <p>{run.processing_failure.message}</p>
                <p>{run.processing_failure.next_action}</p>
              </div>
            )}
            {run.job_state === 'WAITING_REVIEW' && (
              <p>
                A financial reviewer will handle this exception. You do not need to enter a reviewer
                credential.
              </p>
            )}
            <p>Last updated {dateTime(run.updated_at)}</p>
            <p>
              {run.source_mode === 'MOCK_OPENAI'
                ? 'Prepared sample extraction'
                : run.model_id === 'not-configured'
                  ? 'Extraction not started'
                  : `Model: ${run.model_id}`}{' '}
              · Recorded requests: {run.usage.recorded_attempts} · Estimated API cost:{' '}
              {run.usage.cost_status === 'not_applicable'
                ? 'Not applicable (mock)'
                : run.usage.estimated_cost_usd == null
                  ? 'Unknown'
                  : `US$${run.usage.estimated_cost_usd}`}
            </p>
          </section>
          <BusinessTimeline
            run={run}
            events={events}
            connection="Updates from saved processing records"
            reconnect={() => {}}
            technical={false}
          />
          <section className="panel provider-panel">
            <h2>Extracted invoice information</h2>
            <dl className="submitter-fields">
              {run.fields.map((field) => (
                <div key={field.field}>
                  <dt>
                    {field.field.startsWith('lines.')
                      ? `Line ${field.field.split('.')[1]} · ${pretty(field.field.split('.').slice(2).join('.'))}`
                      : pretty(field.field)}
                  </dt>
                  <dd>
                    {field.value ?? 'Missing'} · {field.verification}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        </>
      )}
      <section className="panel provider-panel">
        <h2>Your submitted PDF</h2>
        {pdfError && <p role="alert">{pdfError}</p>}
        {pdf && (
          <>
            <a href={pdf} target="_blank" rel="noreferrer">
              Open PDF
            </a>
            <Suspense fallback={<p>Loading PDF preview…</p>}>
              <PDFPreview url={pdf} />
            </Suspense>
          </>
        )}
      </section>
    </>
  );
}
