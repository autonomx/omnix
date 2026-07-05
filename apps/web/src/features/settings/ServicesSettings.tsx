import { useEffect, useState } from 'react';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import { SettingsSection } from './SettingsPrimitives';

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
  useEffect(() => {
    omnixApiClient.listProviders().then(setPayload).catch(() => undefined);
  }, []);
  return (
    <div className="settings-category-panel">
      <div className="settings-category-title-row"><p className="eyebrow">Settings category</p><h2>Tools & Integrations</h2><p>Review configuration ownership and connected runtime services.</p></div>
      <SettingsSection title="Configuration ownership" description="This page delegates to existing owners instead of creating duplicate state." scope="global">
        <div className="settings-ownership-table">{ownershipRows.map(([label, owner, note]) => <div key={label}><strong>{label}</strong><span>{owner}</span><small>{note}</small></div>)}</div>
      </SettingsSection>
      <p>{payload?.providers.length ?? 0} services reported.</p>
    </div>
  );
}
