import { Button } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import type { ChangeEvent, FormEventHandler } from 'react';
import { useMemo, useState } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { omnixApiClient, type RpgLaunchResponse, type RpgNewGameRequest } from '../../api/client';
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

type LauncherView = 'home' | 'new_game' | 'load_game';
type RpgPlayerBuild = 'balanced_adventurer' | 'warrior' | 'ranger' | 'silver_tongue';
type RpgDifficulty = 'story' | 'normal' | 'harsh';
type RpgWorldActivity = 'quiet' | 'standard' | 'living_world';

const BUILD_OPTIONS: { value: RpgPlayerBuild; label: string; detail: string }[] = [
  { value: 'balanced_adventurer', label: 'Balanced Adventurer', detail: 'Even stats and flexible starter gear.' },
  { value: 'warrior', label: 'Warrior', detail: 'High strength and constitution.' },
  { value: 'ranger', label: 'Ranger', detail: 'High dexterity and wilderness awareness.' },
  { value: 'silver_tongue', label: 'Silver Tongue', detail: 'High charisma for social routes.' },
];

const STARTING_LOCATIONS = [
  { value: 'rusty_flagon_tavern', label: 'Rusty Flagon Tavern' },
  { value: 'market_district', label: 'Market District' },
  { value: 'northern_road', label: 'Northern Road' },
  { value: 'glimmerdeep_pass', label: 'Glimmerdeep Pass' },
  { value: 'old_quarry', label: 'Old Quarry' },
];

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

