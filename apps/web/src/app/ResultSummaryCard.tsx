import { createResultDisplayState } from './resultDisplayState';

export function ResultSummaryCard({ payload }: { payload?: unknown }) {
  const state = createResultDisplayState(payload);

  return (
    <section aria-label="Result review summary">
      <h3>{state.title}</h3>
      <p>{state.detail}</p>
      <p>Status: {state.status}</p>
      <p>Review: {state.reviewRequired ? 'required' : 'not required'}</p>
      <p>Mode: {state.readOnly ? 'read-only' : 'write-enabled'}</p>
      <p>Execution: {state.executes ? 'enabled' : 'disabled'}</p>
    </section>
  );
}
