import { Button } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import type { ChangeEvent, FormEventHandler } from 'react';
import { useState } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { omnixApiClient, type RpgLaunchResponse } from '../../api/client';
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

function safeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function launchedSessionId(response: RpgLaunchResponse): string | undefined {
  if (response.session_id) {
    return response.session_id;
  }

  const game = safeRecord(response.game);
  if (typeof game.session_id === 'string') {
    return game.session_id;
  }

  const session = safeRecord(response.session);
  const manifest = safeRecord(session.manifest);
  if (typeof manifest.session_id === 'string') {
    return manifest.session_id;
  }
  if (typeof manifest.id === 'string') {
    return manifest.id;
  }

  return undefined;
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
  const [selectedSessionId, setSelectedSessionId] = useState('');

  const refreshRpgWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'replay-inventory'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'reports'] }),
    ]);
  };

  const applySelectedSessionId = (sessionId: string) => {
    setSelectedSessionId(sessionId);
    void sessionRegistration.onChange({
      target: { name: sessionRegistration.name, value: sessionId },
      type: 'change',
    });
  };

  const handleSessionSelectChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setSelectedSessionId(event.currentTarget.value);
    void sessionRegistration.onChange(event);
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

      const sessionId = launchedSessionId(response);
      if (sessionId) {
        applySelectedSessionId(sessionId);
      }

      await refreshRpgWorkspace();
      setLaunchStatus(
        sessionId
          ? `Session ready and selected: ${sessionId}. The next command will use this session.`
          : 'Session ready. Workspace refreshed, but no session id was returned.',
      );
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : 'RPG session launch failed.');
    } finally {
      setIsLaunching(false);
    }
  };

  const selectedSessionHasOption = !selectedSessionId || sessionSummaries.some((session) => session.id === selectedSessionId);

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
        {launchStatus ? <p className="rpg-session-launcher-status" aria-live="polite">{launchStatus}</p> : null}
        {launchError ? <p className="rpg-session-launcher-error" aria-live="assertive">{launchError}</p> : null}
      </section>

      <form className="rpg-action-composer" aria-labelledby="rpg-turn-request-title" onSubmit={onSubmit}>
        <div className="rpg-action-composer-heading">
          <h3 id="rpg-turn-request-title">Turn request</h3>
          <p>Queue replay-preserving RPG commands into the deterministic turn pipeline.</p>
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
