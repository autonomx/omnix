import { Button } from '@mantine/core';
import type { ChangeEvent, FormEventHandler } from 'react';
import { useState } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { rpgSessionClient } from './api/rpgSessionClient';
import type { RpgQuickActionPreview, RpgSessionSummaryPreview } from './rpgUiTypes';

interface RpgActionComposerProps {
  commandRegistration: UseFormRegisterReturn<'command'>;
  hasCommandError: boolean;
  isPending: boolean;
  /** The campaign being played, when there is one: what Undo rewinds. */
  liveSessionId: string;
  onQuickAction: (command: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  /** A turn the composer ran (an undo) changed the campaign. */
  onTurnApplied: () => void;
  quickActions: RpgQuickActionPreview[];
  selectedSessionId: string;
  sessionRegistration: UseFormRegisterReturn<'sessionId'>;
  sessionSummaries: RpgSessionSummaryPreview[];
}

/** The player's turn: what they type, the scene's suggestions, and undoing the last turn. */
export function RpgActionComposer({
  commandRegistration,
  hasCommandError,
  isPending,
  liveSessionId,
  onQuickAction,
  onSubmit,
  onTurnApplied,
  quickActions,
  selectedSessionId,
  sessionRegistration,
  sessionSummaries,
}: RpgActionComposerProps) {
  const [isUndoing, setIsUndoing] = useState(false);
  const selectedSessionHasOption = !selectedSessionId || sessionSummaries.some((session) => session.id === selectedSessionId);

  const handleSessionSelectChange = (event: ChangeEvent<HTMLSelectElement>) => {
    void sessionRegistration.onChange(event);
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
        <label className="rpg-session-field" title="Session">
          <span className="rpg-field-label">Session</span>
          <select {...sessionRegistration} value={selectedSessionId} onChange={handleSessionSelectChange}>
            <option value="">New or current session</option>
            {!selectedSessionHasOption ? <option value={selectedSessionId}>Launching session — {selectedSessionId}</option> : null}
            {sessionSummaries.map((session) => (
              <option key={session.id} value={session.id}>
                {session.title === session.id ? session.id : `${session.title} — ${session.id}`}
              </option>
            ))}
          </select>
        </label>
        <label className="rpg-command-field">
          <span className="rpg-field-label">Command</span>
          <textarea rows={1} aria-invalid={hasCommandError} placeholder="What do you want to do?" {...commandRegistration} />
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
      </form>
      <div role="group" className="rpg-quick-actions" aria-label="Quick RPG actions">
        {quickActions.map((action) => (
          <button key={`${action.label}:${action.command}`} type="button" onClick={() => onQuickAction(action.command)}>
            <span className="rpg-quick-action-icon" aria-hidden="true">{action.icon}</span>
            <span className="rpg-quick-action-label">{action.label}</span>
          </button>
        ))}
      </div>
    </>
  );
}
