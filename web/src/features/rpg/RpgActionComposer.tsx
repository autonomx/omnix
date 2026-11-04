import { Button } from '@mantine/core';
import type { FormEventHandler, KeyboardEvent } from 'react';
import { useState } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { rpgSessionClient } from './api/rpgSessionClient';
import type { RpgQuickActionPreview } from './rpgUiTypes';
import './RpgActionComposer.css';

interface RpgActionComposerProps {
  commandRegistration: UseFormRegisterReturn<'command'>;
  hasCommandError: boolean;
  isPending: boolean;
  /** The campaign being played, when there is one: what Undo rewinds. */
  liveSessionId: string;
  /** Opens the talk with the game master, which changes nothing in the story. */
  onAskGameMaster?: () => void;
  /** A card plays at once (EV-9); an action without one fills the command to send. */
  onQuickAction: (action: RpgQuickActionPreview) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  /** A turn the composer ran (an undo) changed the campaign. */
  onTurnApplied: () => void;
  quickActions: RpgQuickActionPreview[];
  selectedSessionId: string;
  sessionRegistration: UseFormRegisterReturn<'sessionId'>;
}

/** The player's turn: what they type, the scene's suggestions, and undoing the last turn. */
export function RpgActionComposer({
  commandRegistration,
  hasCommandError,
  isPending,
  liveSessionId,
  onAskGameMaster,
  onQuickAction,
  onSubmit,
  onTurnApplied,
  quickActions,
  selectedSessionId,
  sessionRegistration,
}: RpgActionComposerProps) {
  const [isUndoing, setIsUndoing] = useState(false);

  // Enter sends the turn; Shift+Enter starts a new line (RQ-7.6: play from the keyboard).
  const sendOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  };

  const undoLastTurn = async () => {
    if (!liveSessionId) return;
    setIsUndoing(true);
    try {
      await rpgSessionClient.rewindRpgSession(liveSessionId);
      onTurnApplied();
    } catch {
      // A refused undo (nothing to undo, a hardcore campaign) is told in the story log, like any turn.
    } finally {
      setIsUndoing(false);
    }
  };

  return (
    <>
      <form className="rpg-action-composer" aria-labelledby="rpg-turn-request-title" onSubmit={onSubmit}>
        <div className="rpg-action-composer-heading">
          <h3 id="rpg-turn-request-title">Your turn</h3>
        </div>
        <input type="hidden" {...sessionRegistration} value={selectedSessionId} />
        <label className="rpg-command-field">
          <span className="rpg-field-label">Command</span>
          <textarea rows={1} aria-invalid={hasCommandError} onKeyDown={sendOnEnter} placeholder="What do you want to do?" {...commandRegistration} />
        </label>
        <Button
          aria-label={isPending ? 'Sending your turn' : 'Submit RPG turn'}
          className="rpg-submit-button"
          type="submit"
          disabled={isPending || isUndoing}
          loading={isPending}
        >
          {isPending ? 'Sending…' : 'Submit'}
        </Button>
        <button
          aria-label="Undo last turn"
          className="rpg-undo-button"
          disabled={!liveSessionId || isPending || isUndoing}
          onClick={() => void undoLastTurn()}
          title="Undo last turn"
          type="button"
        >
          <span aria-hidden="true">↶</span>
        </button>
        {onAskGameMaster ? (
          <button
            aria-label="Ask the game master"
            className="rpg-undo-button rpg-ask-button"
            onClick={onAskGameMaster}
            title="Ask the game master: a question changes nothing in the story"
            type="button"
          >
            <span aria-hidden="true">?</span>
          </button>
        ) : null}
      </form>
      <div role="group" className="rpg-quick-actions" aria-label="Quick RPG actions">
        {quickActions.map((action) => (
          <button key={`${action.label}:${action.command}`} title={action.label} type="button" onClick={() => onQuickAction(action)}>
            <span className="rpg-quick-action-icon" aria-hidden="true">{action.icon}</span>
            <span className="rpg-quick-action-label">{action.label}</span>
          </button>
        ))}
      </div>
    </>
  );
}
