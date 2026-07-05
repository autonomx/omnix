import { useEffect, useState } from 'react';
import { omnixApiClient, type ModelResidencyDiagnostics, type ProviderFacadePayload } from '../../api/client';
import { SettingsSection } from './SettingsPrimitives';

export function CatalogPanel() {
  const [catalog, setCatalog] = useState<ProviderFacadePayload>();
  const [residency, setResidency] = useState<ModelResidencyDiagnostics>();
  useEffect(() => {
    let active = true;
    Promise.allSettled([omnixApiClient.listModels(), omnixApiClient.getModelResidency()]).then(([models, records]) => {
      if (!active) return;
      if (models.status === 'fulfilled') setCatalog(models.value);
      if (records.status === 'fulfilled') setResidency(records.value);
    });
    return () => { active = false; };
  }, []);
  return <SettingsSection title="Runtime catalog" scope="status"><p>{catalog?.models.length ?? 0} models discovered and {residency?.records.length ?? 0} runtime records reported.</p></SettingsSection>;
}
