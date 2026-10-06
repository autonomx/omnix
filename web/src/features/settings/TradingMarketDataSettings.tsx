import { useEffect, useState } from 'react';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import {
  tradingMarketDataApi,
  type CoinMarketCapCredentialStatus,
  type IbkrSettings,
  type IbkrSettingsStatus,
} from './tradingMarketDataApi';

function sourceLabel(source: CoinMarketCapCredentialStatus['api_key_source']): string {
  if (source === 'environment') return 'Environment variable';
  if (source === 'os_protected_store') return 'Windows user-scoped protected store';
  return 'Not configured';
}

function ibkrSourceLabel(source: IbkrSettingsStatus['settings_source']): string {
  if (source === 'omnix_settings') return 'Omnix settings';
  if (source === 'environment') return 'Legacy environment variables';
  if (source === 'runtime_arguments') return 'Runtime arguments';
  return 'Omnix defaults';
}

function ibkrConnectionLabel(status: IbkrSettingsStatus['connection_status']): string {
  if (status === 'connected') return 'Connected to IB Gateway';
  if (status === 'client_unavailable') return 'Official ibapi package missing';
  if (status === 'disabled') return 'Disabled';
  return 'Gateway not connected';
}

const DEFAULT_IBKR_FORM: IbkrSettings = {
  enabled: false,
  monitor_enabled: true,
  host: '127.0.0.1',
  port: 4002,
  client_id: 71,
  live_authority_enabled: false,
  recovery_authority_enabled: false,
};

