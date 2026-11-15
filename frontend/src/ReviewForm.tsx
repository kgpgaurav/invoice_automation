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
}: {
  review: Review;
  onSubmitted: () => void;
  onRefresh: () => void;
  notify: (s: string) => void;
  reasonCode?: string | null;
  authorizedToken?: string;
}) {
  const [action, setAction] = useState(''),
    [po, setPo] = useState(''),
    [reason, setReason] = useState(''),
    [reviewerToken, setReviewerToken] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const requestKey = useRef({ fingerprint: '', key: crypto.randomUUID() }),
    pending = useRef(false);
  const credential = authorizedToken ?? reviewerToken;
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
    <section id="human-review" className="review-panel" aria-label="Human review">
      <div className="review-intro">
        <span className="review-icon">
          <Icon name="shield" size={23} />
        </span>
        <div>
          <p className="eyebrow">AUTHORIZED REVIEW</p>
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
      <form onSubmit={submit}>
        <fieldset disabled={busy}>
          <legend className="sr-only">Review response</legend>
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
          {action === 'SELECT_PO' && (
            <div className="po-options">
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
            <small>Credentials stay in memory. Your action is recorded permanently.</small>
            <button
              className="button"
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
