import { StrictMode, useEffect, useRef, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import type { components } from './api.generated';
import './styles.css';

type Run = components['schemas']['RunStatus'];
type Intake = components['schemas']['IntakeResponse'];

async function api<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` },
  });
  const body = await response.json();
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message ?? `Request failed (${response.status}).`);
  }
  return body as T;
}

function App() {
  const [token, setToken] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [runId, setRunId] = useState(() => new URLSearchParams(location.search).get('run') ?? '');
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState('Checking API…');
  const key = useRef(crypto.randomUUID());

  useEffect(() => {
    let active = true;
    fetch('/api/v1/readyz').then(r => {
      if (active) setHealth(r.ok ? 'API & database ready' : 'API database not ready');
    }).catch(() => { if (active) setHealth('API unreachable'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!runId || !token) return;
    let active = true;
    const controller = new AbortController();
    async function refresh() {
      try {
        const result = await api<Run>(`/api/v1/runs/${encodeURIComponent(runId)}`, token,
          { signal: controller.signal });
        if (active) { setRun(result); setError(''); }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : 'Could not load run.');
      }
    }
    void refresh();
    const timer = setInterval(refresh, 2000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [runId, token]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !token) return;
    if (file.size > 12 * 1024 * 1024) { setError('PDF exceeds 12 MiB.'); return; }
    setBusy(true); setError('');
    const form = new FormData();
    form.append('file', file);
    try {
      const result = await api<Intake>('/api/v1/invoices/process', token, {
        method: 'POST', body: form, headers: { 'X-Idempotency-Key': key.current },
      });
      setRun(null); setRunId(result.run_id);
      history.replaceState(null, '', `?run=${result.run_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Upload failed.'); }
    finally { setBusy(false); }
  }

  return <>
    <header><a href="/" className="brand"><span className="mark">P1</span> Invoice workspace</a>
      <span className="health">{health}</span></header>
    <main>
      <p className="eyebrow">PS-1 / ZAMP CASE STUDY</p>
      <h1>Every invoice starts<br />with a clear record.</h1>
      <p className="intro">Upload a PDF and inspect its durable intake status.</p>
      <aside className="notice"><strong>Infrastructure preview</strong>
        <span>Intake works. Processing, AI extraction and financial decisions are not implemented.
        Uploaded runs stay queued.</span></aside>
      <div className="workspace">
        <section className="card">
          <div className="section-title"><span className="step">01</span><h2>Upload an invoice</h2></div>
          <form onSubmit={upload}>
            <label htmlFor="token">Local access token</label>
            <input id="token" type="password" autoComplete="off" value={token}
              onChange={e => setToken(e.target.value)} placeholder="Enter APP_API_TOKEN" required />
            <p className="hint">Held in memory only. Re-enter after refreshing the page.</p>
            <label className="file-zone" htmlFor="invoice">
              <span className="file-icon" aria-hidden="true">↑</span>
              <strong>{file ? file.name : 'Choose an invoice PDF'}</strong>
              <span>1–5 pages · up to 12 MiB · unencrypted</span>
              <input id="invoice" type="file" accept="application/pdf,.pdf" required disabled={busy}
                onChange={e => {
                  setFile(e.target.files?.[0] ?? null); key.current = crypto.randomUUID();
                }} />
            </label>
            <button disabled={busy || !file || !token} type="submit">{busy ? 'Storing invoice…' : 'Create intake run'} <span>↗</span></button>
          </form>
        </section>
        <section className="card" aria-live="polite">
          <div className="section-title"><span className="step">02</span><h2>Run status</h2></div>
          {!runId ? <div className="empty"><span className="empty-ring" />
            <h3>Ready when you are</h3><p>Your run ID and server status will appear here after upload.</p></div>
            : <div className="status-content">
              <span className="badge">{run?.job_state ?? 'Loading status'}</span>
              <dl><dt>Run ID</dt><dd>{runId}</dd><dt>Financial decision</dt>
                <dd>{run?.decision ?? 'None'}</dd>
                {run && <><dt>Created</dt><dd>{new Date(run.created_at).toLocaleString()}</dd></>}
              </dl><p>{run?.implementation_notice ?? 'Reading the persisted run from the API…'}</p>
              <p className="hint">Status refreshes from the server every 2 seconds.</p>
            </div>}
        </section>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <footer>PDFs stay in PostgreSQL. No AI request or financial posting occurs in this preview.</footer>
    </main>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
