import { money, type Run } from './api';
import { Icon, reasonLabel } from './ui';
export default function RuleChecklist({ run }: { run: Run }) {
  const unknownLabels: Record<string, string> = {
    VENDOR_IDENTITY: 'Vendor identity',
    PO_MATCH: 'Purchase order match',
    DUPLICATE_IDENTITY: 'Invoice duplicate check',
    INVOICE_ARITHMETIC: 'Invoice arithmetic',
    TAX_RECONCILIATION: 'Tax reconciliation',
    PO_QUANTITY: 'PO quantity allowance',
    PO_BALANCE: 'Available PO balance',
  };
  const checks = [...run.checks].sort(
    (a, b) =>
      ({ failed: 0, requires_review: 1, passed: 2, not_evaluated: 3 })[a.status] -
      { failed: 0, requires_review: 1, passed: 2, not_evaluated: 3 }[b.status],
  );
  return (
    <section className="panel rule-panel" aria-label="Financial rule checklist">
      <div className="panel-heading">
        <div>
          <h2>Financial rule checklist</h2>
          <p>Recorded results. An unknown check is never treated as a pass.</p>
        </div>
      </div>
      <ul className="rule-list">
        {checks.map((check) => (
          <li
            key={check.rule_id}
            className={'rule-check ' + check.status}
            data-rule={check.rule_id}
          >
            <span className="check-symbol">
              <Icon
                name={
                  check.status === 'passed'
                    ? 'check'
                    : check.status === 'not_evaluated'
                      ? 'clock'
                      : 'alert'
                }
                size={16}
              />
            </span>
            <div>
              <div className="check-heading">
                <strong>
                  {check.status === 'failed' || check.status === 'requires_review'
                    ? reasonLabel(check.finding_code)
                    : check.status === 'not_evaluated'
                      ? (unknownLabels[check.rule_id] ?? check.title)
                      : check.title}
                </strong>
                <span className="check-status">
                  {check.status === 'passed'
                    ? 'Passed'
                    : check.status === 'failed'
                      ? 'Failed'
                      : check.status === 'requires_review'
                        ? 'Requires review'
                        : 'Not evaluated'}
                </span>
              </div>
              {check.rule_id === 'PO_BALANCE' &&
                check.finding_code === 'PO_CAP_EXCEEDED' &&
                run.decision_observations && (
                  <p className="rule-numbers">
                    Exceeds available balance by{' '}
                    {money(
                      run.decision_observations.excess_gross,
                      run.decision_observations.currency,
                    )}{' '}
                    at assessment.
                  </p>
                )}
              <details>
                <summary>Supporting record</summary>
                <p>{check.description}</p>
                <small className="mono">
                  Rule {check.rule_id} · {check.provenance}
                  {check.assessment_revision != null
                    ? ' · revision ' + check.assessment_revision
                    : ''}
                </small>
                {check.pages.length > 0 && (
                  <small>
                    Locally verified document pages: {check.pages.join(', ')}. No field geometry is
                    available.
                  </small>
                )}
              </details>
            </div>
          </li>
        ))}
      </ul>
      {!checks.length && <p className="empty-inline">No financial assessment has been recorded.</p>}
      <details className="disclosure table-note">
        <summary>How these checks are evidenced</summary>
        <p>
          Passed checks are certified by the immutable VALIDATED assessment plus its committed
          approval ledger. Individual check execution logs were not recorded. Held assessments
          expose only their recorded finding.
        </p>
      </details>
    </section>
  );
}
