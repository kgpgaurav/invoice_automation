import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { api, errorMessage, type RunPage, type Access } from './api';
import { Icon, Link } from './ui';
import Upload, { type UploadLimits } from './Upload';
import History from './History';
import ReviewQueue from './ReviewQueue';
import RunView from './RunView';
import Overview from './Overview';
import PurchaseOrders from './PurchaseOrders';
import Scenarios from './Scenarios';
import OpenAIConnection, { disconnectOpenAI, type OpenAISession } from './OpenAIConnection';
import SubmitterRunView from './SubmitterRunView';
import DemoAccess from './DemoAccess';

export default function App() {
  const [providerMode, setProviderMode] = useState<'server' | 'reviewer' | null>(null);
  const [mockMode, setMockMode] = useState(false);
  const [provider, setProvider] = useState<OpenAISession | null>(null);
  const [uploadLimits, setUploadLimits] = useState<UploadLimits | null>(null);
  const [configurationError, setConfigurationError] = useState('');
  const [query, setQuery] = useState(location.search);
  const [token, setToken] = useState('');
  const [draft, setDraft] = useState('');
  const [access, setAccess] = useState<Access | null>(null);
  const [accessError, setAccessError] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const [reviewCount, setReviewCount] = useState<number | null>(null);
  const authPending = useRef(false);
  const pages = access?.pages ?? [];
  const submitter = access?.role === 'submitter';
  const canUpload = pages.includes('upload');
  const home = submitter ? '?view=history' : '?view=review';
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
    const controller = new AbortController();
    fetch('/api/v1/openai/config', { cache: 'no-store', signal: controller.signal })
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
          data.max_pdf_pages <= 0 ||
          (data.mock_mode !== undefined && typeof data.mock_mode !== 'boolean')
        )
          throw new Error();
        if (controller.signal.aborted) return;
        setUploadLimits({ max_pdf_bytes: data.max_pdf_bytes, max_pdf_pages: data.max_pdf_pages });
        setProviderMode(data.mode);
        setMockMode(data.mock_mode === true);
        setConfigurationError('');
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setConfigurationError('Upload configuration could not be loaded. Refresh to try again.');
      });
    return () => controller.abort();
  }, []);
  async function connect(e: FormEvent) {
    e.preventDefault();
    if (authPending.current || !draft.trim()) return;
    authPending.current = true;
    setConnecting(true);
    setAccessError('');
    try {
      await disconnectOpenAI(token, provider);
      setProvider(null);
      setAccess(null);
      setToken('');
      const credential = draft.trim();
      const profile = await api<Access>('/access', credential);
      setToken(credential);
      setAccess(profile);
      setDraft('');
      setAccountOpen(false);
      const p = new URLSearchParams(location.search);
      if (!p.has('view') && !p.has('run') && !p.has('po'))
        navigate(profile.role === 'submitter' ? '?view=history' : '?view=review');
    } catch (e) {
      setAccessError(errorMessage(e));
    } finally {
      authPending.current = false;
      setConnecting(false);
    }
  }
  async function disconnect() {
    if (authPending.current) return;
    authPending.current = true;
    setConnecting(true);
    try {
      await disconnectOpenAI(token, provider);
      setProvider(null);
      setAccess(null);
      setToken('');
      setDraft('');
      setAccessError('');
      setAccountOpen(false);
      setReviewCount(null);
      navigate('?');
    } catch (e) {
      setNotice(errorMessage(e));
    } finally {
      authPending.current = false;
      setConnecting(false);
    }
  }
  useEffect(() => {
    setReviewCount(null);
    if (!access || !access.pages.includes('review')) return;
    const controller = new AbortController();
    let pending = false;
    const refresh = () => {
      if (pending) return;
      pending = true;
      void api<RunPage>('/runs?state=WAITING_REVIEW&limit=1', token, { signal: controller.signal })
        .then((value) => {
          if (!controller.signal.aborted) setReviewCount(value.total_count);
        })
        .catch(() => {})
        .finally(() => {
          pending = false;
        });
    };
    refresh();
    addEventListener('ps1:record-updated', refresh);
    const timer = setInterval(refresh, 10000);
    return () => {
      controller.abort();
      clearInterval(timer);
      removeEventListener('ps1:record-updated', refresh);
    };
  }, [access, token]);

  if (!access)
    return (
      <div className="access-screen">
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <div className="entry-brand">
          <Icon name="invoice" size={28} />
          Invoice operations
        </div>
        <main id="main-content" tabIndex={-1} className="access-main">
          <section className="access-card" aria-label="Workspace access">
            <Icon name="key" size={28} />
            <h1>Connect to your workspace</h1>
            <p>Enter a workspace access token to continue.</p>
            <form onSubmit={(e) => void connect(e)}>
              <label htmlFor="workspace-token">Workspace access token</label>
              <input
                id="workspace-token"
                type="password"
                value={draft}
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                required
                disabled={connecting}
                aria-invalid={!!accessError}
                aria-describedby={accessError ? 'access-error' : 'access-help'}
                onChange={(e) => {
                  setDraft(e.target.value);
                  setAccessError('');
                }}
              />
              {accessError && (
                <div id="access-error" className="error" role="alert">
                  {accessError}
                </div>
              )}
              <button className="button" disabled={connecting || !draft.trim()}>
                {connecting ? 'Verifying access…' : 'Connect'}
                <Icon name="arrow" size={18} />
              </button>
            </form>
            <p id="access-help" className="access-help">
              Your token opens the screens assigned to you. It stays in this tab and is separate
              from an OpenAI API key.
            </p>
            <DemoAccess
              disabled={connecting}
              onUse={(credential) => {
                setDraft(credential);
                setAccessError('');
                document.getElementById('workspace-token')?.focus();
              }}
            />
          </section>
        </main>
      </div>
    );

  const params = new URLSearchParams(query);
  const runId = params.get('run'),
    poId = params.get('po');
  const requested = params.get('view') ?? (submitter ? 'history' : 'review');
  const view = runId ? 'run' : poId ? 'purchase-orders' : requested;
  const allowed = view === 'connection' ? canUpload : pages.includes(view);
  const titles: Record<string, string> = {
    review: 'Review queue',
    upload: 'Submit invoice',
    history: submitter ? 'My invoices' : 'Invoice history',
    connection: 'OpenAI connection',
    'purchase-orders': 'Purchase orders',
    overview: 'Overview',
    scenarios: 'Try a scenario',
    run: 'Invoice details',
  };
  const navigation = submitter
    ? [
        ['history', 'file'],
        ['upload', 'upload'],
        ['connection', 'key'],
      ]
    : [
        ['review', 'list'],
        ['history', 'file'],
        ['purchase-orders', 'cart'],
        ['overview', 'chart'],
        ...(canUpload
          ? [
              ['upload', 'upload'],
              ['connection', 'key'],
            ]
          : []),
      ];
  const connectionActive = !!provider && new Date(provider.expires_at).getTime() > Date.now();
  const connected = !!provider?.model && connectionActive;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="sidebar">
        <Link to={home} navigate={navigate} className="brand">
          <span className="brand-mark">
            <Icon name="invoice" size={24} />
          </span>
          <span>
            Invoice operations
            <small>{submitter ? 'Submission workspace' : 'Finance workspace'}</small>
          </span>
        </Link>
        <nav aria-label="Primary navigation">
          {navigation
            .filter(([key]) => (key === 'connection' ? canUpload : pages.includes(key)))
            .map(([key, icon]) => (
              <Link
                key={key}
                to={'?view=' + key}
                navigate={navigate}
                className={view === key || (view === 'run' && key === 'history') ? 'active' : ''}
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
            Try a scenario
            <Icon name="arrow" size={16} />
          </Link>
        )}
        <div className="account-area">
          {accountOpen && (
            <section className="account-menu" aria-label="Workspace account">
              <strong>{access.actor_id}</strong>
              <p>
                {access.mode === 'shared'
                  ? 'Shared workspace access'
                  : 'Individual workspace access'}
              </p>
              <button
                className="button quiet small"
                disabled={connecting}
                onClick={() => void disconnect()}
              >
                {connecting ? 'Disconnecting…' : 'Disconnect'}
              </button>
            </section>
          )}
          <button
            className="account-button"
            aria-label={
              'Workspace account: ' +
              (submitter
                ? 'Invoice submitter'
                : access.role === 'reviewer'
                  ? 'Financial reviewer'
                  : 'Shared workspace')
            }
            aria-expanded={accountOpen}
            onClick={() => setAccountOpen(!accountOpen)}
          >
            <Icon name="user" />
            <span>
              {submitter
                ? 'Invoice submitter'
                : access.role === 'reviewer'
                  ? 'Financial reviewer'
                  : 'Shared workspace'}
            </span>
            <Icon name="down" size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <main id="main-content" tabIndex={-1}>
          {canUpload && configurationError && (view === 'upload' || view === 'connection') && (
            <div className="error" role="alert">
              {configurationError}
            </div>
          )}
          {notice && (
            <div className="toast" role="status">
              {notice}
              <button aria-label="Dismiss notification" onClick={() => setNotice('')}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {!runId && !allowed ? (
            <section className="panel empty-state" aria-label="Access unavailable" role="alert">
              <Icon name="shield" size={28} />
              <h1>This page is unavailable</h1>
              <p>You do not have access to this page with your workspace role.</p>
              <Link to={home} navigate={navigate} className="button quiet">
                Return to {submitter ? 'my invoices' : 'review queue'}
              </Link>
            </section>
          ) : runId && submitter ? (
            <SubmitterRunView
              key={token + ':' + runId}
              runId={runId}
              token={token}
              navigate={navigate}
            />
          ) : runId ? (
            <RunView
              key={token + ':' + runId}
              runId={runId}
              token={token}
              navigate={navigate}
              notify={setNotice}
              reviewerToken={access.role === 'reviewer' ? token : undefined}
            />
          ) : view === 'review' ? (
            <ReviewQueue
              token={token}
              params={params}
              navigate={navigate}
              notify={setNotice}
              reviewerToken={access.role === 'reviewer' ? token : undefined}
            />
          ) : view === 'connection' ? (
            <>
              <div className="page-heading">
                <div>
                  <h1>OpenAI connection</h1>
                  <p>
                    {providerMode === 'reviewer'
                      ? 'Connect your OpenAI API key and select a model before adding an invoice.'
                      : 'View the extraction setup for your workspace.'}
                  </p>
                </div>
              </div>
              {providerMode === 'reviewer' ? (
                <OpenAIConnection
                  key={token}
                  token={token}
                  connection={provider}
                  change={setProvider}
                />
              ) : (
                <section className="panel provider-panel">
                  <h2>
                    {providerMode === 'server'
                      ? 'Managed by your workspace'
                      : 'Loading connection settings…'}
                  </h2>
                  <p>
                    {providerMode === 'server'
                      ? 'Your workspace supplies the extraction connection. You do not need to enter an OpenAI key here.'
                      : 'Upload configuration is not ready yet. Refresh if this persists.'}
                  </p>
                </section>
              )}
              {(connected || providerMode === 'server') && (
                <Link to="?view=upload" navigate={navigate} className="button">
                  Continue to submit invoice
                  <Icon name="arrow" size={18} />
                </Link>
              )}
            </>
          ) : view === 'upload' ? (
            <>
              {providerMode === 'reviewer' && (
                <section className="upload-prerequisite" aria-label="Extraction connection">
                  <Icon name={connected ? 'check' : 'key'} />
                  <div>
                    <strong>
                      {connected
                        ? 'OpenAI connection ready'
                        : provider && !connectionActive
                          ? 'Reconnect OpenAI before adding an invoice'
                          : connectionActive
                            ? 'Select a model before adding an invoice'
                            : 'Add your OpenAI API key first'}
                    </strong>
                    <p>
                      {connected
                        ? 'Selected model: ' + provider?.model
                        : provider && !connectionActive
                          ? 'Open OpenAI connection, disconnect the expired connection, then reconnect your key and choose a model for new invoices.'
                          : connectionActive
                            ? 'Your key is connected. Open OpenAI connection and choose an Invoice extraction model, then return here to add your PDF.'
                            : 'Open OpenAI connection, enter your own API key, click Connect OpenAI and choose an Invoice extraction model. Then return here to add your PDF.'}
                    </p>
                  </div>
                  <Link to="?view=connection" navigate={navigate} className="button quiet small">
                    {connected ? 'Manage connection' : 'Set up connection'}
                    <Icon name="arrow" size={16} />
                  </Link>
                </section>
              )}
              <Upload
                token={token}
                mockMode={mockMode}
                navigate={navigate}
                limits={uploadLimits}
                provider={provider}
                providerRequired={providerMode === 'reviewer'}
                configurationReady={providerMode !== null}
              />
            </>
          ) : view === 'overview' ? (
            <Overview token={token} navigate={navigate} canReset={access.role === 'reviewer'} />
          ) : view === 'purchase-orders' ? (
            <PurchaseOrders
              token={token}
              poId={poId}
              navigate={navigate}
              canCreate={access.role === 'reviewer'}
            />
          ) : view === 'scenarios' ? (
            <Scenarios navigate={navigate} />
          ) : (
            <History
              key={view}
              token={token}
              params={params}
              navigate={navigate}
              ownOnly={submitter}
              canUpload={canUpload}
            />
          )}
        </main>
      </div>
    </div>
  );
}
