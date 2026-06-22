import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchRpgItemDetails } from './rpgItemApi';
import type { RpgItemDetailPreview, RpgItemObjectivePreview, RpgItemStatusCard, RpgItemUiAction, RpgMerchantEntryPreview } from './rpgItemUiState';
import { buildItemDetailPreview } from './rpgItemUiState';
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
  const selectedItem = actions.find((action) => action.item)?.item;
  const selectedItemSessionId = selectedItem?.sessionId ?? null;
  const itemDetailQuery = useQuery({
    enabled: Boolean(selectedItemSessionId && selectedItem?.label),
    queryKey: ['feature', 'rpg', 'item-detail', selectedItemSessionId, selectedItem?.label, selectedItem?.count],
    queryFn: () => fetchRpgItemDetails(selectedItemSessionId ?? '', { itemName: selectedItem?.label ?? '', itemCount: selectedItem?.count, source: 'rpg-item-panel' }),
    retry: false,
    staleTime: 30_000,
  });
  const itemDetail = useMemo(() => buildItemDetailPreview(itemDetailQuery.data, selectedItem), [itemDetailQuery.data, selectedItem]);
  const displayedItemDetail = itemDetail
    ? {
        ...itemDetail,
        source: itemDetailQuery.isError && itemDetail.source === 'pending' ? 'unavailable' : itemDetail.source,
        summary:
          itemDetailQuery.isError && itemDetail.source === 'pending'
            ? 'LLM item details are unavailable right now; the action icons still execute deterministic item actions.'
            : itemDetail.summary,
      }
    : undefined;

  return (
    <section className="rpg-item-panel" aria-label="Item actions and coverage">
      <header className="rpg-item-panel-header">
        <div>
          <p className="eyebrow">Item systems</p>
          <h3>Inventory, crafting, and trade</h3>
        </div>
        <span>{hasActions ? `${actions.length} action${actions.length === 1 ? '' : 's'}` : 'No item selected'}</span>
      </header>

      {displayedItemDetail ? <ItemDetailCard detail={displayedItemDetail} isPending={itemDetailQuery.isFetching} /> : null}

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

function ItemDetailCard({ detail, isPending }: { detail: RpgItemDetailPreview; isPending: boolean }) {
  const sourceLabel =
    detail.source === 'llm'
      ? 'LLM item details'
      : detail.source === 'unavailable'
        ? 'Item details unavailable'
        : detail.source === 'pending' || isPending
          ? 'Generating item details'
          : 'Preview item details';

  return (
    <article className={`rpg-item-detail-card rpg-item-detail-${detail.source}`} aria-label={`Selected item details: ${detail.itemName}`}>
      <header>
        <span className="rpg-item-detail-icon" aria-hidden="true">{detail.icon}</span>
        <div>
          <p className="eyebrow">{sourceLabel}</p>
          <h4>{detail.itemName}</h4>
        </div>
        <small>{detail.countLabel}</small>
      </header>
      <p>{isPending && detail.source === 'pending' ? 'Generating LLM item details for the selected inventory item…' : detail.summary}</p>
      <dl>
        <div>
          <dt>Use</dt>
          <dd>{detail.usage}</dd>
        </div>
        <div>
          <dt>Trade</dt>
          <dd>{detail.trade}</dd>
        </div>
        <div>
          <dt>Risk</dt>
          <dd>{detail.risk}</dd>
        </div>
      </dl>
      {detail.tags.length ? (
        <div className="rpg-item-detail-tags" aria-label="Item detail tags">
          {detail.tags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      ) : null}
    </article>
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
