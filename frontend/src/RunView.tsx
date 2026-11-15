import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import {
  api,
  request,
  dateTime,
  duration,
  errorMessage,
  mergeEvents,
  money,
  streamEvents,
  type Run,
  type RunEvent,
  type Review,
} from './api';
import { Badge, Link, Mode, pretty, type Navigate } from './ui';
import ReviewForm from './ReviewForm';
import InvoiceDecision from './InvoiceDecision';
import RuleChecklist from './RuleChecklist';
import BusinessTimeline from './BusinessTimeline';
const PDFPreview = lazy(() => import('./PDFPreview'));

export default function RunView({
  runId,
  token,
  navigate,
  notify,
  reviewerToken,
}: {
  runId: string;
  token: string;
  navigate: Navigate;
  notify: (s: string) => void;
  reviewerToken?: string;
}) {
  const [run, setRun] = useState<Run | null>(null),
    [events, setEvents] = useState<RunEvent[]>([]),
    [review, setReview] = useState<Review | null>(null),
    [pdf, setPdf] = useState('');
  const [error, setError] = useState(''),
    [pdfError, setPdfError] = useState(''),
    [connection, setConnection] = useState('Connecting'),
    [streamVersion, setStreamVersion] = useState(0);
  const [pageTarget, setPageTarget] = useState({ page: 1, revision: 0 }),
    [sourceNotice, setSourceNotice] = useState('');
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
  }, [runId, token]);
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
  const fieldTitle = (path: string) => {
    const parts = path.split('.');
    return parts.length === 3 ? `Line ${parts[1]} · ${pretty(parts[2])}` : pretty(path);
  };
  function source(page: number, field: string) {
    setPageTarget((old) => ({ page, revision: old.revision + 1 }));
    setSourceNotice(`Showing page ${page} for ${fieldTitle(field)}.`);
    document.getElementById('source-document')?.scrollIntoView({ block: 'start' });
  }
  return (
    <>
      <div className="page-heading run-heading">
        <div>
          <Link to="?view=history" navigate={navigate} className="back-link">
            ← Back to Invoice History
          </Link>
          <p className="eyebrow">INVOICE WORKSPACE</p>
          <h1 className="mono">{run?.invoice_number ?? 'Invoice details'}</h1>
          <p className="run-ident">Run {runId}</p>
        </div>
        <div className="heading-badges">
          {run && <Mode value={run.source_mode} />}
          <Badge value={run?.job_state ?? 'NOT_LOADED'} />
        </div>
      </div>
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
          <InvoiceDecision run={run} navigate={navigate} />
          <div className="run-layout">
            <section
              className="panel document-panel"
              id="source-document"
              aria-label="Source document"
            >
              <div className="panel-heading">
                <div>
                  <h2>Source document</h2>
                  <p>Original PDF · received {dateTime(run.created_at)}</p>
                </div>
                {pdf && (
                  <a className="text-link" href={pdf} target="_blank" rel="noreferrer">
                    Open PDF ↗
                  </a>
                )}
              </div>
              {pdf ? (
                <Suspense fallback={<div className="empty-state">Loading PDF viewer…</div>}>
                  <PDFPreview url={pdf} target={pageTarget} />
                </Suspense>
              ) : (
                <div className="empty-state">{pdfError || 'Loading private PDF…'}</div>
              )}
              <div className="document-caption" role="status">
                {sourceNotice ||
                  'Verified page links are available in extracted details. Exact source highlighting is not available.'}
              </div>
            </section>
            <div className="run-right">
              <section className="matching-summary panel">
                <div className="matching-grid">
                  <div>
                    <span>Vendor master · current</span>
                    <strong>{run.vendor?.name ?? 'Not matched'}</strong>
                    <small>
                      {run.vendor ? pretty(run.vendor.status) : 'Identity requires verification'}
                    </small>
                  </div>
                  <div>
                    <span>PO Reference</span>
                    {run.purchase_order &&
                    run.purchase_order.relationship !== 'PRINTED_REFERENCE' ? (
                      <Link
                        to={'?po=' + run.purchase_order.po_id}
                        navigate={navigate}
                        className="text-link mono"
                      >
                        {run.purchase_order.po_number} ↗
                      </Link>
                    ) : (
                      <strong className="mono">
                        {run.purchase_order?.po_number ?? 'Not established'}
                      </strong>
                    )}
                    <small>
                      {run.purchase_order
                        ? run.purchase_order.relationship === 'PRINTED_REFERENCE'
                          ? 'Printed reference only · not a verified match'
                          : run.purchase_order.relationship === 'APPROVED_ALLOCATION'
                            ? 'Linked approval allocation'
                            : 'Recorded assessment PO'
                        : 'No implicit selection'}
                    </small>
                  </div>
                </div>
                {run.purchase_order && run.purchase_order.relationship !== 'PRINTED_REFERENCE' && (
                  <div className="current-po-balance">
                    <span>Current PO remaining</span>
                    <strong>
                      {money(run.purchase_order.remaining_gross, run.purchase_order.currency)}
                    </strong>
                    <small>Current master; includes all posted approvals</small>
                  </div>
                )}
              </section>
              <RuleChecklist run={run} />
              {!!run.verification_findings.length && (
                <section className="findings">
                  <strong>Source evidence needs review</strong>
                  <p>
                    {run.verification_findings.includes('SCANNED_EVIDENCE_REQUIRES_REVIEW')
                      ? 'This scan has no local text corroboration. Model transcription alone is not trusted evidence.'
                      : 'Some source fields are missing, conflicting or unresolved. No trust is inferred from a schema-valid extraction.'}
                  </p>
                  <details>
                    <summary>Evidence finding identifiers</summary>
                    {run.verification_findings.map((code) => (
                      <p className="mono" key={code}>
                        {code}
                      </p>
                    ))}
                  </details>
                </section>
              )}
              {review && (
                <ReviewForm
                  authorizedToken={reviewerToken}
                  key={review.review_request_id}
                  review={review}
                  reasonCode={run.reason_code}
                  onRefresh={() => void refreshRef.current()}
                  onSubmitted={() => {
                    notify(
                      'Review recorded. Resume is queued; financial requirements will be revalidated.',
                    );
                    setReview(null);
                    setStreamVersion((n) => n + 1);
                    void refreshRef.current();
                  }}
                  notify={notify}
                />
              )}
              <section className="panel fields-panel">
                <details open>
                  <summary className="panel-heading">
                    <h2>Extracted details</h2>
                    <span className="muted">Source status & page links</span>
                  </summary>
                  {run.fields.length ? (
                    <div className="field-list">
                      {run.fields.map((field) => (
                        <div className="field-row" key={field.field}>
                          <span>{fieldTitle(field.field)}</span>
                          <strong
                            className={
                              /amount|subtotal|total|price/.test(field.field) ? 'amount' : ''
                            }
                          >
                            {field.value == null
                              ? 'Missing'
                              : /amount|subtotal|total|price$/.test(field.field) &&
                                  field.field !== 'price_basis'
                                ? money(field.value, run.invoice_currency ?? '')
                                : field.value}
                          </strong>
                          <div>
                            <small className={'verification ' + field.verification}>
                              {pretty(field.verification)}
                            </small>
                            {field.verification === 'verified' &&
                              field.pages.map((page) => (
                                <button
                                  className="page-link"
                                  key={page}
                                  aria-label={`View ${fieldTitle(field.field)} source, page ${page}`}
                                  onClick={() => source(page, field.field)}
                                >
                                  p{page} ↗
                                </button>
                              ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-inline">No extraction has been stored.</p>
                  )}
                  <p className="table-note">
                    Verification is local source support, not model confidence. Missing values
                    remain missing. Original filename was not retained by intake.
                  </p>
                </details>
              </section>
            </div>
          </div>
          <BusinessTimeline
            run={run}
            events={events}
            connection={connection}
            reconnect={() => setStreamVersion((n) => n + 1)}
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
