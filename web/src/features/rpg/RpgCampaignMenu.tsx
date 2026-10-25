import { Button } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { rpgSessionClient, type RpgLaunchResponse } from './api/rpgSessionClient';
import { rpgPlayerMessage } from './rpgPlayerMessage';
import { RpgSavePointsPanel } from './RpgSavePointsPanel';
import { setRpgLauncherDialog, setRpgLauncherHomeGrid, useRpgLauncherView } from './rpgLauncherSlots';
import type { RpgSessionSummaryPreview } from './rpgUiTypes';
import './RpgSessionLauncher.css';

interface RpgCampaignMenuProps {
  campaignMenuHost?: HTMLElement | null;
  isPending: boolean;
  /** The campaign being played, when there is one. */
  liveSessionId: string;
  /** A turn the menu ran (returning to a save point) changed the campaign. */
  onTurnApplied: () => void;
  renderNewCampaign: (closeLauncher: () => void) => ReactNode;
  selectedSessionId: string;
  sessionRegistration: UseFormRegisterReturn<'sessionId'>;
  sessionSummaries: RpgSessionSummaryPreview[];
}

type LauncherView = 'closed' | 'home' | 'campaign_wizard' | 'load_game' | 'save_points';

const LAUNCHER_TITLES: Record<LauncherView, string> = {
  closed: 'Campaign Menu',
  home: 'Campaign Menu',
  campaign_wizard: 'New Campaign',
  load_game: 'Load Game',
  save_points: 'Save points',
};

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
  const manifest = safeRecord(safeRecord(response.session).manifest);
  if (typeof manifest.session_id === 'string') {
    return manifest.session_id;
  }
  return typeof manifest.id === 'string' ? manifest.id : undefined;
}

