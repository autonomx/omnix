import type { OmnixModeId } from './omnixModeIds';
import { createOmnixModePreview } from './omnixModePreview';

export function ModePreviewCard({ mode }: { mode: OmnixModeId }) {
  const value = createOmnixModePreview(mode);

  return (
    <section aria-label={`Mode ${value.label}`}>
      <h3>{value.label}</h3>
      <p>Path: {value.path}</p>
      <p>Owner: {value.owner}</p>
      <p>Status: {value.statusLabel}</p>
    </section>
  );
}
