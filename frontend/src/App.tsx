import { useCallback, useEffect, useState } from 'react';
import { api, type RunPage, type Access } from './api';
import { Icon, Link } from './ui';
import Upload, { type UploadLimits } from './Upload';
import History from './History';
import RunView from './RunView';
import Overview from './Overview';
import PurchaseOrders from './PurchaseOrders';
import Scenarios from './Scenarios';
import OpenAIConnection, { disconnectOpenAI, type OpenAISession } from './OpenAIConnection';
import SubmitterRunView from './SubmitterRunView';

export default function App() {
  const [providerMode, setProviderMode] = useState<'server' | 'reviewer' | null>(null),
    [provider, setProvider] = useState<OpenAISession | null>(null);
  const [uploadLimits, setUploadLimits] = useState<UploadLimits | null>(null);
  const [query, setQuery] = useState(location.search),
    [token, setToken] = useState(''),
    [draft, setDraft] = useState('');
  const [accessOpen, setAccessOpen] = useState(false),
    [health, setHealth] = useState('Checking connection'),
    [notice, setNotice] = useState(''),
    [reviewCount, setReviewCount] = useState<number | null>(null);
  const [identity, setIdentity] = useState<{ credential: string; profile: Access } | null>(null);
  const [accessError, setAccessError] = useState('');
  const access = identity?.credential === token ? identity.profile : null;
  const pages = access?.pages ?? [];
  const submitter = access?.role === 'submitter';
  const canUpload = pages.includes('upload');
  const navigate = useCallback((to: string) => {
    history.pushState(null, '', to);
    setQuery(location.search);
    setNotice('');
    window.scrollTo(0, 0);
  }, []);
  useEffect(() => {
    const pop = () => setQuery(location.search);
    addEventListener('popstate', pop);
    return () => removeEventListener('popstate', pop);
  }, []);
  useEffect(() => {
    fetch('/api/v1/openai/config', { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then((data) => {
        if (
          (data.mode !== 'server' && data.mode !== 'reviewer') ||
          !Number.isSafeInteger(data.max_pdf_bytes) ||
          data.max_pdf_bytes <= 0 ||
          !Number.isSafeInteger(data.max_pdf_pages) ||
          data.max_pdf_pages <= 0
        )
          throw new Error();
        setUploadLimits({ max_pdf_bytes: data.max_pdf_bytes, max_pdf_pages: data.max_pdf_pages });
        setProviderMode(data.mode);
      })
      .catch(() =>
        setNotice('OpenAI configuration unavailable. Restart the updated API before uploading.'),
      );
    fetch('/api/v1/readyz')
      .then((r) => setHealth(r.ok ? 'API & database ready' : 'Database not ready'))
      .catch(() => setHealth('API unavailable'));
  }, []);
  useEffect(() => {
    setIdentity(null);
    setAccessError('');
    if (!token) return;
    const controller = new AbortController();
    api<Access>('/access', token, { signal: controller.signal })
      .then((profile) => {
        if (!controller.signal.aborted) setIdentity({ credential: token, profile });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setAccessError(e instanceof Error ? e.message : 'Access unavailable.');
      });
    return () => controller.abort();
  }, [token]);
  useEffect(() => {
    setReviewCount(null);
    if (!token || !access) return;
    if (access.role === 'submitter') {
      const p = new URLSearchParams(query);
      if (!p.has('view') && !p.has('run') && !p.has('po')) navigate('?view=upload');
      return;
    }
    const controller = new AbortController();
    let pending = false;
    function refreshCount() {
      if (pending) return;
      pending = true;
      void api<RunPage>('/runs?state=WAITING_REVIEW&limit=1', token, { signal: controller.signal })
        .then((s) => {
          if (controller.signal.aborted) return;
          setReviewCount(s.total_count);
          const p = new URLSearchParams(query);
          if (!p.has('view') && !p.has('run') && !p.has('po'))
            navigate(s.total_count ? '?view=review' : '?view=overview');
        })
        .catch(() => {})
        .finally(() => {
          pending = false;
        });
    }
    refreshCount();
    addEventListener('ps1:record-updated', refreshCount);
    const timer = setInterval(refreshCount, 10000);
    return () => {
      controller.abort();
      clearInterval(timer);
      removeEventListener('ps1:record-updated', refreshCount);
    };
  }, [token, query, navigate, access]);
  const params = new URLSearchParams(query),
    runId = params.get('run'),
    poId = params.get('po');
  const requested = params.get('view') ?? 'review';
  const view = runId
    ? 'run'
    : poId
      ? 'purchase-orders'
      : requested === 'upload'
        ? 'upload'
        : ['history', 'review', 'purchase-orders', 'overview', 'scenarios'].includes(requested)
          ? requested
          : 'review';
  const titles: Record<string, string> = {
    review: 'Review Queue',
    upload: 'Process Invoice',
    history: submitter ? 'My Invoices' : 'Invoice History',
    'purchase-orders': 'Purchase Orders',
    overview: 'Overview',
    scenarios: 'Try a Scenario',
    run: 'Invoice workspace',
  };
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="sidebar">
        <Link
          to={submitter ? '?view=upload' : '?view=review'}
          navigate={navigate}
          className="brand"
        >
          <span className="brand-mark">P1</span>
          <span>
            Invoice operations<small>PS-1 · ACCOUNTS PAYABLE</small>
          </span>
        </Link>
        <div className="workspace-label">
          <span className="workspace-avatar">Z</span>
          <div>
            {submitter ? 'Submission workspace' : 'Finance workspace'}
            <small>
              {access ? `${access.role} · ${access.actor_id}` : 'Private demonstration'}
            </small>
          </div>
          <Icon name="shield" size={16} />
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav aria-label="Primary navigation">
          {(
            [
              ['review', 'clock'],
              ['upload', 'upload'],
              ['history', 'file'],
              ['purchase-orders', 'grid'],
              ['overview', 'grid'],
            ] as const
          )
            .filter(([key]) => pages.includes(key))
            .map(([key, icon]) => (
              <Link
                key={key}
                to={'?view=' + key}
                navigate={navigate}
                className={view === key ? 'active' : ''}
              >
                <Icon name={icon} />
                {titles[key]}
                {key === 'review' && reviewCount != null && (
                  <span className="nav-count">{reviewCount}</span>
                )}
              </Link>
            ))}
        </nav>
        {pages.includes('scenarios') && (
          <Link to="?view=scenarios" navigate={navigate} className="scenario-entry">
            <span>Try a Scenario</span>
            <Icon name="arrow" size={16} />
          </Link>
        )}
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>
            <strong>{titles[view]}</strong>
          </div>
          <div className="topbar-actions">
            <span
              className={'connection ' + (health === 'API & database ready' ? 'connected' : '')}
            >
              <i />
              {health}
            </span>
            <button
              className="access-button"
              onClick={() => setAccessOpen((v) => !v)}
              aria-expanded={accessOpen || !token}
            >
              <Icon name="key" size={16} />
              {token ? 'Access connected' : 'Connect workspace'}
            </button>
            {canUpload && (
              <Link to="?view=upload" navigate={navigate} className="button small primary-process">
                <Icon name="upload" size={16} />
                Process Invoice
              </Link>
            )}
          </div>
        </header>
        {(!token || accessOpen) && (
          <section className="access-panel" aria-label="Workspace access">
            <div>
              <strong>{token ? 'Workspace access' : 'Connect to your finance workspace'}</strong>
              <p>
                Your access token determines your permitted screens and stays in this tab only. It
                is separate from an OpenAI API key.
              </p>
            </div>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await disconnectOpenAI(token, provider);
                  setProvider(null);
                  setIdentity(null);
                  setToken(draft.trim());
                  setDraft('');
                  setAccessOpen(false);
                } catch (e) {
                  setNotice(e instanceof Error ? e.message : 'Disconnect OpenAI first.');
                }
              }}
            >
              <label className="sr-only" htmlFor="workspace-token">
                Workspace access token
              </label>
              <input
                id="workspace-token"
                type="password"
                value={draft}
                autoComplete="off"
                placeholder="Workspace access token"
                onChange={(e) => setDraft(e.target.value)}
                required
              />
              <button className="button small">
                Connect <Icon name="arrow" size={16} />
              </button>
              {token && (
                <button
                  type="button"
                  className="button quiet small"
                  onClick={async () => {
                    try {
                      await disconnectOpenAI(token, provider);
                      setProvider(null);
                      setIdentity(null);
                      setToken('');
                      setDraft('');
                    } catch (e) {
                      setNotice(e instanceof Error ? e.message : 'Disconnect OpenAI first.');
                    }
                  }}
                >
                  Disconnect
                </button>
              )}
            </form>
          </section>
        )}
        <main id="main-content" tabIndex={-1}>
          {notice && (
            <div className="toast" role="status">
              {notice}
              <button aria-label="Dismiss notification" onClick={() => setNotice('')}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {token && !access ? (
            accessError ? (
              <div className="error" role="alert">
                {accessError}
              </div>
            ) : (
              <p role="status">Verifying access…</p>
            )
          ) : access && !runId && !pages.includes(view) ? (
            <div className="error" role="alert">
              You do not have access to this page.
            </div>
          ) : runId && submitter ? (
            <SubmitterRunView
              key={`${token}:${runId}`}
              runId={runId}
              token={token}
              navigate={navigate}
            />
          ) : runId ? (
            <RunView
              key={runId}
              runId={runId}
              token={token}
              navigate={navigate}
              notify={setNotice}
              reviewerToken={access?.role === 'reviewer' ? token : undefined}
            />
          ) : view === 'upload' ? (
            <>
              {providerMode === 'reviewer' && token && (
                <OpenAIConnection
                  key={token}
                  token={token}
                  connection={provider}
                  change={setProvider}
                />
              )}
              <Upload
                token={token}
                navigate={navigate}
                limits={uploadLimits}
                provider={provider}
                providerRequired={providerMode === 'reviewer'}
                configurationReady={providerMode !== null}
              />
            </>
          ) : view === 'overview' ? (
            <Overview token={token} navigate={navigate} />
          ) : view === 'purchase-orders' ? (
            <PurchaseOrders token={token} poId={poId} navigate={navigate} />
          ) : view === 'scenarios' ? (
            <Scenarios navigate={navigate} />
          ) : (
            <History
              key={view}
              token={token}
              params={params}
              navigate={navigate}
              queue={view === 'review'}
              ownOnly={submitter}
              canUpload={canUpload}
            />
          )}
          <footer>
            <span>PS-1 · Invoice operations</span>
            <span>
              Approval is authorization for downstream processing. No payment is executed.
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
