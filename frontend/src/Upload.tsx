import { useRef, useState, type FormEvent } from 'react';
import { api, errorMessage, type Intake } from './api';
import { Icon, type Navigate } from './ui';
import type { OpenAISession } from './OpenAIConnection';
import type { components } from './api.generated';

export type UploadLimits = Pick<
  components['schemas']['ProviderConfig'],
  'max_pdf_bytes' | 'max_pdf_pages'
>;

export default function Upload({
  token,
  navigate,
  limits,
  provider = null,
  providerRequired = false,
  configurationReady = true,
  mockMode = false,
}: {
  token: string;
  navigate: Navigate;
  limits: UploadLimits | null;
  provider?: OpenAISession | null;
  providerRequired?: boolean;
  configurationReady?: boolean;
  mockMode?: boolean;
}) {
  const sizeLabel = limits
    ? `${(limits.max_pdf_bytes / 1048576).toLocaleString('en-IN', { maximumFractionDigits: 2 })} MiB`
    : '';
  const providerReady =
    !providerRequired || Boolean(provider?.model && Date.parse(provider.expires_at) > Date.now());
  const [file, setFile] = useState<File | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [drag, setDrag] = useState(false);
  const key = useRef(crypto.randomUUID()),
    submitting = useRef(false),
    selection = useRef(0);
  async function choose(files: FileList | null) {
    const revision = ++selection.current;
    setError('');
    setFile(null);
    key.current = crypto.randomUUID();
    if (!files?.length || !limits) return;
    if (files.length !== 1) {
      setError('Choose one invoice PDF at a time.');
      return;
    }
    const candidate = files[0];
    if (
      !candidate.name.toLowerCase().endsWith('.pdf') ||
      candidate.size > limits.max_pdf_bytes ||
      candidate.size === 0
    ) {
      setError(`Choose a nonempty PDF of at most ${sizeLabel}.`);
      return;
    }
    if (new TextDecoder().decode(await candidate.slice(0, 5).arrayBuffer()) !== '%PDF-') {
      setError('This file does not have a PDF signature. Choose a valid PDF.');
      return;
    }
    if (revision === selection.current) setFile(candidate);
  }
  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!token || !file || !limits || submitting.current || !providerReady || !configurationReady)
      return;
    submitting.current = true;
    setBusy(true);
    setError('');
    const form = new FormData();
    form.append('file', file);
    if (providerRequired && provider) form.append('model_id', provider.model);
    try {
      const result = await api<Intake>('/invoices/process', token, {
        method: 'POST',
        body: form,
        headers: {
          'X-Idempotency-Key': key.current,
          ...(providerRequired && provider ? { 'X-OpenAI-Session': provider.session_token } : {}),
        },
      });
      navigate(`?run=${result.run_id}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Submit invoice</h1>
          <p>Upload a PDF invoice to track its processing status and outcome.</p>
        </div>
      </div>
      <div className="upload-layout">
        <section className="panel upload-panel">
          <div className="panel-heading">
            <h2>Upload an invoice</h2>
            <span className="muted">PDF documents only</span>
          </div>
          <p className="hint upload-limit-note" id="upload-limits" role="note">
            {limits
              ? `Allowed: PDF only, up to ${sizeLabel}, 1–${limits.max_pdf_pages} pages, unencrypted. Choose a smaller PDF if your file exceeds this limit.`
              : 'Loading PDF upload limits…'}
          </p>
          <form onSubmit={upload}>
            <label
              className={`dropzone ${drag ? 'dragging' : ''}`}
              htmlFor="invoice-file"
              onDragOver={(e) => {
                e.preventDefault();
                if (!busy) setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                if (!busy) void choose(e.dataTransfer.files);
              }}
            >
              <span className="upload-icon">
                <Icon name="upload" size={28} />
              </span>
              <strong>{file ? file.name : 'Drop your invoice here'}</strong>
              <span>
                {file ? (
                  `${(file.size / 1024).toFixed(1)} KB · selected`
                ) : (
                  <>
                    or <u>browse files</u> to choose a document
                  </>
                )}
              </span>
              <small>
                {limits
                  ? `1–${limits.max_pdf_pages} pages · up to ${sizeLabel} · unencrypted`
                  : 'Checking upload limits…'}
              </small>
              <input
                id="invoice-file"
                type="file"
                accept="application/pdf,.pdf"
                aria-label="Invoice PDF"
                aria-describedby="upload-limits"
                disabled={busy || !configurationReady || !limits}
                onChange={(e) => void choose(e.target.files)}
              />
            </label>
            {mockMode && (
              <div className="info-line" role="note" aria-label="Mock extraction">
                <Icon name="shield" size={16} />
                <span>
                  Mock workspaces accept only their own sample invoice PDFs. No live OpenAI call is
                  made.
                </span>
              </div>
            )}
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <button
              className="button upload-submit"
              disabled={!file || !token || !limits || busy || !providerReady || !configurationReady}
            >
              {busy ? 'Uploading invoice…' : 'Submit invoice'}
              <Icon name="arrow" size={18} />
            </button>
            {!token && <p className="hint">Connect the workspace above to upload.</p>}
            {token && !file && <p className="hint">Choose an invoice PDF to continue.</p>}
            {token && providerRequired && !providerReady && (
              <p className="hint">
                Complete OpenAI connection setup and select a model to enable submission.
              </p>
            )}
          </form>
        </section>
        <aside className="upload-explainer">
          <h2>After you submit</h2>
          <p>
            Submitters can upload invoices and track submissions made with their identity. Purchase
            order creation and financial review are handled by a financial reviewer.
          </p>
          <p>Track progress and read the outcome in My invoices.</p>
          {[
            [
              'file',
              'Document received',
              'Your original PDF is stored with its processing record.',
            ],
            ['shield', 'Processing', 'Invoice details and purchase order information are checked.'],
            [
              'check',
              'Outcome recorded',
              'See the decision or information needed from financial review.',
            ],
          ].map(([icon, title, text]) => (
            <div className="explain-step" key={title}>
              <Icon name={icon} />
              <div>
                <strong>{title}</strong>
                <p>{text}</p>
              </div>
            </div>
          ))}
        </aside>
      </div>
    </>
  );
}
