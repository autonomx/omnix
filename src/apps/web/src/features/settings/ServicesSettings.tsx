import { useCallback, useEffect, useState } from 'react';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import { SettingsSection, SettingsStatusRow } from './SettingsPrimitives';

export type ServiceStatusPayload = {
  ok?: boolean;
  enabled?: boolean;
  mode?: string;
  source?: string;
  error?: string;
  [key: string]: unknown;
};

export function summarizeServiceStatus(status: ServiceStatusPayload | undefined): string {
  if (!status) return 'Unavailable';
  if (status.error) return 'Error';
  if (status.enabled === false) return 'Disabled';
  if (status.ok === true) return 'Ready';
  return typeof status.mode === 'string' && status.mode ? status.mode : 'Reported';
}

const ownershipRows = [
  ['Assistant actions', 'Assistant configuration API', 'Runtime-owned'],
  ['Provider accounts', 'Provider registry', 'Adapter-owned'],
  ['Hermes routing', 'Hermes API', 'Diagnostic access'],
] as const;

export function ServicesSettings() {
  const [payload, setPayload] = useState<ProviderFacadePayload>();
  const [service, setService] = useState<ServiceStatusPayload>();
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const refresh = useCallback(async () => {
    setLoading(true);
    const [providers, status] = await Promise.allSettled([
      omnixApiClient.listProviders(),
      omnixApiClient.get<ServiceStatusPayload>('/api/hermes/status'),
    ]);
    if (providers.status === 'fulfilled') setPayload(providers.value);
    if (status.status === 'fulfilled') setService(status.value);
    const failure = [providers, status].find((result) => result.status === 'rejected');
    setMessage(failure?.status === 'rejected' ? (failure.reason instanceof Error ? failure.reason.message : 'Service status is unavailable.') : 'Service status refreshed.');
    setLoading(false);
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const connected = (payload?.providers ?? []).filter((provider) => provider.status === 'available' || provider.status === 'configured');
  return (
    <div className="settings-category-panel">
      <div className="settings-category-title-row"><p className="eyebrow">Settings category</p><h2>Tools & Integrations</h2><p>Review configuration ownership and connected runtime services.</p></div>
      <SettingsSection title="Configuration ownership" description="This page delegates to existing owners instead of creating duplicate state." scope="global">
        <div className="settings-ownership-table">{ownershipRows.map(([label, owner, note]) => <div key={label}><strong>{label}</strong><span>{owner}</span><small>{note}</small></div>)}</div>
      </SettingsSection>
      <SettingsSection title="Connected services" description="Connection state comes from the provider registry." actions={<button type="button" className="settings-secondary-button" disabled={loading} onClick={() => void refresh()}>{loading ? 'Refreshing…' : 'Refresh'}</button>}>
        {connected.length ? <div className="settings-status-list">{connected.map((provider) => <SettingsStatusRow key={provider.id} label={provider.label} value={provider.status} tone="ready" />)}</div> : <div className="settings-planned-state"><strong>No configured services reported</strong><p>Use the owning provider module to configure a service.</p></div>}
      </SettingsSection>
      <SettingsSection title="Hermes diagnostics" description="Settings reads the existing diagnostics contract.">
        <SettingsStatusRow label="Hermes" value={summarizeServiceStatus(service)} tone={service?.ok ? 'ready' : 'idle'} />
        <dl className="settings-detail-grid"><div><dt>Mode</dt><dd>{String(service?.mode ?? 'Not reported')}</dd></div><div><dt>Source</dt><dd>{String(service?.source ?? 'Hermes diagnostics API')}</dd></div></dl>
        {message ? <p className="settings-inline-status" role="status">{message}</p> : null}
      </SettingsSection>
    </div>
  );
}
