import { useEffect, useState } from 'react';
import { tradingExecutionApi, type AlpacaIexCredentialStatus } from './tradingExecutionApi';

function sourceLabel(source: AlpacaIexCredentialStatus['api_key_source']): string {
  if (source === 'environment') return 'Environment';
  if (source === 'os_protected_store') return 'Windows DPAPI';
  return 'Not configured';
}

export function TradingStrategyExecutionCredentials() {
  const [status, setStatus] = useState<AlpacaIexCredentialStatus | null>(null);
  const [apiKeyId, setApiKeyId] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Loading execution credentials…');

  const refresh = async () => {
    try {
      const next = await tradingExecutionApi.alpacaCredentials();
      setStatus(next);
      setMessage(next.configured
        ? 'Alpaca IEX execution data is configured.'
        : 'Alpaca IEX credentials are required before AUTO PAPER can obtain executable US-equity quotes.');
    } catch (error) {
      setStatus(null);
      setMessage(error instanceof Error ? error.message : String(error));
    }
  };

  useEffect(() => { void refresh(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const input: { api_key_id?: string; secret_key?: string } = {};
      if (apiKeyId.trim()) input.api_key_id = apiKeyId.trim();
      if (secretKey.trim()) input.secret_key = secretKey.trim();
      if (!Object.keys(input).length) {
        setMessage('Enter a new API Key ID or Secret Key. Blank fields leave the stored value unchanged.');
        return;
      }
      const next = await tradingExecutionApi.saveAlpacaCredentials(input);
      setStatus(next);
      setApiKeyId('');
      setSecretKey('');
      setMessage(next.configured
        ? 'Alpaca IEX credentials saved in the OS-protected store. Secret values are not returned to the browser.'
        : 'Credential update saved, but both Alpaca fields are still required.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const clearStored = async () => {
    if (!status) return;
    const clearApi = status.api_key_editable && status.api_key_source === 'os_protected_store';
    const clearSecret = status.secret_key_editable && status.secret_key_source === 'os_protected_store';
    if (!clearApi && !clearSecret) {
      setMessage('No UI-owned Alpaca credentials can be cleared. Environment-owned values must be changed outside Omnix.');
      return;
    }
    if (!window.confirm('Clear the Alpaca credentials stored by Omnix? Environment-owned values are not changed.')) return;
    setBusy(true);
    try {
      const next = await tradingExecutionApi.saveAlpacaCredentials({
        clear_api_key_id: clearApi,
        clear_secret_key: clearSecret,
      });
      setStatus(next);
      setApiKeyId('');
      setSecretKey('');
      setMessage(next.configured
        ? 'UI-owned credentials were cleared; environment-owned credentials still keep Alpaca configured.'
        : 'Stored Alpaca credentials cleared. AUTO PAPER will fail closed until credentials are configured again.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="strategy-provider-card" aria-label="Alpaca IEX execution credentials">
      <header>
        <div>
          <strong>Alpaca IEX execution data</strong>
          <small>Authoritative real-time quote source for US-equity AUTO PAPER. Yahoo never authorizes a fill.</small>
        </div>
        <span data-ready={status?.configured ? 'true' : 'false'}>{status?.configured ? 'Configured' : 'Credentials required'}</span>
      </header>

      <div className="strategy-provider-status-grid">
        <div><small>API key</small><strong>{status?.api_key_id_masked || 'Not configured'}</strong><span>{status ? sourceLabel(status.api_key_source) : 'Checking…'}</span></div>
        <div><small>Secret</small><strong>{status?.secret_key_source === 'missing' ? 'Not configured' : '••••••••'}</strong><span>{status ? sourceLabel(status.secret_key_source) : 'Checking…'}</span></div>
        <div><small>Storage</small><strong>{status?.storage ?? 'Checking…'}</strong><span>Secrets are never persisted in strategy configuration.</span></div>
      </div>

      <div className="strategy-provider-credential-grid">
        <label>
          <span>Alpaca API Key ID<small>Blank leaves the existing value unchanged.</small></span>
          <input
            type="password"
            autoComplete="off"
            value={apiKeyId}
            disabled={busy || status?.api_key_editable === false}
            placeholder={status?.api_key_source === 'environment' ? 'Environment-owned' : 'Enter API key ID'}
            onChange={(event) => setApiKeyId(event.target.value)}
          />
        </label>
        <label>
          <span>Alpaca Secret Key<small>Never returned after saving.</small></span>
          <input
            type="password"
            autoComplete="new-password"
            value={secretKey}
            disabled={busy || status?.secret_key_editable === false}
            placeholder={status?.secret_key_source === 'environment' ? 'Environment-owned' : 'Enter secret key'}
            onChange={(event) => setSecretKey(event.target.value)}
          />
        </label>
        <div className="strategy-provider-actions">
          <button type="button" className="primary" disabled={busy || !status || (!status.api_key_editable && !status.secret_key_editable)} onClick={() => void save()}>{busy ? 'Saving…' : 'Save credentials'}</button>
          <button type="button" disabled={busy || !status} onClick={() => void clearStored()}>Clear stored</button>
          <button type="button" disabled={busy} onClick={() => void refresh()}>Refresh status</button>
        </div>
      </div>
      <p className="strategy-provider-message" role="status">{message}</p>
      <small className="strategy-provider-security-note">On Windows, UI-entered credentials are encrypted with the current user’s DPAPI key. Environment variables remain authoritative and cannot be overwritten from this screen.</small>
    </section>
  );
}
