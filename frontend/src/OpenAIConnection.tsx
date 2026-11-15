import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, errorMessage, request } from './api';

export type OpenAISession = {
  session_token: string;
  models: string[];
  expires_at: string;
  model: string;
};
type Connection = Omit<OpenAISession, 'model'>;

export async function disconnectOpenAI(token: string, connection: OpenAISession | null) {
  if (connection)
    await request('/openai/session', token, {
      method: 'DELETE',
      headers: { 'X-OpenAI-Session': connection.session_token },
    });
}

export default function OpenAIConnection({
  token,
  connection,
  change,
}: {
  token: string;
  connection: OpenAISession | null;
  change: (value: OpenAISession | null) => void;
}) {
  const [key, setKey] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  async function connect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await api<Connection>('/openai/sessions', token, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key.trim() }),
      });
      if (active.current) change({ ...result, model: '' });
      else await disconnectOpenAI(token, { ...result, model: '' });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setKey('');
      setBusy(false);
    }
  }
  async function disconnect() {
    setBusy(true);
    setError('');
    try {
      await disconnectOpenAI(token, connection);
      change(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel provider-panel" aria-label="Your OpenAI connection">
      <h2>Your OpenAI connection</h2>
      <p>
        Each submitter connects their own OpenAI API key and selects a model. Extraction is charged
        to that OpenAI account. Financial reviewers do not need an OpenAI key.
      </p>
      <p>
        Connect once for multiple invoices in this tab, for up to 24 hours. You do not need to
        re-enter the key for each invoice. Reconnect for new uploads after refreshing, opening a new
        tab, disconnecting or expiry.
      </p>
      {connection ? (
        <>
          <label htmlFor="openai-model">Invoice extraction model</label>
          <select
            id="openai-model"
            value={connection.model}
            disabled={busy}
            onChange={(e) => change({ ...connection, model: e.target.value })}
          >
            <option value="">Select a model</option>
            {connection.models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
          <p>
            Access expires {new Date(connection.expires_at).toLocaleString('en-IN')}. Model access
            and billing permissions are checked by OpenAI when processing runs.
          </p>
          <button
            type="button"
            className="button quiet small"
            disabled={busy}
            onClick={() => void disconnect()}
          >
            Disconnect OpenAI
          </button>
        </>
      ) : (
        <form onSubmit={(e) => void connect(e)}>
          <label htmlFor="openai-key">Your OpenAI API key</label>
          <input
            id="openai-key"
            type="password"
            value={key}
            autoComplete="off"
            maxLength={1024}
            required
            disabled={busy}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="button small" disabled={!token || !key.trim() || busy}>
            {busy ? 'Checking model access…' : 'Connect OpenAI'}
          </button>
        </form>
      )}
      <p className="hint">
        The server temporarily encrypts your key for up to 24 hours. Disconnect erases it and blocks
        new calls; already dispatched calls may finish and be charged. Closing or refreshing the tab
        does not revoke the connection used by submitted runs. Your key is not saved in browser
        storage. Only account-listed models supported by this invoice pipeline are offered.
      </p>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
