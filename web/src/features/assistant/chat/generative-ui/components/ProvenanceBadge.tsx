import type { ChatUiBlock } from '../schema';

const SAFE_URL = /^(?:https?:|mailto:)/i;

/**
 * Where a block's numbers came from (GUI-4.3): values bound to this turn's sources show a
 * "Sourced" disclosure naming them; numbers the model wrote show "AI-generated values".
 */
export function ProvenanceBadge({ block }: { block: ChatUiBlock }) {
  const sources = [...new Map(block.bindings.map((binding) => [binding.ref, binding])).values()];
  const modelNumbers = block.provenance === 'model' && (block.type === 'stats' || block.type === 'chart');
  if (!sources.length && !modelNumbers) return null;
  return (
    <span className="gui-provenance">
      {modelNumbers ? (
        <span className="gui-provenance-model" title="The AI model wrote these values; they are not from a source.">AI-generated values</span>
      ) : null}
      {sources.length ? (
        <details className="gui-provenance-sourced">
          <summary aria-label={`Sourced from ${sources.length} source${sources.length === 1 ? '' : 's'}`}>Sourced</summary>
          <ul>
            {sources.map((source) => (
              <li key={source.ref}>
                {source.url && SAFE_URL.test(source.url)
                  ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
                  : source.title}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </span>
  );
}
