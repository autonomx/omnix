import { Button } from '@mantine/core';
import type { FormEventHandler } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import type { RpgQuickActionPreview, RpgSessionSummaryPreview } from './rpgUiState';

interface RpgActionComposerProps {
  commandRegistration: UseFormRegisterReturn<'command'>;
  hasCommandError: boolean;
  isPending: boolean;
  onQuickAction: (command: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  quickActions: RpgQuickActionPreview[];
  sessionRegistration: UseFormRegisterReturn<'sessionId'>;
  sessionSummaries: RpgSessionSummaryPreview[];
}

export function RpgActionComposer({
  commandRegistration,
  hasCommandError,
  isPending,
  onQuickAction,
  onSubmit,
  quickActions,
  sessionRegistration,
  sessionSummaries,
}: RpgActionComposerProps) {
  return (
    <>
      <form className="rpg-action-composer" onSubmit={onSubmit}>
        <div className="rpg-action-composer-heading">
          <h3>Turn request</h3>
          <p>Queue replay-preserving RPG commands into the deterministic turn pipeline.</p>
        </div>
        <label>
          <span>Session</span>
          <select {...sessionRegistration}>
            <option value="">New or current session</option>
            {sessionSummaries.map((session) => (
              <option key={session.id} value={session.id}>
                {session.title === session.id ? session.id : `${session.title} — ${session.id}`}
              </option>
            ))}
          </select>
        </label>
        <label className="rpg-command-field">
          <span>Command</span>
          <textarea rows={3} aria-invalid={hasCommandError} placeholder="What do you want to do?" {...commandRegistration} />
        </label>
        <Button className="rpg-submit-button" type="submit" disabled={isPending} loading={isPending}>
          {isPending ? 'Queueing…' : 'Queue RPG turn'}
        </Button>
      </form>
      <div className="rpg-quick-actions" aria-label="Quick RPG actions">
        {quickActions.map((action) => (
          <button key={action.label} type="button" onClick={() => onQuickAction(action.command)}>
            <span aria-hidden="true">{action.icon}</span>
            {action.label}
          </button>
        ))}
      </div>
    </>
  );
}
