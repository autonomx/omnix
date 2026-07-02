export type HermesSequencePreviewItem = {
  item_id?: string;
  statement?: string;
  expected_effect?: string;
  guards?: string[];
  user_gate?: boolean;
  status?: string;
};

export type HermesSequencePreviewState = {
  sequence_id?: string;
  objective?: string;
  domain?: string;
  state_owner?: string;
  risk?: string;
  user_gate?: boolean;
  status?: string;
  items?: HermesSequencePreviewItem[];
};

interface HermesSequencePreviewProps {
  sequence?: HermesSequencePreviewState | null;
  onApprove?: () => void;
  onReject?: () => void;
  onUseFirstItem?: (statement: string) => void;
}

export function HermesSequencePreview({ sequence, onApprove, onReject, onUseFirstItem }: HermesSequencePreviewProps) {
  const items = sequence?.items ?? [];
  const firstStatement = items.find((item) => item.statement?.trim())?.statement?.trim() ?? '';
  if (!sequence) {
    return <p className="rpg-empty-state">No Hermes sequence is ready for review.</p>;
  }

  return (
    <section className="rpg-card" aria-label="Hermes sequence preview">
      <div className="rpg-section-heading">
        <p className="eyebrow">Hermes sequence</p>
        <span>{sequence.status ?? 'draft'}</span>
      </div>
      <h3>{sequence.objective || 'Untitled objective'}</h3>
      <div className="rpg-resource-grid">
        <div>
          <span>Risk</span>
          <strong>{sequence.risk ?? 'medium'}</strong>
        </div>
        <div>
          <span>Owner</span>
          <strong>{sequence.state_owner ?? 'rpg_sim'}</strong>
        </div>
        <div>
          <span>Domain</span>
          <strong>{sequence.domain ?? 'rpg'}</strong>
        </div>
        <div>
          <span>Items</span>
          <strong>{items.length}</strong>
        </div>
      </div>
      <div className="rpg-list-stack">
        {items.map((item, index) => (
          <article className="rpg-list-row" key={item.item_id ?? `${index}-${item.statement ?? 'item'}`}>
            <span className="rpg-icon-tile" aria-hidden="true">{index + 1}</span>
            <div>
              <strong>{item.statement || 'No statement supplied'}</strong>
              <span>{item.expected_effect || 'Expected effect not provided.'}</span>
            </div>
            <span className="rpg-pill">{item.user_gate === false ? 'auto-safe' : 'review'}</span>
          </article>
        ))}
      </div>
      <div className="rpg-survival-actions" aria-label="Hermes sequence actions">
        <button className="rpg-secondary-button" disabled={!firstStatement || !onUseFirstItem} onClick={() => firstStatement && onUseFirstItem?.(firstStatement)} type="button">
          Use first item
        </button>
        <button className="rpg-secondary-button" disabled={!onApprove} onClick={() => onApprove?.()} type="button">
          Approve sequence
        </button>
        <button className="rpg-secondary-button" disabled={!onReject} onClick={() => onReject?.()} type="button">
          Reject
        </button>
      </div>
      <small>Preview only. The RPG simulation still owns state changes.</small>
    </section>
  );
}