export function TradingMarketDataSettings() {
  const [status, setStatus] = useState<CoinMarketCapCredentialStatus>();
  const [ibkrStatus, setIbkrStatus] = useState<IbkrSettingsStatus>();
  const [ibkrForm, setIbkrForm] = useState<IbkrSettings>(DEFAULT_IBKR_FORM);
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [ibkrBusy, setIbkrBusy] = useState(false);
  const [message, setMessage] = useState('Checking market-data credentials...');
  const [ibkrMessage, setIbkrMessage] = useState('Checking IBKR connection...');

  const load = async () => {
    try {
      const [next, nextIbkr] = await Promise.all([
        tradingMarketDataApi.coinmarketcapCredentials(),
        tradingMarketDataApi.ibkrSettings(),
      ]);
      setStatus(next);
      setIbkrStatus(nextIbkr);
      setIbkrForm(nextIbkr.settings);
      setMessage(next.configured
        ? 'CoinMarketCap market-cap data is configured.'
        : 'Add a CoinMarketCap API key to enable CRYPTOCAP symbols and dominance charts.');
      setIbkrMessage(ibkrConnectionLabel(nextIbkr.connection_status));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Market-data credential status is unavailable.');
      setIbkrMessage(error instanceof Error ? error.message : 'IBKR connection status is unavailable.');
    }
  };

  useEffect(() => { void load(); }, []);

  const save = async () => {
    const value = apiKey.trim();
    if (!value) {
      setMessage('Enter a CoinMarketCap API key. The key is never returned to the browser after saving.');
      return;
    }
    setBusy(true);
    try {
      const next = await tradingMarketDataApi.saveCoinMarketCapCredentials({ api_key: value });
      setStatus(next);
      setApiKey('');
      setMessage('CoinMarketCap API key saved in the OS-protected store.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'CoinMarketCap credential update failed.');
    } finally {
      setBusy(false);
    }
  };

  const saveIbkr = async () => {
    setIbkrBusy(true);
    try {
      const next = await tradingMarketDataApi.saveIbkrSettings(ibkrForm);
      setIbkrStatus(next);
      setIbkrForm(next.settings);
      setIbkrMessage(ibkrConnectionLabel(next.connection_status));
    } catch (error) {
      setIbkrMessage(error instanceof Error ? error.message : 'IBKR settings update failed.');
    } finally {
      setIbkrBusy(false);
    }
  };

  const clearStored = async () => {
    if (!status || !status.api_key_editable || status.api_key_source !== 'os_protected_store') {
      setMessage('Environment-owned values must be changed outside Omnix.');
      return;
    }
    if (!window.confirm('Clear the CoinMarketCap key stored by Omnix?')) return;
    setBusy(true);
    try {
      const next = await tradingMarketDataApi.saveCoinMarketCapCredentials({ clear_api_key: true });
      setStatus(next);
      setApiKey('');
      setMessage(next.configured
        ? 'Stored key cleared; an environment-owned key is still active.'
        : 'Stored CoinMarketCap key cleared.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'CoinMarketCap credential update failed.');
    } finally {
      setBusy(false);
    }
  };

  const editable = status?.api_key_editable ?? true;
  return (
    <div className="settings-category-panel" aria-labelledby="settings-category-title">
      <div className="settings-category-title-row">
        <p className="eyebrow">Settings category</p>
        <h2 id="settings-category-title">Trading &amp; Market Data</h2>
        <p>Configure market-data providers used by charts, arithmetic symbols, watchlists, and replay.</p>
      </div>

      <SettingsSection
        title="CoinMarketCap"
        description="Historical crypto market-cap data for CRYPTOCAP symbols such as TOTAL3 and USDT.D."
        scope="global"
      >
        <div className="settings-form-grid">
          <SettingsField
            label="API key"
            help={`${status ? sourceLabel(status.api_key_source) : 'Checking credential source...'}. Environment override: COINMARKETCAP_API_KEY or CMC_PRO_API_KEY.`}
          >
            <input
              aria-label="CoinMarketCap API key"
              type="password"
              autoComplete="new-password"
              value={apiKey}
              disabled={busy || !editable}
              placeholder={status?.configured ? status.api_key_masked : 'Enter API key'}
              onChange={(event) => setApiKey(event.currentTarget.value)}
            />
            <button type="button" className="settings-primary-button" disabled={busy || !editable || !apiKey.trim()} onClick={() => void save()}>
              {busy ? 'Saving...' : 'Save key'}
            </button>
            {status?.configured && status.api_key_source === 'os_protected_store' ? (
              <button type="button" className="settings-secondary-button" disabled={busy} onClick={() => void clearStored()}>Clear stored key</button>
            ) : null}
          </SettingsField>
          <div className="settings-status-card">
            <h3>Coverage</h3>
            <p>CRYPTOCAP: TOTAL, TOTAL2, TOTAL3, BTC, ETH, USDT, and dominance symbols ending in <code>.D</code>.</p>
            <p className="settings-inline-status" role="status">{message}</p>
          </div>
        </div>
        <p className="settings-inline-status">Secret values are never stored in chart or strategy configuration. UI-entered keys are protected with the current Windows user's DPAPI key.</p>
      </SettingsSection>

      <SettingsSection
        title="Interactive Brokers (IBKR)"
        description="Connect Omnix to a locally running IB Gateway for market-data observation and repair. Login credentials stay inside IB Gateway."
        scope="global"
      >
        <div className="settings-form-grid">
          <div className="settings-form-grid">
            <SettingsField label="Enable IBKR" help="Omnix uses the official ibapi client only when this is enabled.">
              <input
                aria-label="Enable IBKR"
                type="checkbox"
                checked={ibkrForm.enabled}
                disabled={ibkrBusy}
                onChange={(event) => {
                  const { checked } = event.currentTarget;
                  setIbkrForm((current) => ({ ...current, enabled: checked }));
                }}
              />
            </SettingsField>
            <SettingsField label="Gateway host">
              <input
                aria-label="Gateway host"
                value={ibkrForm.host}
                disabled={ibkrBusy}
                onChange={(event) => setIbkrForm((current) => ({ ...current, host: event.currentTarget.value }))}
              />
            </SettingsField>
            <SettingsField label="Gateway socket port" help="IB Gateway paper default is 4002; live default is 4001.">
              <input
                aria-label="Gateway socket port"
                type="number"
                min="1"
                max="65535"
                value={ibkrForm.port}
                disabled={ibkrBusy}
                onChange={(event) => setIbkrForm((current) => ({ ...current, port: Number(event.currentTarget.value) }))}
              />
            </SettingsField>
            <SettingsField label="Client ID" help="Use a unique client ID for this Omnix connection.">
              <input
                aria-label="IBKR client ID"
                type="number"
                min="0"
                max="32767"
                value={ibkrForm.client_id}
                disabled={ibkrBusy}
                onChange={(event) => setIbkrForm((current) => ({ ...current, client_id: Number(event.currentTarget.value) }))}
              />
            </SettingsField>
            <SettingsField label="Start market-data monitor" help="Keeps the zero-authority observation stream reconciled for active strategy demand.">
              <input
                aria-label="Start IBKR market-data monitor"
                type="checkbox"
                checked={ibkrForm.monitor_enabled}
                disabled={ibkrBusy}
                onChange={(event) => {
                  const { checked } = event.currentTarget;
                  setIbkrForm((current) => ({ ...current, monitor_enabled: checked }));
                }}
              />
            </SettingsField>
            <SettingsField label="Allow live-data authority" help="Requires fresh, complete, live-entitled quotes. This never grants order execution authority.">
              <input
                aria-label="Allow IBKR live-data authority"
                type="checkbox"
                checked={ibkrForm.live_authority_enabled}
                disabled={ibkrBusy}
                onChange={(event) => {
                  const { checked } = event.currentTarget;
                  setIbkrForm((current) => ({ ...current, live_authority_enabled: checked }));
                }}
              />
            </SettingsField>
            <SettingsField label="Allow historical recovery authority" help="Allows IBKR exact-range history into canonical gap repair after your soak review.">
              <input
                aria-label="Allow IBKR historical recovery authority"
                type="checkbox"
                checked={ibkrForm.recovery_authority_enabled}
                disabled={ibkrBusy}
                onChange={(event) => {
                  const { checked } = event.currentTarget;
                  setIbkrForm((current) => ({ ...current, recovery_authority_enabled: checked }));
                }}
              />
            </SettingsField>
            <button type="button" className="settings-primary-button" disabled={ibkrBusy} onClick={() => void saveIbkr()}>
              {ibkrBusy ? 'Saving...' : 'Save IBKR settings'}
            </button>
          </div>
          <div className="settings-status-card">
            <h3>{ibkrStatus ? ibkrConnectionLabel(ibkrStatus.connection_status) : 'Checking IBKR...'}</h3>
            <p>Source: {ibkrStatus ? ibkrSourceLabel(ibkrStatus.settings_source) : 'Checking...'}</p>
            <p>Official Python API: {ibkrStatus?.official_ibapi_available ? 'installed' : 'not installed'}</p>
            <p>Live-data authority: {ibkrStatus?.settings.live_authority_enabled ? 'enabled' : 'observation only'}</p>
            <p>Recovery authority: {ibkrStatus?.settings.recovery_authority_enabled ? 'enabled' : 'off'}</p>
            <p>Order execution authority: disabled</p>
            <p className="settings-inline-status" role="status">{ibkrMessage}</p>
            {ibkrStatus?.last_error ? <p className="settings-field-help">Last error: {ibkrStatus.last_error}</p> : null}
          </div>
        </div>
        <p className="settings-inline-status">Live-data authority and recovery authority remain off by default. Omnix stores no IBKR username, password, or API secret.</p>
      </SettingsSection>
    </div>
  );
}
