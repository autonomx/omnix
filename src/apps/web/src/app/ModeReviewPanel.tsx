import type { OmnixModeId } from './omnixModeIds';
import { createOmnixModePreview } from './omnixModePreview';
import { makeTaskContract } from './taskContract';

export function ModeReviewPanel({ mode, input = '' }: { mode: OmnixModeId; input?: string }) {
  const preview = createOmnixModePreview(mode);
  const contract = makeTaskContract(mode, input);

  return (
    <section aria-label={`Mode review ${preview.label}`}>
      <h3>{preview.label}</h3>
      <p>Path: {preview.path}</p>
      <p>Owner: {preview.owner}</p>
      <p>Status: {preview.statusLabel}</p>
      <p>Review: {contract.review ? 'required' : 'not required'}</p>
    </section>
  );
}
