import type { HermesRpgExecutionLedgerItem } from '../../api/hermesRpgApprovedFlowClient';

interface RpgHermesExecutionHistoryProps {
  items?: HermesRpgExecutionLedgerItem[];
  isLoading?: boolean;
}

export function RpgHermesExecutionHistory({ items = [], isLoading = false }: RpgHermesExecutionHistoryProps) {
  return (
    <section className="rpg-card" aria-label="Hermes execution history">
      <div className="rpg-section-heading">
        <p className="eyebrow">Hermes history</p>
        <span>{isLoading ? 'loading' : items.length}</span>
      </div>
      <div className="rpg-list-stack">
        {items.length === 0 ? <p className="rpg-empty-state">No Hermes execution history for this session yet.</p> : null}
        {items.map((item) => (
          <article className="rpg-list-row" key={item.execution_id ?? `${item.sequence_id}:${item.item_id}:${item.command_text}`}>
            <span className="rpg-icon-tile" aria-hidden="true">{item.state_changed ? '✓' : '!'}</span>
            <div>
              <strong>{item.command_text || 'No command text'}</strong>
              <span>{item.result_summary || item.error || item.checkpoint_reason || 'Recorded by Hermes approved flow.'}</span>
            </div>
            <span className="rpg-pill">{item.sequence_id ?? item.approval_source ?? 'approved'}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
