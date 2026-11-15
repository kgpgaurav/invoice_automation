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
}: {
  token: string;
  navigate: Navigate;
  limits: UploadLimits | null;
  provider?: OpenAISession | null;
  providerRequired?: boolean;
  configurationReady?: boolean;
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
          <p className="eyebrow">DOCUMENT INTAKE</p>
          <h1>Process Invoice</h1>
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
                  `${(file.size / 1024).toFixed(1)} KB · ready to upload`
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
            <div className="info-line">
              <Icon name="shield" size={16} />
              <span>
                Mock workspaces accept only their generated scenario PDFs. Other PDFs require an
                explicitly configured live workspace. Missing or uncertain invoice evidence goes to
                review.
              </span>
            </div>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
            <button
              className="button upload-submit"
              disabled={!file || !token || !limits || busy || !providerReady || !configurationReady}
            >
              {busy ? 'Creating invoice run…' : 'Process invoice'}
              <Icon name="arrow" size={18} />
            </button>
            {!token && <p className="hint">Connect the workspace above to upload.</p>}
            {token && providerRequired && !providerReady && (
              <p className="hint">Connect your OpenAI key and select a model before processing.</p>
            )}
          </form>
        </section>
        <aside className="upload-explainer">
          <h2>What happens after upload</h2>
          <p>The background worker processes your invoice and records the outcome.</p>
          {[
            ['file', 'Extract the printed facts', 'Preserve missing fields and original values.'],
            [
              'shield',
              'Verify against the source',
              'Check evidence, arithmetic, vendor and PO rules.',
            ],
            [
              'check',
              'Approve or ask for review',
              'No inferred PO, spending override or payment execution.',
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
          <small>Processing starts when the configured worker is available.</small>
        </aside>
      </div>
    </>
  );
}
