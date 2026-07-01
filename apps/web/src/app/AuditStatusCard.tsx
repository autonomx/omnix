import { createAuditDisplayState } from './auditDisplayState';

export function AuditStatusCard({ payload }: { payload?: unknown }) {
  const state = createAuditDisplayState(payload);

  return (
    <section aria-label="Audit status">
      <h3>Audit status</h3>
      <p>Source: {state.source}</p>
      <p>Status: {state.status}</p>
      <p>Timestamp: {state.timestamp || 'not recorded'}</p>
      <p>Review: {state.reviewRequired ? 'required' : 'not required'}</p>
      <p>Mode: {state.readOnly ? 'read-only' : 'write-enabled'}</p>
      <p>Execution: {state.executes ? 'enabled' : 'disabled'}</p>
    </section>
  );
}
