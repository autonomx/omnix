import type { HermesRpgSequenceResponse } from '../../api/hermesRpgSequenceClient';
import { HermesSequencePreview } from './HermesSequencePreview';
import { hermesSequencePreviewModel } from './hermesSequencePreviewModel';
import { hermesSequenceStatusLabel } from './hermesSequenceStatus';

interface HermesSequenceBoxProps {
  response?: HermesRpgSequenceResponse | null;
  onUseFirstItem?: (statement: string) => void;
}

export function HermesSequenceBox({ response, onUseFirstItem }: HermesSequenceBoxProps) {
  const sequence = hermesSequencePreviewModel(response);
  const status = hermesSequenceStatusLabel(response);

  return (
    <section className="rpg-card" aria-label="Hermes sequence box">
      <div className="rpg-section-heading">
        <p className="eyebrow">Hermes sequence</p>
        <span>{status}</span>
      </div>
      <HermesSequencePreview sequence={sequence} onUseFirstItem={onUseFirstItem} />
    </section>
  );
}
