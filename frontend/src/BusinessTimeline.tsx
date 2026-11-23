import { dateTime, duration, type Run, type RunEvent } from './api';
import { Icon, pretty } from './ui';
const steps = [
  ['DOCUMENT_LOADING', 'Read document', 'Open and validate the stored PDF.'],
  [
    'EXTRACTION',
    'Extract invoice information',
    'Read the printed invoice fields; preserve missing values.',
  ],
  ['EVIDENCE_VERIFICATION', 'Verify evidence', 'Check source support and invoice arithmetic.'],
  [
    'MATCHING',
    'Match purchase order',
    'Find the supplier and supporting PO, or offer review candidates.',
  ],
  [
    'FINALIZATION',
    'Apply financial rules',
    'Revalidate and, if eligible, allocate funds in one transaction.',
  ],
  [
    'DECISION',
    'Record decision',
    'Persist the assessment or final decision with its audit record.',
  ],
];
export default function BusinessTimeline({
  run,
  events,
  connection,
  reconnect,
  technical = true,
}: {
  run: Pick<Run, 'stages' | 'job_state' | 'source_mode'> &
    Partial<Pick<Run, 'decision' | 'decision_reason' | 'reason_code' | 'error_code' | 'checks'>>;
  events: RunEvent[];
  connection: string;
  reconnect: () => void;
  technical?: boolean;
}) {
  const needsReview = run.job_state === 'WAITING_REVIEW';
  const issue = needsReview || run.job_state === 'FAILED';
  const sourceIssue = run.checks?.some(
    (check) =>
      ['REQUIRED_FIELDS', 'SOURCE_EVIDENCE'].includes(check.rule_id) &&
      ['requires_review', 'failed'].includes(check.status),
  );
  const code = run.reason_code ?? '';
  const issueStage =
    sourceIssue || ['UNVERIFIED_TOTAL', 'CRITICAL_FIELD_MISSING'].includes(code)
      ? 'EVIDENCE_VERIFICATION'
      : code.startsWith('VENDOR_') ||
          [
            'PO_MISSING',
            'PO_AMBIGUOUS',
            'PO_VENDOR_MISMATCH',
            'DUPLICATE_APPROVED',
            'DUPLICATE_CONFLICT',
          ].includes(code)
        ? 'MATCHING'
        : run.job_state === 'FAILED'
          ? (run.stages.filter((stage) => stage.status !== 'finished').at(-1)?.name ?? 'EXTRACTION')
          : 'FINALIZATION';
  const details: {
    title: string;
    at: string | undefined;
    total: number | null;
    count: number;
    explanation: string;
  }[] = [];
  return (
    <section className="panel timeline-panel compact-progress">
      <div className="panel-heading">
        <div>
          <h2>Processing timeline</h2>
          <p>Recorded progress. Completed stages can still find an issue.</p>
        </div>
        <span className="stream-state">{connection}</span>
      </div>
      {issue && (
        <p className="progress-issue" role="note">
          <Icon name="alert" size={16} />
          {needsReview ? 'Needs review' : 'Processing failed'}:{' '}
          {run.decision_reason ?? 'See the recorded issue above.'}
        </p>
      )}
      <ol className="business-timeline">
        {steps.map(([key, title, explanation], index) => {
          const rows = run.stages.filter((stage) => stage.name === key),
            last = rows.at(-1),
            decision =
              key === 'DECISION'
                ? events.filter((e) => e.type === 'DECISION_RECORDED').at(-1)
                : undefined;
          const closed =
            rows.length > 0 && rows.every((s) => s.status === 'finished' && s.elapsed_ms != null);
          const total = closed ? rows.reduce((sum, s) => sum + s.elapsed_ms!, 0) : null;
          const interrupted =
            last?.status === 'running' &&
            ['FAILED', 'INTERRUPTED', 'WAITING_REVIEW'].includes(run.job_state);
          const status =
            key === issueStage && issue
              ? needsReview
                ? 'Needs review'
                : 'Failed'
              : key === 'DECISION' && needsReview
                ? 'Awaiting review'
                : decision
                  ? 'Recorded'
                  : last
                    ? interrupted
                      ? 'Interrupted'
                      : last.status === 'finished'
                        ? 'Completed'
                        : 'In progress'
                    : 'Not recorded';
          const at = decision?.occurred_at ?? last?.finished_at ?? last?.started_at;
          details.push({ title, at, total, count: rows.length, explanation });
          return (
            <li
              key={key}
              className={
                'business-stage ' +
                (status === 'Needs review' || status === 'Failed'
                  ? 'has-issue'
                  : status === 'Completed' || status === 'Recorded'
                    ? 'complete'
                    : status === 'In progress'
                      ? 'current'
                      : '')
              }
              data-stage={key}
            >
              <span className="stage-index" aria-hidden="true">
                {status === 'Completed' || status === 'Recorded' ? (
                  <Icon name="check" size={13} />
                ) : (
                  index + 1
                )}
              </span>
              <div>
                <div className="stage-heading">
                  <strong>{title}</strong>
                  <span>{status}</span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      <details className="disclosure stage-details">
        <summary>Stage details & timings</summary>
        <ul>
          {details.map((item) => (
            <li key={item.title}>
              <strong>{item.title}</strong>
              <span>
                {item.at ? dateTime(item.at) : 'No execution event recorded'}
                {item.total != null && ' · ' + duration(item.total)}
                {item.count > 1 && ' · ' + item.count + ' recorded executions'}
              </span>
              {technical && <p>{item.explanation}</p>}
            </li>
          ))}
        </ul>
      </details>
      {technical && (
        <details className="disclosure technical-events">
          <summary>Technical audit events ({events.length})</summary>
          <div className="timeline">
            {events.map((event) => (
              <div className={'timeline-event ' + event.type.toLowerCase()} key={event.seq}>
                <strong>
                  #{event.seq} ·{' '}
                  {event.payload.operation === 'OPENAI_REQUEST' && run.source_mode === 'MOCK_OPENAI'
                    ? 'Mock extraction request'
                    : pretty(String(event.payload.operation ?? event.stage))}
                </strong>
                <p>
                  {pretty(event.type)}
                  {typeof event.payload.code === 'string' ? ' · ' + event.payload.code : ''}
                  {event.payload.fresh_api_call === false
                    ? ' · persisted extraction reused; no fresh call'
                    : ''}
                </p>
                <time dateTime={event.occurred_at}>{dateTime(event.occurred_at)}</time>
              </div>
            ))}
          </div>
        </details>
      )}
      {technical && (
        <button className="text-link stream-retry" onClick={reconnect}>
          Reconnect live stream
        </button>
      )}
    </section>
  );
}
