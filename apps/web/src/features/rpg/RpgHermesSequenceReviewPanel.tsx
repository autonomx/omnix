import type { HermesSequencePreviewState } from './HermesSequencePreview';
import { HermesSequencePreview } from './HermesSequencePreview';

interface RpgHermesSequenceReviewPanelProps {
  assistMode?: string;
  error?: Error | null;
  isPending?: boolean;
  onAssistModeChange?: (mode: string) => void;
  onReview: () => void;
  onUseFirstItem: (command: string) => void;
  sequence?: HermesSequencePreviewState | null;
}

export function RpgHermesSequenceReviewPanel({
  assistMode = 'review_each_step',
  error,
  isPending = false,
  onAssistModeChange,
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
      <div className="rpg-tabs" aria-label="Hermes assist mode">
        {['off', 'suggest_only', 'review_each_step', 'auto_low_risk', 'manual_override'].map((mode) => (
          <button
            className={assistMode === mode ? 'active' : ''}
            key={mode}
            onClick={() => onAssistModeChange?.(mode)}
            type="button"
          >
            {mode}
          </button>
        ))}
      </div>
      {error ? <p className="rpg-empty-state" role="alert">Hermes sequence review failed: {error.message}</p> : null}
      <HermesSequencePreview sequence={sequence ?? null} onUseFirstItem={onUseFirstItem} />
    </section>
  );
}
