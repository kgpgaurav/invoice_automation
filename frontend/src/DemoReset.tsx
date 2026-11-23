import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { components } from './api.generated';
type Preview = components['schemas']['ResetPreview'];
type Receipt = components['schemas']['ResetRecorded'];

export default function DemoReset({ token, onReset }: { token: string; onReset: () => void }) {
  const [enabled, setEnabled] = useState(false),
    [open, setOpen] = useState(false),
    [preview, setPreview] = useState<Preview | null>(null),
    [error, setError] = useState(''),
    [confirmation, setConfirmation] = useState(''),
    [busy, setBusy] = useState(false),
    [success, setSuccess] = useState('');
  const dialog = useRef<HTMLDialogElement>(null),
    input = useRef<HTMLInputElement>(null),
    requestKey = useRef('');
  useEffect(() => {
    const controller = new AbortController();
    api<Preview>('/demo/reset', token, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setEnabled(value.enabled === true);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [token]);
  useEffect(() => {
    if (open) {
      dialog.current?.showModal();
      input.current?.focus();
    } else dialog.current?.close();
  }, [open]);
  async function refreshPreview() {
    setOpen(true);
    setBusy(true);
    setPreview(null);
    setError('');
    setConfirmation('');
    setSuccess('');
    try {
      const value = await api<Preview>('/demo/reset', token);
      if (!value.enabled || !value.snapshot) throw new Error('Demo reset is unavailable.');
      requestKey.current = crypto.randomUUID();
      setPreview(value);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function reset() {
    if (busy || !preview?.snapshot || confirmation !== 'RESET DEMO') return;
    setBusy(true);
    setError('');
    try {
      await api<Receipt>('/demo/reset', token, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Idempotency-Key': requestKey.current },
        body: JSON.stringify({
          dataset: preview.dataset,
          snapshot: preview.snapshot,
          confirmation,
        }),
      });
      setOpen(false);
      setSuccess(
        'Demo reset complete. Prepared vendors and purchase orders were restored. New activity may already appear.',
      );
      dispatchEvent(new Event('ps1:record-updated'));
      onReset();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  if (!enabled) return null;
  return (
    <section className="panel demo-reset-panel" aria-label="Demo workspace controls">
      <div>
        <h2>Demo workspace</h2>
        <p>Start a fresh demonstration with the prepared vendors and purchase orders.</p>
      </div>
      <button className="button quiet reset-trigger" onClick={() => void refreshPreview()}>
        Reset demo data
      </button>
      {success && <p role="status">{success}</p>}
      <dialog
        className="reset-dialog"
        ref={dialog}
        aria-labelledby="reset-title"
        onCancel={(event) => {
          if (busy) event.preventDefault();
          else setOpen(false);
        }}
        onClose={() => {
          if (!busy) setOpen(false);
        }}
      >
        <h2 id="reset-title">Reset demo workspace</h2>
        <p>
          This permanently deletes every submitted PDF, processing record, review and approval in
          this shared workspace. Custom vendors and purchase orders are removed too.
        </p>
        <p>
          It restores <strong>3 demo vendors and 4 purchase orders with zero allocations</strong>.
          OpenAI connections are erased and submitters must reconnect their keys. Workspace login
          tokens stay the same.
        </p>
        {preview && (
          <dl className="reset-counts">
            <div>
              <dt>Submitted invoices</dt>
              <dd>{preview.counts?.runs ?? 0}</dd>
            </div>
            <div>
              <dt>Recorded approvals</dt>
              <dd>{preview.counts?.approval_ledger ?? 0}</dd>
            </div>
            <div>
              <dt>Vendors / purchase orders</dt>
              <dd>
                {preview.counts?.vendors ?? 0} / {preview.counts?.purchase_orders ?? 0}
              </dd>
            </div>
          </dl>
        )}
        {error && (
          <div role="alert" className="error">
            <p>{error}</p>
            <button className="text-link" disabled={busy} onClick={() => void refreshPreview()}>
              Refresh reset preview
            </button>
          </div>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void reset();
          }}
        >
          <label htmlFor="reset-confirmation">Type RESET DEMO to clear data for everyone</label>
          <input
            id="reset-confirmation"
            ref={input}
            value={confirmation}
            autoComplete="off"
            disabled={busy}
            onChange={(event) => setConfirmation(event.target.value)}
          />
          <div className="reset-actions">
            <button
              className="button quiet"
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Cancel reset
            </button>
            <button
              className="button reset-confirm"
              disabled={busy || !preview?.snapshot || confirmation !== 'RESET DEMO'}
            >
              {busy ? 'Please wait…' : 'Clear data & restore demo'}
            </button>
          </div>
        </form>
      </dialog>
    </section>
  );
}
