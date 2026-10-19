import type { ChoicesBlock } from '../schema';
import { choiceAction, type ChatUiInteraction } from '../uiActions';

/**
 * Suggested next messages. A button sends exactly the label it shows; only the latest reply's
 * choices are active, and older ones show what was chosen.
 */
export function ChoicesBlockView({ block, messageId, interaction }: { block: ChoicesBlock; messageId: string; interaction?: ChatUiInteraction }) {
  const submitted = interaction?.submissions[block.id];
  const chosen = submitted?.action.action === 'choose' ? submitted.action.option_index ?? -1 : -1;
  const active = Boolean(interaction?.active) && !submitted;
  return (
    <section className="gui-block gui-choices" aria-label={block.prompt ?? 'Suggested replies'}>
      {block.prompt ? <p className="gui-choices-prompt">{block.prompt}</p> : null}
      <div className="gui-choice-list" role="group" aria-label={block.prompt ?? 'Suggested replies'}>
        {block.options.map((option, index) => (
          <button
            type="button"
            key={option.label}
            className="gui-choice"
            data-chosen={index === chosen ? 'true' : undefined}
            aria-pressed={index === chosen}
            disabled={!active}
            title={active ? `Send "${option.label}"` : undefined}
            onClick={() => interaction?.choose(option.label, choiceAction(messageId, block, index))}
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  );
}
