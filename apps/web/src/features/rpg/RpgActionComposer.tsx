import { Button } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import type { FormEventHandler } from 'react';
import { useState } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { RpgQuickActionPreview, RpgSessionSummaryPreview } from './rpgUiState';
import './RpgSessionLauncher.css';

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
  const queryClient = useQueryClient();
  const [launchStatus, setLaunchStatus] = useState<string>();
  const [launchError, setLaunchError] = useState<string>();
  const [isLaunching, setIsLaunching] = useState(false);

  const refreshRpgWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'replay-inventory'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'reports'] }),
    ]);
  };

  const launchSession = async (kind: 'new_game' | 'demo') => {
    setIsLaunching(true);
    setLaunchError(undefined);
    setLaunchStatus(kind === 'new_game' ? 'Creating new Level 1 campaign…' : 'Cloning demo session…');
    try {
      const response =
        kind === 'new_game'
          ? await omnixApiClient.createRpgNewGame({
              campaign_template: 'classic_fantasy',
              starting_location: 'rusty_flagon_tavern',
              player: { name: 'Alyndra', pronouns: 'she/her', background: 'Wanderer', build: 'balanced_adventurer' },
              difficulty: 'normal',
              world_activity: 'standard',
              companions_enabled: true,
              permadeath: false,
              features: {
                autosave: true,
                validator: true,
                background_soft_audit: true,
                llm_narration: true,
                image_generation: false,
                tts: false,
                stt: false,
              },
            })
          : await omnixApiClient.startRpgPreset('demo_glimmerdeep_pass_lvl14');

      if (!response.ok) {
        throw new Error(response.error ?? 'RPG session launch failed.');
      }

      await refreshRpgWorkspace();
      setLaunchStatus(`Session ready: ${response.session_id ?? 'created'}. Workspace refreshed.`);
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : 'RPG session launch failed.');
    } finally {
      setIsLaunching(false);
    }
  };

  return (
    <>
      <section className="rpg-session-launcher" aria-label="RPG session launcher">
        <div>
          <p className="eyebrow">Campaign launcher</p>
          <h3>Start or resume an RPG session</h3>
          <p>New Game creates a fresh Level 1 campaign. Demo Session clones the polished Glimmerdeep Pass showcase save.</p>
        </div>
        <div className="rpg-session-launcher-actions">
          <Button variant="light" type="button" disabled={isLaunching || isPending} loading={isLaunching && launchStatus?.includes('Level 1')} onClick={() => void launchSession('new_game')}>
            New Game
          </Button>
          <Button variant="light" type="button" disabled={isLaunching || isPending} loading={isLaunching && launchStatus?.includes('demo')} onClick={() => void launchSession('demo')}>
            Demo Session
          </Button>
        </div>
        {launchStatus ? <p className="rpg-session-launcher-status">{launchStatus}</p> : null}
        {launchError ? <p className="rpg-session-launcher-error">{launchError}</p> : null}
      </section>

      <form className="rpg-action-composer" aria-labelledby="rpg-turn-request-title" onSubmit={onSubmit}>
        <div className="rpg-action-composer-heading">
          <h3 id="rpg-turn-request-title">Turn request</h3>
          <p>Queue replay-preserving RPG commands into the deterministic turn pipeline.</p>
        </div>
        <label className="rpg-session-field" title="Session">
          <span className="rpg-field-label">Session</span>
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
          <span className="rpg-field-label">Command</span>
          <textarea rows={1} aria-invalid={hasCommandError} placeholder="What do you want to do?" {...commandRegistration} />
        </label>
        <Button
          aria-label={isPending ? 'Queueing RPG turn' : 'Queue RPG turn'}
          className="rpg-submit-button"
          type="submit"
          disabled={isPending || isLaunching}
          loading={isPending}
        >
          {isPending ? 'Queueing...' : 'Submit'}
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
