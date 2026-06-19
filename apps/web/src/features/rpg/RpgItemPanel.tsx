import type { RpgItemObjectivePreview, RpgItemStatusCard, RpgItemUiAction, RpgMerchantEntryPreview } from './rpgItemUiState';

interface RpgItemPanelProps {
  actions: RpgItemUiAction[];
  objectives?: RpgItemObjectivePreview[];
  statusCards?: RpgItemStatusCard[];
  merchantEntries?: RpgMerchantEntryPreview[];
  isPending?: boolean;
  onApplyAction?: (action: RpgItemUiAction) => void;
  onApplyObjective?: (objective: RpgItemObjectivePreview) => void;
  onApplyMerchantEntry?: (entry: RpgMerchantEntryPreview) => void;
  onSelectCommand?: (command: string) => void;
}

export function RpgItemPanel({
  actions,
  objectives = [],
  statusCards = [],
  merchantEntries = [],
  isPending = false,
  onApplyAction,
  onApplyObjective,
  onApplyMerchantEntry,
  onSelectCommand,
}: RpgItemPanelProps) {
  const hasActions = actions.length > 0;
  const hasObjectives = objectives.length > 0;
  const hasStatus = statusCards.length > 0;
  const hasMerchantEntries = merchantEntries.length > 0;

  return (
    <section className="rpg-item-panel" aria-label="Item actions and coverage">
      <header className="rpg-item-panel-header">
        <div>
          <p className="eyebrow">Item systems</p>
          <h3>Inventory, crafting, and trade</h3>
        </div>
        <span>{hasActions ? `${actions.length} action${actions.length === 1 ? '' : 's'}` : 'No item selected'}</span>
      </header>

      {hasStatus ? (
        <div className="rpg-item-status-grid" aria-label="Item status cards">
          {statusCards.map((card) => (
            <article className={`rpg-item-status-card rpg-item-status-${card.tone}`} key={card.id}>
              <small>{card.label}</small>
              <strong>{card.value}</strong>
              <p>{card.detail}</p>
            </article>
          ))}
        </div>
      ) : null}

      <ActionList
        actions={actions}
        emptyLabel="Select an inventory item to reveal deterministic actions."
        isPending={isPending}
        onApplyAction={onApplyAction}
        onSelectCommand={onSelectCommand}
      />

      {hasObjectives ? (
        <div className="rpg-item-objectives" aria-label="Item objectives">
          <h4>Suggested next item steps</h4>
          {objectives.map((objective) => (
            <button
              aria-label={objective.label}
              className="rpg-item-action-row"
              disabled={isPending || objective.disabled}
              key={objective.id}
              onClick={() => onApplyObjective?.(objective)}
              type="button"
            >
              <span>
                <strong>{objective.label}</strong>
                <small>{objective.detail}</small>
              </span>
              <code>{objective.action}</code>
            </button>
          ))}
        </div>
      ) : null}

      {hasMerchantEntries ? (
        <div className="rpg-item-merchant" aria-label="Merchant entries">
          <h4>Merchant service</h4>
          {merchantEntries.map((entry) => (
            <button
              aria-label={`${entry.action} ${entry.label}`}
              className="rpg-item-action-row"
              disabled={isPending || entry.disabled}
              key={entry.id}
              onClick={() => onApplyMerchantEntry?.(entry)}
              type="button"
            >
              <span>
                <strong>{entry.label}</strong>
                <small>{entry.detail}</small>
              </span>
              <code>{entry.priceLabel}</code>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

interface ActionListProps {
  actions: RpgItemUiAction[];
  emptyLabel: string;
  isPending: boolean;
  onApplyAction?: (action: RpgItemUiAction) => void;
  onSelectCommand?: (command: string) => void;
}

function ActionList({ actions, emptyLabel, isPending, onApplyAction, onSelectCommand }: ActionListProps) {
  if (!actions.length) {
    return <p className="rpg-item-empty">{emptyLabel}</p>;
  }

  return (
    <div className="rpg-item-actions" aria-label="Selected item actions">
      {actions.map((action) => (
        <button
          aria-label={action.label}
          className="rpg-item-action-row"
          disabled={isPending || action.disabled}
          key={action.id}
          onClick={() => {
            if (onApplyAction) {
              onApplyAction(action);
              return;
            }
            onSelectCommand?.(action.command);
          }}
          type="button"
        >
          <span>
            <strong>{action.label}</strong>
            <small>{action.detail}</small>
          </span>
          <code>{action.mode}</code>
        </button>
      ))}
    </div>
  );
}
