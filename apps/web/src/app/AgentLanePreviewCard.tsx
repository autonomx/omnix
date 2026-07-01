import { createOmnixModePreview } from './omnixModePreview';
import { makeTaskContract } from './taskContract';

export function AgentLanePreviewCard({ input = '' }: { input?: string }) {
  const preview = createOmnixModePreview('agent');
  const contract = makeTaskContract('agent', input);

  return (
    <section aria-label="Agent lane preview">
      <h3>{preview.label}</h3>
      <p>Path: {preview.path}</p>
      <p>Owner: {preview.owner}</p>
      <p>Status: {preview.statusLabel}</p>
      <p>Review: {contract.review ? 'required' : 'not required'}</p>
    </section>
  );
}
