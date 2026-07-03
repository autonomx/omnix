import type { HermesSequencePreviewState } from './HermesSequencePreview';
import { HermesSequencePreview } from './HermesSequencePreview';

interface RpgHermesSequenceReviewPanelProps {
  error?: Error | null;
  isPending?: boolean;
  onReview: () => void;
  onUseFirstItem: (command: string) => void;
  sequence?: HermesSequencePreviewState | null;
}

export function RpgHermesSequenceReviewPanel({
  error,
  isPending = false,
  onReview,
  onUseFirstItem,
  sequence,
}: RpgHermesSequenceReviewPanelProps) {
  return (
    <section className="rpg-hermes-sequence-review" aria-label="Hermes sequence review">
      <div className="rpg-section-heading rpg-hermes-sequence-toolbar">
        <p className="eyebrow">Hermes sequence review</p>
        <button disabled={isPending} onClick={onReview} type="button">
          {isPending ? 'Reviewing...' : 'Review sequence'}
        </button>
      </div>
      {error ? <p className="rpg-empty-state" role="alert">Hermes sequence review failed: {error.message}</p> : null}
      <HermesSequencePreview sequence={sequence ?? null} onUseFirstItem={onUseFirstItem} />
    </section>
  );
}
