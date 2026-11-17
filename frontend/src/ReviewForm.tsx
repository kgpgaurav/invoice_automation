import { useRef, useState, type FormEvent } from 'react';
import { api, ApiError, errorMessage, money, type Review, type ReviewBody } from './api';
import { Icon, pretty } from './ui';
export default function ReviewForm({
  review,
  onSubmitted,
  onRefresh,
  notify,
  reasonCode,
  authorizedToken,
  compact = false,
}: {
  review: Review;
  onSubmitted: () => void;
  onRefresh: () => void;
  notify: (s: string) => void;
  reasonCode?: string | null;
  authorizedToken?: string;
  compact?: boolean;
}) {
  const [action, setAction] = useState(
      review.allowed_actions.includes('SELECT_PO') ? 'SELECT_PO' : '',
    ),
    [po, setPo] = useState(''),
    [reason, setReason] = useState(''),
    [reviewerToken, setReviewerToken] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const requestKey = useRef({ fingerprint: '', key: crypto.randomUUID() }),
    pending = useRef(false);
  const credential = authorizedToken ?? reviewerToken;
  const ready = Boolean(action && credential && reason.trim() && (action !== 'SELECT_PO' || po));
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      pending.current ||
      !action ||
      !reason.trim() ||
      !credential ||
      (action === 'SELECT_PO' && !po)
    )
      return;
    const body: ReviewBody = {
      generation: review.generation,
      action: action as ReviewBody['action'],
      payload: action === 'SELECT_PO' ? { po_id: po } : {},
      reason: reason.trim(),
    };
    const fingerprint = JSON.stringify(body);
    if (requestKey.current.fingerprint !== fingerprint)
      requestKey.current = { fingerprint, key: crypto.randomUUID() };
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await api(`/reviews/${review.review_request_id}/respond`, credential.trim(), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Idempotency-Key': requestKey.current.key,
        },
        body: JSON.stringify(body),
      });
      onSubmitted();
    } catch (e) {
      const message = errorMessage(e);
      setError(message);
      if (e instanceof ApiError && e.status === 409) {
        notify(message);
        onRefresh();
      }
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      id="human-review"
      className={'review-panel' + (compact ? ' compact-review' : '')}
      aria-label="Human review"
    >
      {!compact && (
        <div className="review-intro">
          <span className="review-icon">
            <Icon name="shield" size={23} />
          </span>
          <div>
            <h2>
              {review.kind === 'PO_SELECTION'
                ? 'Choose the supporting purchase order'
                : 'Resolve this exception'}
            </h2>
            <p>
              {review.kind === 'PO_SELECTION'
                ? 'The invoice did not establish a supporting PO. Compare the offered candidates and select the procurement record you can substantiate.'
                : reasonCode === 'BANK_MISMATCH'
                  ? 'Independently verify bank information using your established vendor contact process. This is a change warning, not a fraud finding.'
                  : reasonCode === 'PO_CAP_EXCEEDED'
                    ? 'The invoice exceeds the recorded available PO balance. An authorized PO amendment or corrected source is needed; this form cannot waive the cap.'
                    : 'This invoice is held. Inspect the recorded checks and supporting figures before choosing a permitted action.'}
            </p>
            <small>
              Selection never waives financial rules. Funds are rechecked when processing resumes.
            </small>
          </div>
        </div>
      )}
      <form onSubmit={submit}>
        <fieldset disabled={busy}>
          <legend className="sr-only">Review response</legend>
          {action === 'SELECT_PO' && (
            <div className="po-options">
              <h2>Matching purchase order</h2>
              {!review.options.length && (
                <p>No purchase order candidates are available. Choose another permitted action.</p>
              )}
              {review.options.map((candidate) => (
                <label
                  className={`po-option ${po === candidate.po_id ? 'selected' : ''}`}
                  key={candidate.po_id}
                >
                  <input
                    type="radio"
                    name="purchase-order"
                    value={candidate.po_id}
                    checked={po === candidate.po_id}
                    onChange={() => setPo(candidate.po_id)}
                    required
                  />
                  <div>
                    <strong>{candidate.po_number ?? 'Unavailable PO'}</strong>
                    <small>
                      {pretty(candidate.status)} · {candidate.currency ?? 'Currency unavailable'}
                    </small>
                  </div>
                  <div>
                    <span>Available now</span>
                    <strong>{money(candidate.remaining_gross, candidate.currency ?? '')}</strong>
                  </div>
                </label>
              ))}
            </div>
          )}
          <div className="review-controls">
            <label>
              Next action
              <select
                aria-label="Action"
                value={action}
                onChange={(e) => setAction(e.target.value)}
                required
              >
                <option value="">Choose an action</option>
                {review.allowed_actions.map((a) => (
                  <option key={a} value={a}>
                    {a === 'SELECT_PO'
                      ? 'Select PO & resume'
                      : a === 'REQUEST_INFO'
                        ? 'Request source information & stop'
                        : 'Reject invoice'}
                  </option>
                ))}
              </select>
            </label>
            {!authorizedToken && (
              <label>
                Reviewer access token
                <input
                  type="password"
                  autoComplete="off"
                  value={reviewerToken}
                  onChange={(e) => {
                    setReviewerToken(e.target.value);
                    setError('');
                  }}
                  required
                  placeholder="Separate reviewer credential"
                />
              </label>
            )}
          </div>
          <label>
            Review rationale
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              required
              rows={2}
              placeholder="Explain the supporting records or information needed."
            />
          </label>
          <div className="review-submit">
            <p className="review-revalidation">
              <Icon name="info" size={17} />
              {action === 'SELECT_PO'
                ? 'Selection reruns validation. It does not approve the invoice.'
                : 'Your response will be recorded. No payment is executed.'}
            </p>
            <small id="review-submit-help" className={ready ? 'sr-only' : ''}>
              {!action
                ? 'Choose a permitted action to continue.'
                : !credential
                  ? 'Enter the reviewer access token to continue.'
                  : action === 'SELECT_PO' && !po
                    ? 'Select a supporting purchase order and add your rationale.'
                    : !reason.trim()
                      ? 'Add your review rationale to continue.'
                      : 'Ready to record this response.'}
            </small>
            <button
              className="button"
              aria-describedby="review-submit-help"
              disabled={
                busy || !action || !credential || !reason.trim() || (action === 'SELECT_PO' && !po)
              }
            >
              {busy
                ? 'Recording response…'
                : action === 'SELECT_PO'
                  ? 'Confirm selection & resume'
                  : 'Submit review response'}
              <Icon name="arrow" size={16} />
            </button>
          </div>
        </fieldset>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
      </form>
    </section>
  );
}
