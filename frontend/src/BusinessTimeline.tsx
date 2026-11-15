import { dateTime, duration, type Run, type RunEvent } from './api';
import { pretty } from './ui';
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
  run: Pick<Run, 'stages' | 'job_state' | 'source_mode'>;
  events: RunEvent[];
  connection: string;
  reconnect: () => void;
  technical?: boolean;
}) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <div>
          <h2>Processing timeline</h2>
          <p>
            {technical
              ? 'Actual recorded execution · completion of a stage is not a passed financial check.'
              : 'Processing updates recorded for your invoice.'}
          </p>
        </div>
        <span className="stream-state">{connection}</span>
      </div>
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
          const status = decision
            ? 'Recorded'
            : last
              ? interrupted
                ? 'Interrupted'
                : last.status === 'finished'
                  ? 'Completed'
                  : 'In progress'
              : 'Not recorded';
          const at = decision?.occurred_at ?? last?.finished_at ?? last?.started_at;
          return (
            <li
              key={key}
              className={
                'business-stage ' +
                (status === 'Completed' || status === 'Recorded'
                  ? 'complete'
                  : status === 'In progress'
                    ? 'current'
                    : '')
              }
              data-stage={key}
            >
              <span className="stage-index">{index + 1}</span>
              <div>
                <div className="stage-heading">
                  <strong>{title}</strong>
                  <span>{status}</span>
                </div>
                <p>
                  {technical
                    ? explanation
                    : [
                        'Read your submitted PDF.',
                        'Extract the printed invoice information.',
                        'Check required fields and totals.',
                        'Verify supplier and purchase-order information.',
                        'Check the invoice against purchasing requirements.',
                        'Save the invoice outcome.',
                      ][index]}
                </p>
                <small>
                  {at ? <time dateTime={at}>{dateTime(at)}</time> : 'No execution event recorded'}
                  {total != null ? ' · ' + duration(total) : ''}
                  {rows.length > 1 ? ' · ' + rows.length + ' recorded executions' : ''}
                </small>
                {technical && key === 'DECISION' && decision && (
                  <small>
                    Assessment recorded; see the current outcome above. Decision write shares the
                    financial transaction; no separate duration is measured.
                  </small>
                )}
              </div>
            </li>
          );
        })}
      </ol>
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
