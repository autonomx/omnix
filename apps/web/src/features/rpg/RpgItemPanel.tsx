import type { RpgItemObjectivePreview, RpgItemStatusCard, RpgItemUiAction, RpgMerchantEntryPreview } from './rpgItemUiState';
import './RpgItemPanel.css';

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

const actionIcons: Record<string, string> = {
  inspect: '🔎',
  use: '✨',
  equip: '🛡️',
  drop: '⬇️',
  salvage: '♻️',
  craft: '🛠️',
  modify: '⚙️',
  sell: '🪙',
  buy: '🛒',
  diagnostics: '📋',
  maintenance: '🧰',
  objectives: '🎯',
  scenario: '🧭',
};

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
        hasMerchantContext={hasMerchantEntries}
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
              title={objective.disabled ? 'This objective is not currently available.' : objective.detail}
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
              title={entry.disabled ? 'This merchant entry is not currently available.' : `${entry.action} ${entry.label}: ${entry.detail}`}
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
  hasMerchantContext: boolean;
  isPending: boolean;
  onApplyAction?: (action: RpgItemUiAction) => void;
  onSelectCommand?: (command: string) => void;
}

function ActionList({ actions, emptyLabel, hasMerchantContext, isPending, onApplyAction, onSelectCommand }: ActionListProps) {
  if (!actions.length) {
    return <p className="rpg-item-empty">{emptyLabel}</p>;
  }

  return (
    <div className="rpg-item-actions" aria-label="Selected item actions">
      <div className="rpg-item-action-toolbar" role="toolbar" aria-label="Selected item contextual actions">
        {actions.map((action) => {
          const disabledReason = itemActionDisabledReason(action, { hasMerchantContext, isPending });
          const disabled = Boolean(disabledReason);
          return (
            <button
              aria-label={action.label}
              className={`rpg-item-action-icon-button rpg-item-action-${action.kind}`}
              disabled={disabled}
              key={action.id}
              onClick={() => {
                if (disabled) {
                  return;
                }
                if (onApplyAction) {
                  onApplyAction(action);
                  return;
                }
                onSelectCommand?.(action.command);
              }}
              title={disabledReason ? `${action.label}: ${disabledReason}` : `${action.label}: ${action.detail}`}
              type="button"
            >
              <span aria-hidden="true">{actionIcons[action.kind] ?? '•'}</span>
            </button>
          );
        })}
      </div>
      <ul className="rpg-item-action-context-list" aria-label="Item action context requirements">
        {actions.map((action) => {
          const disabledReason = itemActionDisabledReason(action, { hasMerchantContext, isPending });
          return (
            <li key={`${action.id}:context`} className={disabledReason ? 'rpg-item-action-context-disabled' : undefined}>
              <strong>{action.label}</strong>
              <span>{disabledReason ?? action.detail}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function itemActionDisabledReason(action: RpgItemUiAction, context: { hasMerchantContext: boolean; isPending: boolean }): string | null {
  if (context.isPending) {
    return 'Item action is already running.';
  }
  if (action.disabled) {
    return 'Select a live session before applying item actions.';
  }
  if (action.kind === 'sell' && !context.hasMerchantContext) {
    return 'Start a merchant conversation or open a merchant service before selling.';
  }
  return null;
}
