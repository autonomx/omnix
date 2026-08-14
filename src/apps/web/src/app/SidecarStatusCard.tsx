import { createServiceCardState } from './serviceCardState';
import { createSidecarStatusState } from './sidecarStatusState';

export function SidecarStatusCard({ payload, error }: { payload?: unknown; error?: string | null }) {
  const status = createSidecarStatusState({ payload: payload as { ok?: boolean; status?: string; enabled?: boolean } | null, error });
  const card = createServiceCardState('Sidecar', status.status);

  return (
    <section aria-label="Sidecar status">
      <h3>{card.label}</h3>
      <p>Status: {card.status}</p>
      <p>{status.message}</p>
      <p>Mode: {status.readOnly ? 'read-only' : 'write-enabled'}</p>
      <p>Execution: {status.executes ? 'enabled' : 'disabled'}</p>
    </section>
  );
}
