import { Button } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { CAPABILITIES_QUERY_KEY, modelPacksClient, type CapabilitiesResponse } from './api/modelPacksClient';
import './setup.css';

/** The bundle capabilities a workspace can ask about (catalog v2 bundles). */
export type ModelCapability = 'live_stt' | 'tts' | 'stt_batch' | 'image';

/**
 * Whether a capability's models are installed. Outside the desktop app (or before the answer arrives) it counts as
 * installed: there the services are set up separately, and a workspace keeps its usual behaviour.
 */
export function useCapability(capability: ModelCapability): { installed: boolean; running: boolean; label: string; desktop: boolean } {
  const query = useQuery<CapabilitiesResponse>({
    queryKey: CAPABILITIES_QUERY_KEY,
    queryFn: () => modelPacksClient.capabilities(),
    staleTime: 15_000,
    retry: false,
  });
  const entry = query.data?.capabilities?.[capability];
  const desktop = Boolean(query.data?.desktop);
  return {
    installed: !desktop || entry?.installed !== false,
    running: Boolean(entry?.running),
    label: entry?.label ?? '',
    desktop,
  };
}

/**
 * In the desktop app, where a workspace needs a model that is not downloaded yet: says so and offers the download in
 * place (desktop roadmap §4.5, "features adapt"). Renders nothing when the capability is installed, or outside the
 * desktop app.
 */
export function CapabilityNotice({ capability, purpose }: { capability: ModelCapability; purpose: string }) {
  const state = useCapability(capability);
  if (state.installed) return null;
  return (
    <div className="setup-capability-notice" role="status">
      <span>{purpose} needs {state.label ? state.label.toLowerCase() : 'a model'}, which is not on this computer yet.</span>
      <Button component="a" href="/setup" size="compact-xs" variant="light">Download {state.label || 'it'}</Button>
    </div>
  );
}
