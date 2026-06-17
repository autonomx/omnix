export type RpgLiveDataStatusState = 'loading' | 'refreshing' | 'empty' | 'error' | 'ready';

export interface RpgLiveDataStatusCard {
  id: string;
  label: string;
  state: RpgLiveDataStatusState;
  detail: string;
}

const statusLabels: Record<RpgLiveDataStatusState, string> = {
  loading: 'Loading',
  refreshing: 'Refreshing',
  empty: 'Empty',
  error: 'Error',
  ready: 'Ready',
};

function summarize(cards: RpgLiveDataStatusCard[]) {
  const errorCount = cards.filter((card) => card.state === 'error').length;
  const loadingCount = cards.filter((card) => card.state === 'loading' || card.state === 'refreshing').length;
  const emptyCount = cards.filter((card) => card.state === 'empty').length;

  if (errorCount) {
    return `${errorCount} source${errorCount === 1 ? '' : 's'} need attention`;
  }

  if (loadingCount) {
    return `${loadingCount} source${loadingCount === 1 ? '' : 's'} updating`;
  }

  if (emptyCount) {
    return `${emptyCount} source${emptyCount === 1 ? '' : 's'} empty`;
  }

  return 'All live sources ready';
}

export function RpgLiveDataStatus({ cards }: { cards: RpgLiveDataStatusCard[] }) {
  return (
    <section className="rpg-card rpg-live-data-status" aria-label="RPG live data status">
      <div className="rpg-section-heading">
        <p className="eyebrow">Live data status</p>
        <span>{summarize(cards)}</span>
      </div>
      <div className="rpg-data-status-grid">
        {cards.map((card) => (
          <article
            aria-label={`${card.label} status`}
            className={`rpg-data-status-card rpg-data-status-${card.state}`}
            key={card.id}
          >
            <div>
              <strong>{card.label}</strong>
              <span>{statusLabels[card.state]}</span>
            </div>
            <p>{card.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
