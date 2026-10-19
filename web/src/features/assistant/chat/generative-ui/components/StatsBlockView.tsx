import type { StatsBlock } from '../schema';
import { ProvenanceBadge } from './ProvenanceBadge';

const TREND_MARK = { up: '▲', down: '▼', flat: '▬' } as const;
const TREND_WORD = { up: 'up', down: 'down', flat: 'unchanged' } as const;

/** 1-6 headline numbers as tiles. */
export function StatsBlockView({ block }: { block: StatsBlock }) {
  return (
    <section className="gui-block gui-stats" aria-label={block.title ?? 'Headline figures'}>
      {block.title || block.bindings.length || block.provenance === 'model' ? (
        <header className="gui-block-header">
          {block.title ? <h4>{block.title}</h4> : null}
          <ProvenanceBadge block={block} />
        </header>
      ) : null}
      <dl className="gui-stats-grid">
        {block.items.map((item, index) => {
          const tone = item.tone ?? (item.trend === 'up' ? 'positive' : item.trend === 'down' ? 'negative' : 'neutral');
          return (
            <div className="gui-stat" data-tone={tone} key={`${index}:${item.label}`}>
              <dt>{item.label}</dt>
              <dd className="gui-stat-value">{item.value}</dd>
              {item.delta ? (
                <dd className="gui-stat-delta">
                  {item.trend ? <span aria-hidden="true">{TREND_MARK[item.trend]} </span> : null}
                  {item.trend ? <span className="gui-visually-hidden">{TREND_WORD[item.trend]} </span> : null}
                  {item.delta}
                </dd>
              ) : null}
              {item.hint ? <dd className="gui-stat-hint">{item.hint}</dd> : null}
            </div>
          );
        })}
      </dl>
    </section>
  );
}
