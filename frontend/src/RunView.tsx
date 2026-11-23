import { useEffect, useRef, useState } from 'react';
import {
  api,
  request,
  duration,
  errorMessage,
  mergeEvents,
  streamEvents,
  type Run,
  type RunEvent,
  type Review,
} from './api';
import { Link, pretty, type Navigate } from './ui';
import ReviewDetail from './ReviewDetail';
import InvoiceWorkspace from './InvoiceWorkspace';

export default function RunView({
  runId,
  token,
  navigate,
  notify,
  reviewerToken,
  embedded = false,
}: {
  runId: string;
  token: string;
  navigate: Navigate;
  notify: (s: string) => void;
  reviewerToken?: string;
  embedded?: boolean;
}) {
  const [run, setRun] = useState<Run | null>(null),
    [events, setEvents] = useState<RunEvent[]>([]),
    [review, setReview] = useState<Review | null>(null),
    [pdf, setPdf] = useState('');
  const [error, setError] = useState(''),
    [pdfError, setPdfError] = useState(''),
    [connection, setConnection] = useState('Connecting'),
    [streamVersion, setStreamVersion] = useState(0);
  const [pdfVersion, setPdfVersion] = useState(0);
  const cursor = useRef(0),
    refreshRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    if (run) dispatchEvent(new Event('ps1:record-updated'));
  }, [run?.job_state, run?.decision, run?.review_request_id]);
  useEffect(() => {
    setRun(null);
    setEvents([]);
    cursor.current = 0;
    setReview(null);
    setError('');
    if (!token) return;
    const controller = new AbortController();
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const value = await api<Run>(`/runs/${runId}`, token, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(value);
        setError('');
        if (value.review_request_id) {
          const current = await api<Review>(`/runs/${runId}/review`, token, {
            signal: controller.signal,
          });
          if (!controller.signal.aborted) setReview(current);
        } else setReview(null);
        const rows = await api<RunEvent[]>(
          `/runs/${runId}/events?after_seq=${cursor.current}&limit=500`,
          token,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setEvents((old) => mergeEvents(old, rows));
          if (rows.length) cursor.current = Math.max(cursor.current, rows.at(-1)!.seq);
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(errorMessage(e));
      } finally {
        pending = false;
      }
    }
    refreshRef.current = refresh;
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
    if (!token) return;
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
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    async function connect() {
      try {
        while (!controller.signal.aborted) {
          const end = await streamEvents(
            runId,
            token,
            cursor.current,
            controller.signal,
            (event) => {
              setEvents((old) => mergeEvents(old, [event]));
              cursor.current = Math.max(cursor.current, event.seq);
              void refreshRef.current();
            },
            () => setConnection('Live events'),
          );
          if (end === 'caught_up') {
            setConnection('Up to date · polling backup');
            return;
          }
        }
      } catch {
        if (!controller.signal.aborted) setConnection('Polling fallback · every 2 seconds');
      }
    }
    void connect();
    return () => controller.abort();
  }, [runId, token, streamVersion]);
  function submitted() {
    notify('Review recorded. Processing will revalidate the financial requirements.');
    setReview(null);
    setStreamVersion((n) => n + 1);
    void refreshRef.current();
    dispatchEvent(new Event('ps1:record-updated'));
  }
  if (embedded)
    return (
      <ReviewDetail
        run={run}
        runId={runId}
        events={events}
        review={review}
        pdf={pdf}
        pdfError={pdfError}
        error={error}
        refresh={() => void refreshRef.current()}
        submitted={submitted}
        notify={notify}
        reviewerToken={reviewerToken}
        navigate={navigate}
        connection={connection}
        retryPDF={() => setPdfVersion((value) => value + 1)}
      />
    );
  return (
    <>
      <div className="invoice-breadcrumb">
        <Link to="?view=history" navigate={navigate} className="back-link">
          ← Back to Invoice History
        </Link>
      </div>
      {!run && <h1 className="invoice-loading-title">Invoice details</h1>}
      {error && (
        <div className="error" role="alert">
          {error}
          <button className="text-link" onClick={() => void refreshRef.current()}>
            Retry
          </button>
        </div>
      )}
      {!token ? (
        <div className="panel empty-state">
          <h3>Connect to view this invoice.</h3>
          <p>The run URL is preserved. Connect your workspace above to access the document.</p>
        </div>
      ) : !run ? (
        <div className="panel empty-state" role="status">
          {error ? 'Invoice details could not be loaded.' : 'Reading invoice details…'}
        </div>
      ) : (
        <>
          {run.source_mode === 'MOCK_OPENAI' && (
            <div className="mode-banner">
              <strong>MOCKED EXTRACTION</strong> Controlled fixture response; source verification,
              rules, review and ledger transactions execute for real. No live OpenAI call.
            </div>
          )}
          {run.replay_mode && (
            <div className="mode-banner">
              DEMO REPLAY — cached extraction, not a fresh model call.
            </div>
          )}
          <InvoiceWorkspace
            run={run}
            events={events}
            pdf={pdf}
            pdfError={pdfError}
            audience="finance"
            connection={connection}
            reconnect={() => {
              setStreamVersion((n) => n + 1);
              void refreshRef.current();
            }}
            navigate={navigate}
            review={review}
            reviewerToken={reviewerToken}
            submitted={submitted}
            notify={notify}
            retryPDF={() => setPdfVersion((value) => value + 1)}
          />
          <details className="panel audit-panel disclosure">
            <summary>Evidence & audit metadata</summary>
            <dl className="audit-grid">
              <div>
                <dt>Processing time</dt>
                <dd>
                  {duration(run.processing_ms)}
                  <small>{pretty(run.processing_time_status)} · human wait excluded</small>
                </dd>
              </div>
              <div>
                <dt>Extraction source</dt>
                <dd>
                  {run.source_mode === 'MOCK_OPENAI'
                    ? 'Mocked OpenAI response'
                    : run.model_id === 'not-configured'
                      ? 'Not started'
                      : 'OpenAI · ' + run.model_id}
                </dd>
              </div>
              <div>
                <dt>Estimated API cost</dt>
                <dd>
                  {run.usage.cost_status === 'not_applicable'
                    ? 'Not applicable · mock'
                    : run.usage.estimated_cost_usd != null
                      ? 'USD ' + run.usage.estimated_cost_usd
                      : 'Unknown'}
                  <small>Actual billed cost is unknown.</small>
                </dd>
              </div>
              <div>
                <dt>Recorded live requests</dt>
                <dd>
                  {run.usage.recorded_attempts}
                  <small>
                    {run.usage.reserved_attempts} reserved attempts; missing usage can follow a
                    crash.
                  </small>
                </dd>
              </div>
              <div>
                <dt>Input / output tokens</dt>
                <dd>
                  {run.usage.input_tokens ?? 'Unknown'} / {run.usage.output_tokens ?? 'Unknown'}
                </dd>
              </div>
              <div>
                <dt>Policy version</dt>
                <dd className="mono">{run.policy_version}</dd>
              </div>
              <div>
                <dt>Recorded technical reason</dt>
                <dd>
                  {run.processing_failure && (
                    <>
                      <strong>{run.processing_failure.code}</strong>
                      <small>{run.processing_failure.message}</small>
                      <small>Cause source: {run.processing_failure.provenance}</small>
                    </>
                  )}
                  {run.reason_code ?? run.error_code ?? 'Not recorded'}
                  <small>{run.decision_reason}</small>
                </dd>
              </div>
              <div>
                <dt>Thread ID</dt>
                <dd className="mono">{run.thread_id}</dd>
              </div>
            </dl>
          </details>
        </>
      )}
    </>
  );
}
