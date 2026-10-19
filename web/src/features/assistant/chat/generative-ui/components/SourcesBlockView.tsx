import type { SourcesBlock } from '../schema';

const SAFE_URL = /^(?:https?:|mailto:)/i;

/** Citation chips for this turn's sources; links follow the chat's link rules. */
export function SourcesBlockView({ block }: { block: SourcesBlock }) {
  return (
    <section className="gui-block gui-sources" aria-label={block.title ?? 'Sources'}>
      <header className="gui-block-header"><h4>{block.title ?? 'Sources'}</h4></header>
      <ul className="gui-source-chips">
        {block.refs.map((ref) => {
          const label = <>{ref.citation ? <span className="gui-source-citation">{ref.citation}</span> : null}<span className="gui-source-title">{ref.title}</span></>;
          return (
            <li key={ref.ref}>
              {ref.url && SAFE_URL.test(ref.url) && !/[\s"'<>]/.test(ref.url)
                ? <a className="gui-source-chip" href={ref.url} target="_blank" rel="noopener noreferrer" title={ref.url}>{label}</a>
                : <span className="gui-source-chip">{label}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
