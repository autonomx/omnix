import { useCallback, useEffect, useState } from 'react';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';

export type SettingsStatusSnapshot = {
  gateway: string;
  llm: string;
  tts: string;
  stt: string;
  image: string;
  hermes: string;
  activeJobs: number;
  loadedModels: number;
};

const initialStatus: SettingsStatusSnapshot = { gateway: 'Checking', llm: 'Checking', tts: 'Checking', stt: 'Checking', image: 'Checking', hermes: 'Checking', activeJobs: 0, loadedModels: 0 };
const terminal = new Set(['completed', 'complete', 'succeeded', 'success', 'done', 'failed', 'error', 'cancelled', 'canceled']);

function familyStatus(payload: ProviderFacadePayload | undefined, family: string): string {
  const provider = payload?.providers.find((entry) => entry.family === family || entry.capabilities.some((capability) => capability === family));
  return provider ? provider.status : 'Unavailable';
}

export function useSettingsStatus() {
  const [status, setStatus] = useState(initialStatus);
  const [refreshing, setRefreshing] = useState(false);
  const [lastError, setLastError] = useState('');

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const [runtime, providers, jobs, residency] = await Promise.allSettled([
      omnixApiClient.get<Record<string, unknown>>('/api/runtime/status'),
      omnixApiClient.listProviders(),
      omnixApiClient.listJobs(),
      omnixApiClient.getModelResidency(),
    ]);
    const providerPayload = providers.status === 'fulfilled' ? providers.value : undefined;
    const jobRows = jobs.status === 'fulfilled' ? jobs.value.jobs : [];
    const residencyRows = residency.status === 'fulfilled' ? residency.value.records ?? [] : [];
    const runtimeValue = runtime.status === 'fulfilled' ? runtime.value : {};
    setStatus({
      gateway: runtime.status === 'fulfilled' ? String(runtimeValue.status ?? (runtimeValue.ok ? 'Ready' : 'Degraded')) : 'Offline',
      llm: familyStatus(providerPayload, 'llm'),
      tts: familyStatus(providerPayload, 'tts'),
      stt: familyStatus(providerPayload, 'stt'),
      image: familyStatus(providerPayload, 'image'),
      hermes: String((runtimeValue.compatibility as Record<string, unknown> | undefined)?.hermes ?? 'Disabled'),
      activeJobs: jobRows.filter((job) => !terminal.has(String(job.status).toLowerCase())).length,
      loadedModels: Array.isArray(residencyRows) ? residencyRows.length : 0,
    });
    const failure = [runtime, providers, jobs, residency].find((result) => result.status === 'rejected');
    setLastError(failure?.status === 'rejected' ? String(failure.reason instanceof Error ? failure.reason.message : failure.reason) : '');
    setRefreshing(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { status, refreshing, lastError, refresh };
}