function parseSeed(seed: string): number | null {
  const trimmed = seed.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) ? parsed : null;
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
  const [launcherView, setLauncherView] = useState<LauncherView>('home');
  const [playerName, setPlayerName] = useState('Alyndra');
  const [playerPronouns, setPlayerPronouns] = useState('she/her');
  const [playerBackground, setPlayerBackground] = useState('Wanderer');
  const [playerBuild, setPlayerBuild] = useState<RpgPlayerBuild>('balanced_adventurer');
  const [startingLocation, setStartingLocation] = useState('rusty_flagon_tavern');
  const [difficulty, setDifficulty] = useState<RpgDifficulty>('normal');
  const [worldActivity, setWorldActivity] = useState<RpgWorldActivity>('standard');
  const [seed, setSeed] = useState('');
  const [companionsEnabled, setCompanionsEnabled] = useState(true);
  const [validatorEnabled, setValidatorEnabled] = useState(true);
  const [backgroundSoftAuditEnabled, setBackgroundSoftAuditEnabled] = useState(true);
  const [llmNarrationEnabled, setLlmNarrationEnabled] = useState(true);

  const liveSessionSummaries = useMemo(
    () => sessionSummaries.filter((session) => session.source === 'live').sort((a, b) => b.sortRank - a.sortRank),
    [sessionSummaries],
  );
  const mostRecentLiveSession = liveSessionSummaries[0];

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

  const finishLaunch = async (response: RpgLaunchResponse, fallbackSessionId: string | undefined, readyLabel: string) => {
    if (!response.ok) {
      throw new Error(response.error ?? 'RPG session launch failed.');
    }

    const sessionId = launchedSessionId(response) ?? fallbackSessionId;
    if (sessionId) {
      applySelectedSessionId(sessionId);
    }

    await refreshRpgWorkspace();
    setLauncherView('home');
    setLaunchStatus(
      sessionId
        ? `${readyLabel}: ${sessionId}. The next command will use this session.`
        : `${readyLabel}. Workspace refreshed, but no session id was returned.`,
    );
  };

  const buildNewGameRequest = (): RpgNewGameRequest => ({
    campaign_template: 'classic_fantasy',
    starting_location: startingLocation,
    player: {
      name: playerName.trim() || 'Alyndra',
      pronouns: playerPronouns.trim() || 'they/them',
      background: playerBackground.trim() || 'Wanderer',
      build: playerBuild,
    },
    difficulty,
    world_activity: worldActivity,
    companions_enabled: companionsEnabled,
    permadeath: false,
    seed: parseSeed(seed),
    features: {
      autosave: true,
      validator: validatorEnabled,
      background_soft_audit: backgroundSoftAuditEnabled,
      llm_narration: llmNarrationEnabled,
      image_generation: false,
      tts: false,
      stt: false,
    },
  });

  const launchNewGame = async () => {
    setIsLaunching(true);
    setLaunchError(undefined);
    setLaunchStatus('Creating configured Level 1 campaign…');
    try {
      const response = await omnixApiClient.createRpgNewGame(buildNewGameRequest());
      await finishLaunch(response, undefined, 'New Game ready and selected');
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : 'RPG new game launch failed.');
    } finally {
      setIsLaunching(false);
    }
  };

  const launchDemoSession = async () => {
    setIsLaunching(true);
    setLaunchError(undefined);
    setLaunchStatus('Cloning demo session…');
    try {
      const response = await omnixApiClient.startRpgPreset('demo_glimmerdeep_pass_lvl14');
      await finishLaunch(response, undefined, 'Demo Session ready and selected');
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : 'RPG demo session launch failed.');
    } finally {
      setIsLaunching(false);
    }
  };

  const continueSession = async (sessionId: string) => {
    setIsLaunching(true);
    setLaunchError(undefined);
    setLaunchStatus(`Loading session ${sessionId}…`);
    try {
      const response = await omnixApiClient.continueRpgSession(sessionId);
      await finishLaunch(response, sessionId, 'Session loaded and selected');
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : 'RPG session load failed.');
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
          <h3>Start, resume, or demo an RPG session</h3>
          <p>Continue a saved run, configure a fresh Level 1 campaign, or clone the polished Glimmerdeep Pass showcase.</p>
        </div>
        <div className="rpg-session-launcher-actions">
          <Button
            variant="light"
            type="button"
            disabled={isLaunching || isPending || !mostRecentLiveSession}
            loading={isLaunching && launchStatus?.startsWith('Loading session')}
            onClick={() => mostRecentLiveSession && void continueSession(mostRecentLiveSession.id)}
          >
            Continue
          </Button>
          <Button variant="light" type="button" disabled={isLaunching || isPending} onClick={() => setLauncherView('new_game')}>
            New Game
          </Button>
          <Button variant="light" type="button" disabled={isLaunching || isPending} loading={isLaunching && launchStatus?.includes('demo')} onClick={() => void launchDemoSession()}>
            Demo Session
          </Button>
          <Button variant="light" type="button" disabled={isLaunching || isPending || !liveSessionSummaries.length} onClick={() => setLauncherView('load_game')}>
            Load Game
          </Button>
        </div>

        {launcherView === 'new_game' ? (
          <div className="rpg-launcher-panel" aria-label="New Game setup">
            <div className="rpg-launcher-panel-heading">
              <div>
                <p className="eyebrow">New Game setup</p>
                <h4>Fresh deterministic campaign</h4>
              </div>
              <Button variant="subtle" type="button" disabled={isLaunching} onClick={() => setLauncherView('home')}>
                Close
              </Button>
            </div>

            <div className="rpg-launcher-form-grid">
              <label>
                <span>Character name</span>
                <input value={playerName} onChange={(event) => setPlayerName(event.currentTarget.value)} />
              </label>
              <label>
                <span>Pronouns</span>
                <input value={playerPronouns} onChange={(event) => setPlayerPronouns(event.currentTarget.value)} />
              </label>
              <label>
                <span>Background</span>
                <input value={playerBackground} onChange={(event) => setPlayerBackground(event.currentTarget.value)} />
              </label>
              <label>
                <span>Starting build</span>
                <select value={playerBuild} onChange={(event) => setPlayerBuild(event.currentTarget.value as RpgPlayerBuild)}>
                  {BUILD_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Starting location</span>
                <select value={startingLocation} onChange={(event) => setStartingLocation(event.currentTarget.value)}>
                  {STARTING_LOCATIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Difficulty</span>
                <select value={difficulty} onChange={(event) => setDifficulty(event.currentTarget.value as RpgDifficulty)}>
                  <option value="story">Story</option>
                  <option value="normal">Normal</option>
                  <option value="harsh">Harsh</option>
                </select>
              </label>
              <label>
                <span>World activity</span>
                <select value={worldActivity} onChange={(event) => setWorldActivity(event.currentTarget.value as RpgWorldActivity)}>
                  <option value="quiet">Quiet</option>
                  <option value="standard">Standard</option>
                  <option value="living_world">Living World</option>
                </select>
              </label>
              <label>
                <span>Seed</span>
                <input inputMode="numeric" placeholder="Random visible seed" value={seed} onChange={(event) => setSeed(event.currentTarget.value)} />
              </label>
            </div>

            <div className="rpg-launcher-build-note">
              {BUILD_OPTIONS.find((option) => option.value === playerBuild)?.detail}
            </div>

            <div className="rpg-launcher-toggle-grid" aria-label="New Game feature toggles">
              <label>
                <input type="checkbox" checked={companionsEnabled} onChange={(event) => setCompanionsEnabled(event.currentTarget.checked)} />
                <span>Companions enabled</span>
              </label>
              <label>
                <input type="checkbox" checked={validatorEnabled} onChange={(event) => setValidatorEnabled(event.currentTarget.checked)} />
                <span>Grounding validator</span>
              </label>
              <label>
                <input type="checkbox" checked={backgroundSoftAuditEnabled} onChange={(event) => setBackgroundSoftAuditEnabled(event.currentTarget.checked)} />
                <span>Background soft audit</span>
              </label>
              <label>
                <input type="checkbox" checked={llmNarrationEnabled} onChange={(event) => setLlmNarrationEnabled(event.currentTarget.checked)} />
                <span>LLM narration</span>
              </label>
            </div>

            <div className="rpg-launcher-panel-actions">
              <Button type="button" disabled={isLaunching || isPending} loading={isLaunching && launchStatus?.includes('Level 1')} onClick={() => void launchNewGame()}>
                Start New Game
              </Button>
            </div>
          </div>
        ) : null}

        {launcherView === 'load_game' ? (
          <div className="rpg-launcher-panel" aria-label="Load Game browser">
            <div className="rpg-launcher-panel-heading">
              <div>
                <p className="eyebrow">Load Game</p>
                <h4>Saved sessions</h4>
              </div>
              <Button variant="subtle" type="button" disabled={isLaunching} onClick={() => setLauncherView('home')}>
                Close
              </Button>
            </div>
            <div className="rpg-load-game-list">
              {liveSessionSummaries.map((session) => (
                <button key={session.id} type="button" disabled={isLaunching || isPending} onClick={() => void continueSession(session.id)}>
                  <strong>{session.title}</strong>
                  <span>{session.location} • {session.turnLabel} • {session.updatedAt}</span>
                  <small>{session.id}</small>
                </button>
              ))}
            </div>
          </div>
        ) : null}

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
