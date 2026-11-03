import type { RpgInventoryItemPreview } from './rpgUiTypes';
import type { RpgItemDetailPreview, RpgItemUiAction } from './rpgItemUiState';
import { buildItemDetailPreview } from './rpgItemUiState';
import './RpgItemPanel.css';

interface RpgItemPanelProps {
  actions: RpgItemUiAction[];
  isPending?: boolean;
  item?: RpgInventoryItemPreview;
  onApplyAction?: (action: RpgItemUiAction) => void;
}

const actionIcons: Record<string, string> = {
  use: '✨',
  equip: '🛡️',
  unequip: '🎒',
  drop: '⬇️',
  sell: '🪙',
};

/** The selected item: what the world says of it, and what the hero can do with it. */
export function RpgItemPanel({ actions, isPending = false, item, onApplyAction }: RpgItemPanelProps) {
  const detail = buildItemDetailPreview(item);

  return (
    <section className="rpg-item-panel" aria-label="Selected item">
      {detail ? <ItemDetailCard detail={detail} /> : null}

      {actions.length ? (
        <div role="group" className="rpg-item-actions" aria-label="Selected item actions">
          <div className="rpg-item-action-toolbar" role="toolbar" aria-label="Selected item contextual actions">
            {actions.map((action) => {
              const disabledReason = isPending
                ? 'Another action is on its way.'
                : action.disabled
                  ? 'Start or load a campaign first.'
                  : null;
              return (
                <button
                  aria-label={action.label}
                  className={`rpg-item-action-icon-button rpg-item-action-${action.kind}`}
                  disabled={Boolean(disabledReason)}
                  key={action.id}
                  onClick={() => onApplyAction?.(action)}
                  title={`${action.label}: ${disabledReason ?? action.detail}`}
                  type="button"
                >
                  <span aria-hidden="true">{actionIcons[action.kind] ?? '•'}</span>
                  <span aria-hidden="true">{action.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="rpg-item-empty">Select something you carry.</p>
      )}
    </section>
  );
}

function ItemDetailCard({ detail }: { detail: RpgItemDetailPreview }) {
  return (
    <article className="rpg-item-detail-card" aria-label={`Selected item details: ${detail.itemName}`}>
      <header>
        <span className="rpg-item-detail-icon" aria-hidden="true">{detail.icon}</span>
        <div>
          {detail.category ? <p className="eyebrow">{detail.category}</p> : null}
          <h4>{detail.itemName}</h4>
        </div>
        <small>{detail.countLabel}</small>
      </header>
      <p>{detail.summary}</p>
      <dl>
        <div>
          <dt>Status</dt>
          <dd>{detail.status}</dd>
        </div>
      </dl>
    </article>
  );
}