/** Starting, loading and saving campaigns: the bar above the play screen and the launcher it opens. */
export function RpgCampaignMenu({
  campaignMenuHost,
  isPending,
  liveSessionId,
  onTurnApplied,
  renderNewCampaign,
  selectedSessionId,
  sessionRegistration,
  sessionSummaries,
}: RpgCampaignMenuProps) {
  const queryClient = useQueryClient();
  const [launchStatus, setLaunchStatus] = useState<string>();
  const [launchError, setLaunchError] = useState<string>();
  const [isLaunching, setIsLaunching] = useState(false);
  const [launcherView, setLauncherView] = useRpgLauncherView<LauncherView>('closed', 'home'); // opens on the header's request

  const liveSessionSummaries = useMemo(
    () => sessionSummaries.filter((session) => session.source === 'live').sort((a, b) => b.sortRank - a.sortRank),
    [sessionSummaries],
  );
  const mostRecentLiveSession = liveSessionSummaries[0];
  const refreshRpgWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'replay-inventory'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
    ]);
  };

  const applySelectedSessionId = (sessionId: string) => {
    void sessionRegistration.onChange({
      target: { name: sessionRegistration.name, value: sessionId },
      type: 'change',
    });
  };

  const closeLauncher = () => setLauncherView('closed');

  /** Runs one launcher action, with its progress and failure on the menu bar. */
  const run = async (progress: string, action: () => Promise<string | undefined>, failure: string) => {
    setIsLaunching(true);
    setLaunchError(undefined);
    setLaunchStatus(progress);
    try {
      setLaunchStatus(await action());
    } catch (error) {
      setLaunchStatus(undefined);
      setLaunchError(rpgPlayerMessage(error, failure));
    } finally {
      setIsLaunching(false);
    }
  };

  const finishLaunch = async (response: RpgLaunchResponse, fallbackSessionId: string | undefined, ready: string) => {
    if (!response.ok) {
      throw new Error(response.error ?? 'The campaign could not be opened.');
    }
    const sessionId = launchedSessionId(response) ?? fallbackSessionId;
    if (sessionId) {
      applySelectedSessionId(sessionId);
    }
    await refreshRpgWorkspace();
    closeLauncher();
    return ready;
  };

  const launchDemoSession = () => run('Starting the demo…', async () => {
    const response = await rpgSessionClient.startRpgPreset('demo_glimmerdeep_pass_lvl14');
    return finishLaunch(response, undefined, 'Demo campaign ready.');
  }, 'The demo could not be started.');

  const continueSession = (session: RpgSessionSummaryPreview) => run(`Loading ${session.title}…`, async () => {
    const response = await rpgSessionClient.continueRpgSession(session.id);
    return finishLaunch(response, session.id, `${session.title} loaded.`);
  }, 'The campaign could not be loaded.');

  const renameSession = (session: RpgSessionSummaryPreview) => {
    const nextName = window.prompt('Rename campaign', session.title);
    if (!nextName || nextName.trim() === session.title) {
      return;
    }
    void run('Renaming…', async () => {
      const response = await rpgSessionClient.renameRpgSession(session.id, nextName.trim());
      if (!response.ok) {
        throw new Error(response.error ?? 'The campaign could not be renamed.');
      }
      await refreshRpgWorkspace();
      return `Renamed to ${nextName.trim()}.`;
    }, 'The campaign could not be renamed.');
  };

  const deleteSession = (session: RpgSessionSummaryPreview) => {
    if (!window.confirm(`Delete "${session.title}"? It is archived and leaves this list.`)) {
      return;
    }
    void run('Deleting…', async () => {
      const response = await rpgSessionClient.deleteRpgSession(session.id);
      if (!response.ok) {
        throw new Error(response.error ?? 'The campaign could not be deleted.');
      }
      if (selectedSessionId === session.id) {
        applySelectedSessionId('');
      }
      await refreshRpgWorkspace();
      return `${session.title} deleted.`;
    }, 'The campaign could not be deleted.');
  };

  const busy = isLaunching || isPending;
  const launcherTitle = LAUNCHER_TITLES[launcherView];
  const backHome = (
    <Button variant="subtle" type="button" disabled={isLaunching} onClick={() => setLauncherView('home')}>
      Back
    </Button>
  );
  const campaignMenuBar = (
    <section className="rpg-session-launcher" aria-label="RPG launcher">
      <Button variant="light" type="button" disabled={busy} onClick={() => setLauncherView('home')}>
        Campaign Menu
      </Button>
      <span className="rpg-session-launcher-summary">
        {mostRecentLiveSession ? `Continue: ${mostRecentLiveSession.title}` : 'Start or load a campaign'}
      </span>
      {launchStatus ? <span className="rpg-session-launcher-status" aria-live="polite">{launchStatus}</span> : null}
      {launchError ? <span className="rpg-session-launcher-error" aria-live="assertive">{launchError}</span> : null}
    </section>
  );

  return (
    <>
      {campaignMenuHost ? createPortal(campaignMenuBar, campaignMenuHost) : campaignMenuBar}

      {launcherView !== 'closed' ? (
        <div className="rpg-launcher-modal" role="dialog" aria-modal="true" aria-label={launcherTitle}>
          <button className="rpg-launcher-backdrop" type="button" aria-label="Close RPG launcher" onClick={closeLauncher} />
          <section ref={setRpgLauncherDialog} className={launcherView === 'campaign_wizard' ? 'rpg-launcher-dialog rpg-launcher-dialog-wide' : 'rpg-launcher-dialog'}>
            <div className="rpg-launcher-panel-heading">
              <div>
                <p className="eyebrow">Campaign launcher</p>
                <h3>{launcherTitle}</h3>
              </div>
              <Button variant="subtle" type="button" disabled={isLaunching} onClick={closeLauncher}>
                Close
              </Button>
            </div>

            {launcherView === 'home' ? (
              <div ref={setRpgLauncherHomeGrid} className="rpg-launcher-home-grid">
                <button className="rpg-launcher-card" type="button" disabled={busy || !mostRecentLiveSession} onClick={() => mostRecentLiveSession && void continueSession(mostRecentLiveSession)}>
                  <strong>Continue</strong>
                  <span>{mostRecentLiveSession ? mostRecentLiveSession.title : 'No campaign yet'}</span>
                </button>
                <button className="rpg-launcher-card" type="button" disabled={busy} onClick={() => setLauncherView('campaign_wizard')}>
                  <strong>New Campaign</strong>
                  <span>Choose a world, an opening and your hero.</span>
                </button>
                <button className="rpg-launcher-card" type="button" disabled={busy || !liveSessionId} onClick={() => setLauncherView('save_points')}>
                  <strong>Save points</strong>
                  <span>{liveSessionId ? 'Name this moment, or return to one you named.' : 'Start or load a campaign first.'}</span>
                </button>
                <button className="rpg-launcher-card" type="button" disabled={busy} onClick={() => void launchDemoSession()}>
                  <strong>Demo Session</strong>
                  <span>A level 14 hero at Glimmerdeep Pass.</span>
                </button>
                <button className="rpg-launcher-card" type="button" disabled={busy || !liveSessionSummaries.length} onClick={() => setLauncherView('load_game')}>
                  <strong>Load Game</strong>
                  <span>Open, rename or delete a campaign.</span>
                </button>
              </div>
            ) : null}

            {launcherView === 'campaign_wizard' ? renderNewCampaign(closeLauncher) : null}

            {launcherView === 'save_points' ? (
              <RpgSavePointsPanel
                busy={busy}
                liveSessionId={liveSessionId}
                onBack={() => setLauncherView('home')}
                onReturned={() => {
                  onTurnApplied();
                  closeLauncher();
                }}
                run={run}
              />
            ) : null}

            {launcherView === 'load_game' ? (
              <div role="group" className="rpg-launcher-panel" aria-label="Load Game browser">
                <div className="rpg-launcher-section-heading">
                  <div>
                    <p className="eyebrow">Load Game</p>
                    <h4>Your campaigns</h4>
                  </div>
                  {backHome}
                </div>
                <div className="rpg-load-game-list">
                  {liveSessionSummaries.map((session) => (
                    <div key={session.id} className="rpg-load-game-card">
                      <button className="rpg-load-game-main" type="button" disabled={busy} onClick={() => void continueSession(session)}>
                        <strong>{session.title}</strong>
                        <span>{session.location} • {session.turnLabel} • {session.updatedAt}</span>
                      </button>
                      <div className="rpg-load-game-actions">
                        <Button size="xs" variant="subtle" type="button" disabled={busy} onClick={() => renameSession(session)}>
                          Rename
                        </Button>
                        <Button size="xs" variant="outline" type="button" disabled={busy} onClick={() => deleteSession(session)}>
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}
