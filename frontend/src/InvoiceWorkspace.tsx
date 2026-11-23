import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import type { RunEvent, Review } from './api';
import { dateTime, money } from './api';
import { Icon, pretty, type Navigate } from './ui';
import type { InvoiceRecord, InvoiceTab } from './invoicePresentation';
import InvoiceSummary from './InvoiceSummary';
import InvoiceFields from './InvoiceFields';
import InvoiceIssues from './InvoiceIssues';
import InvoiceDecision from './InvoiceDecision';
import DocumentPanel from './DocumentPanel';
import BusinessTimeline from './BusinessTimeline';
import RuleChecklist from './RuleChecklist';
import ReviewComparisons from './ReviewComparisons';
import ReviewForm from './ReviewForm';

export default function InvoiceWorkspace({
  run,
  events,
  pdf,
  pdfError,
  audience,
  embedded = false,
  connection,
  reconnect,
  navigate,
  review,
  reviewerToken,
  submitted,
  notify,
  retryPDF,
}: {
  run: InvoiceRecord;
  events: RunEvent[];
  pdf: string;
  pdfError: string;
  audience: 'submitter' | 'finance';
  embedded?: boolean;
  connection: string;
  reconnect: () => void;
  navigate: Navigate;
  review?: Review | null;
  reviewerToken?: string;
  submitted?: () => void;
  notify?: (value: string) => void;
  retryPDF?: () => void;
}) {
  const finance = audience === 'finance' && 'checks' in run ? run : null;
  const [tab, setTab] = useState<InvoiceTab>('data');
  const [documentShown, setDocumentShown] = useState(true);
  const [share, setShare] = useState(42);
  const [pageTarget, setPageTarget] = useState({ page: 1, revision: 0 });
  const [sourceNotice, setSourceNotice] = useState('');
  const [focusField, setFocusField] = useState({ field: '', revision: 0 });
  const layout = useRef<HTMLDivElement>(null),
    data = useRef<HTMLDivElement>(null);
  const tabButtons = useRef<Partial<Record<InvoiceTab, HTMLButtonElement | null>>>({});
  const id = useId();
  const userSelectedTab = useRef(false);
  const reviewEvents = events.filter((event) =>
    ['REVIEW_REQUESTED', 'REVIEW_RESOLVED'].includes(event.type),
  );
  const tabs: { key: InvoiceTab; label: string }[] = [
    { key: 'data', label: 'Invoice data' },
    ...(finance
      ? [
          { key: 'comparison' as const, label: 'PO comparison' },
          { key: 'checks' as const, label: 'Financial checks' },
        ]
      : []),
    ...(finance && (review || reviewEvents.length)
      ? [{ key: 'review' as const, label: review ? 'Review response' : 'Review history' }]
      : []),
  ];
  useEffect(() => {
    if (review?.review_request_id && finance && !userSelectedTab.current) setTab('review');
  }, [review?.review_request_id, Boolean(finance)]);
  useEffect(() => {
    if (tab === 'review' && !review && !reviewEvents.length) setTab('data');
  }, [tab, Boolean(review), reviewEvents.length]);
  function inspect(next: InvoiceTab) {
    if (!tabs.some((item) => item.key === next)) return;
    userSelectedTab.current = true;
    setTab(next);
    requestAnimationFrame(() => {
      data.current?.scrollIntoView({ block: 'nearest' });
      tabButtons.current[next]?.focus({ preventScroll: true });
    });
  }
  function showPage(page: number, field: string) {
    userSelectedTab.current = true;
    setDocumentShown(true);
    setPageTarget((old) => ({ page, revision: old.revision + 1 }));
    setSourceNotice(`Showing page ${page} for ${field.replaceAll('_', ' ')}.`);
    requestAnimationFrame(() =>
      layout.current?.querySelector('.invoice-document-pane')?.scrollIntoView({ block: 'nearest' }),
    );
  }
  function fieldFocus(field: string) {
    userSelectedTab.current = true;
    setTab('data');
    setFocusField((old) => ({ field, revision: old.revision + 1 }));
  }
  function keyboardTabs(event: KeyboardEvent, current: InvoiceTab) {
    const index = tabs.findIndex((item) => item.key === current);
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft'
          ? (index + tabs.length - 1) % tabs.length
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? tabs.length - 1
              : -1;
    if (next >= 0) {
      event.preventDefault();
      userSelectedTab.current = true;
      setTab(tabs[next].key);
      tabButtons.current[tabs[next].key]?.focus();
    }
  }
  return (
    <article className={'invoice-detail' + (embedded ? ' embedded-invoice' : '')}>
      <InvoiceSummary run={run} embedded={embedded} inspect={inspect} />
      {finance ? (
        review?.kind === 'PO_SELECTION' ? (
          <div className="review-exception" role="note">
            <Icon name="alert" size={22} />
            <div>
              <h2>Purchase order required</h2>
              <p>
                Select the purchase order supported by this invoice. Selection reruns financial
                validation.
              </p>
            </div>
            <button className="text-link" onClick={() => inspect('review')}>
              Review options
            </button>
          </div>
        ) : (
          <InvoiceDecision run={finance} navigate={navigate} onReview={() => inspect('review')} />
        )
      ) : (
        <section
          className={
            'decision-banner submitter-outcome ' + (run.decision ?? run.job_state).toLowerCase()
          }
          aria-label="Invoice outcome"
        >
          <div className="decision-title">
            <Icon
              name={
                run.decision === 'APPROVED'
                  ? 'check'
                  : run.job_state === 'RUNNING' || run.job_state === 'QUEUED'
                    ? 'clock'
                    : 'alert'
              }
              size={22}
            />
            <div>
              <h2>{pretty(run.decision ?? run.job_state)}</h2>
              <p>{run.decision_reason ?? 'Your invoice is waiting for processing.'}</p>
              {run.decision && (
                <p className="invoice-next-step">
                  {run.decision === 'APPROVED'
                    ? 'Approved for payment processing. Finance will confirm the payment schedule.'
                    : run.decision === 'REJECTED'
                      ? 'This invoice is not approved for payment. See the reason.'
                      : run.job_state === 'WAITING_REVIEW'
                        ? 'A financial reviewer will review this invoice.'
                        : 'Payment is not authorized. See the recorded outcome above.'}
                </p>
              )}
              {run.processing_failure && <p>{run.processing_failure.next_action}</p>}
            </div>
          </div>
        </section>
      )}
      {finance && <InvoiceIssues run={finance} inspect={inspect} />}
      {!!finance?.verification_findings.length && (
        <p className="findings" role="note">
          <strong>Source evidence needs review. </strong>
          {finance.verification_findings.includes('SCANNED_EVIDENCE_REQUIRES_REVIEW')
            ? 'This scan has no local text corroboration. Model transcription alone is not trusted evidence.'
            : 'Some source fields are missing, conflicting or unresolved. Inspect the saved evidence before taking a review action.'}
        </p>
      )}
      <div className="invoice-progress">
        <BusinessTimeline
          run={run}
          events={events}
          connection={connection}
          reconnect={reconnect}
          technical={Boolean(finance) && !embedded}
        />
      </div>
      <div className={'invoice-workspace' + (!documentShown ? ' pdf-collapsed' : '')} ref={layout}>
        <div className="invoice-workspace-tools">
          <span>Invoice workspace</span>
          <button
            className="text-link"
            aria-expanded={documentShown}
            aria-controls={id + '-document'}
            onClick={() => setDocumentShown((value) => !value)}
          >
            <Icon name="file" size={15} /> {documentShown ? 'Hide PDF' : 'Show PDF'}
          </button>
        </div>
        <div
          className="invoice-workspace-grid"
          style={{ '--pdf-share': `${share}%` } as CSSProperties}
        >
          <div className="invoice-document-pane" id={id + '-document'} hidden={!documentShown}>
            <DocumentPanel
              url={pdf}
              error={pdfError}
              target={pageTarget}
              notice={sourceNotice}
              onRetry={retryPDF}
            />
          </div>
          <div
            className="invoice-divider"
            role="separator"
            aria-label="Resize PDF and invoice data"
            aria-orientation="vertical"
            aria-valuemin={35}
            aria-valuemax={50}
            aria-valuenow={share}
            tabIndex={documentShown ? 0 : -1}
            hidden={!documentShown}
            onKeyDown={(event) => {
              if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
                event.preventDefault();
                setShare((value) =>
                  event.key === 'Home'
                    ? 35
                    : event.key === 'End'
                      ? 50
                      : Math.max(35, Math.min(50, value + (event.key === 'ArrowRight' ? 1 : -1))),
                );
              }
            }}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
              const box = event.currentTarget.parentElement!.getBoundingClientRect();
              setShare(
                Math.max(
                  35,
                  Math.min(50, Math.round((100 * (event.clientX - box.left)) / box.width)),
                ),
              );
            }}
            onPointerUp={(event) => {
              if (event.currentTarget.hasPointerCapture(event.pointerId))
                event.currentTarget.releasePointerCapture(event.pointerId);
            }}
          >
            <span />
          </div>
          <div className="invoice-data-pane" ref={data}>
            <div className="invoice-tabs" role="tablist" aria-label="Invoice detail sections">
              {tabs.map((item) => (
                <button
                  key={item.key}
                  role="tab"
                  id={id + '-tab-' + item.key}
                  aria-selected={tab === item.key}
                  aria-controls={id + '-panel-' + item.key}
                  tabIndex={tab === item.key ? 0 : -1}
                  ref={(element) => {
                    tabButtons.current[item.key] = element;
                  }}
                  onClick={() => {
                    userSelectedTab.current = true;
                    setTab(item.key);
                  }}
                  onKeyDown={(event) => keyboardTabs(event, item.key)}
                >
                  {item.label}
                  {item.key === 'review' && <span className="tab-review-dot" aria-hidden="true" />}
                </button>
              ))}
            </div>
            <div
              role="tabpanel"
              id={id + '-panel-data'}
              aria-labelledby={id + '-tab-data'}
              hidden={tab !== 'data'}
              tabIndex={0}
            >
              <InvoiceFields
                run={run}
                showPage={showPage}
                focusField={focusField.field ? focusField : undefined}
              />
            </div>
            {finance && (
              <>
                <div
                  role="tabpanel"
                  id={id + '-panel-comparison'}
                  aria-labelledby={id + '-tab-comparison'}
                  hidden={tab !== 'comparison'}
                  tabIndex={0}
                >
                  <ReviewComparisons
                    run={finance}
                    pdf={pdf}
                    showPage={showPage}
                    inspectField={fieldFocus}
                  />
                </div>
                <div
                  role="tabpanel"
                  id={id + '-panel-checks'}
                  aria-labelledby={id + '-tab-checks'}
                  hidden={tab !== 'checks'}
                  tabIndex={0}
                >
                  <RuleChecklist run={finance} />
                </div>
                {(review || reviewEvents.length > 0) && (
                  <div
                    role="tabpanel"
                    id={id + '-panel-review'}
                    aria-labelledby={id + '-tab-review'}
                    hidden={tab !== 'review'}
                    tabIndex={0}
                  >
                    {review ? (
                      <ReviewForm
                        key={review.review_request_id}
                        review={review}
                        reasonCode={finance.reason_code}
                        authorizedToken={reviewerToken}
                        onRefresh={reconnect}
                        onSubmitted={submitted ?? reconnect}
                        notify={notify ?? (() => {})}
                      />
                    ) : (
                      <p className="empty-inline">
                        No open review action. The recorded outcome is shown above.
                      </p>
                    )}
                    <details className="invoice-review-history disclosure">
                      <summary>Review history ({reviewEvents.length})</summary>
                      {reviewEvents.length ? (
                        <ol>
                          {reviewEvents.map((event) => (
                            <li key={event.seq}>
                              <strong>
                                {event.type === 'REVIEW_REQUESTED'
                                  ? 'Review requested'
                                  : 'Review response recorded'}
                              </strong>
                              <time dateTime={event.occurred_at}>
                                {dateTime(event.occurred_at)}
                              </time>
                              {typeof event.payload.action === 'string' && (
                                <p>{pretty(event.payload.action)}</p>
                              )}
                              {typeof event.payload.actor_id === 'string' && (
                                <small>Recorded actor: {event.payload.actor_id}</small>
                              )}
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p>No review events are available in this record.</p>
                      )}
                    </details>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      {audience === 'submitter' && (
        <details className="invoice-usage disclosure">
          <summary>Processing and usage details</summary>
          <p>
            Last updated {dateTime(run.updated_at)}.{' '}
            {run.source_mode === 'MOCK_OPENAI'
              ? 'Prepared sample extraction'
              : run.model_id === 'not-configured'
                ? 'Extraction not started'
                : 'Model: ' + run.model_id}
            .
          </p>
          <p>
            Recorded requests: {run.usage.recorded_attempts}. Estimated API cost:{' '}
            {run.usage.cost_status === 'not_applicable'
              ? 'Not applicable (mock)'
              : run.usage.estimated_cost_usd == null
                ? 'Unknown'
                : 'USD ' + run.usage.estimated_cost_usd}
            . Actual billed cost is unknown.
          </p>
          <p>Invoice amount: {money(run.invoice_total, run.invoice_currency ?? '')}</p>
        </details>
      )}
      {finance?.verification_findings.length ? (
        <details className="invoice-usage disclosure">
          <summary>Source evidence findings ({finance.verification_findings.length})</summary>
          <p>
            Source verification remains separate from extraction and financial approval. Scans
            without local text require review.
          </p>
          <ul>
            {finance.verification_findings.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </article>
  );
}
