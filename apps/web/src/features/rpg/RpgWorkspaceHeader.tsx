import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import type { OmnixModuleDefinition } from '../../app/modules';
import { RpgLorePanel } from './RpgLorePanel';
import { RpgStarterBubblePromotionPanel } from './RpgStarterBubblePromotionPanel';
import { RpgWorldBundleTransfer } from './RpgWorldBundleTransfer';
import { RpgWorldsCampaignsLibrary } from './RpgWorldsCampaignsLibrary';
import type { RpgSessionSummaryPreview } from './rpgUiState';
import './RpgLoreOverlay.css';
import './RpgWorldLibraryOverlay.css';

interface RpgWorkspaceHeaderProps {
  isLiveDataExpanded: boolean;
  isPlayerRailCollapsed: boolean;
  isWorldRailCollapsed: boolean;
  module: OmnixModuleDefinition;
  onToggleLiveData: () => void;
  onTogglePlayerRail: () => void;
  onToggleWorldRail: () => void;
  selectedSessionSummary: RpgSessionSummaryPreview;
  submitStatus: string;
}

const RPG_SELECTED_SESSION_STORAGE_KEY = 'omnix:rpg:selected-session-id';
const RPG_LAUNCHER_HOME_GRID_SELECTOR = '.rpg-launcher-home-grid';
const RPG_LAUNCHER_DIALOG_SELECTOR = '.rpg-launcher-dialog';
const RPG_LAUNCHER_BUTTON_SELECTOR = '.rpg-session-launcher button';
const RPG_WORLD_LIBRARY_DIALOG_CLASS = 'rpg-launcher-dialog-world-library';

export function RpgWorkspaceHeader(props: RpgWorkspaceHeaderProps) {
  const {
    isLiveDataExpanded,
    isPlayerRailCollapsed,
    isWorldRailCollapsed,
    onToggleLiveData,
    onTogglePlayerRail,
    onToggleWorldRail,
    selectedSessionSummary,
  } = props;
  const [isLoreOpen, setIsLoreOpen] = useState(false);
  const [isWorldLibraryOpen, setIsWorldLibraryOpen] = useState(false);
  const [worldLibraryRequested, setWorldLibraryRequested] = useState(false);
  const [campaignLauncherHomeGrid, setCampaignLauncherHomeGrid] = useState<HTMLElement | null>(null);
  const [campaignLauncherDialog, setCampaignLauncherDialog] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (!isLoreOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsLoreOpen(false);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [isLoreOpen]);

  useEffect(() => {
    const syncLauncherElements = () => {
      const homeGrid = document.querySelector<HTMLElement>(RPG_LAUNCHER_HOME_GRID_SELECTOR);
      const dialog = homeGrid?.closest<HTMLElement>(RPG_LAUNCHER_DIALOG_SELECTOR)
        ?? document.querySelector<HTMLElement>(RPG_LAUNCHER_DIALOG_SELECTOR);
      setCampaignLauncherHomeGrid(homeGrid);
      setCampaignLauncherDialog(dialog);
      if (!dialog) setIsWorldLibraryOpen(false);
    };

    syncLauncherElements();
    const observer = new MutationObserver(syncLauncherElements);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (worldLibraryRequested && campaignLauncherDialog) {
      setIsWorldLibraryOpen(true);
      setWorldLibraryRequested(false);
    }
  }, [campaignLauncherDialog, worldLibraryRequested]);

  useEffect(() => {
    campaignLauncherDialog?.classList.toggle(RPG_WORLD_LIBRARY_DIALOG_CLASS, isWorldLibraryOpen);
    return () => campaignLauncherDialog?.classList.remove(RPG_WORLD_LIBRARY_DIALOG_CLASS);
  }, [campaignLauncherDialog, isWorldLibraryOpen]);

  const openWorldLibrary = () => {
    if (campaignLauncherDialog) {
      setIsWorldLibraryOpen(true);
      return;
    }
    setWorldLibraryRequested(true);
    document.querySelector<HTMLButtonElement>(RPG_LAUNCHER_BUTTON_SELECTOR)?.click();
  };

  const selectLaunchedSession = (sessionId: string) => {
    try {
      window.localStorage.setItem(RPG_SELECTED_SESSION_STORAGE_KEY, sessionId);
    } catch {
      // Reload still refreshes the session list when storage is unavailable.
    }
    setIsWorldLibraryOpen(false);
    window.location.reload();
  };

  return (
    <>
      <div className="rpg-workspace-header-content">
        <button
          className="rpg-secondary-button rpg-lore-entry-control"
          type="button"
          onClick={() => setIsLoreOpen(true)}
        >
          World Lore
        </button>
        <button
          className="rpg-secondary-button rpg-world-library-entry-control"
          type="button"
          onClick={openWorldLibrary}
        >
          Worlds &amp; Campaigns
        </button>
        <div className="rpg-unified-header-controls" aria-label="Workspace layout controls">
          <button
            className="rpg-secondary-button"
            type="button"
            aria-pressed={isPlayerRailCollapsed}
            onClick={onTogglePlayerRail}
          >
            {isPlayerRailCollapsed ? 'Show player rail' : 'Hide player rail'}
          </button>
          <button
            className="rpg-secondary-button"
            type="button"
            aria-pressed={isWorldRailCollapsed}
            onClick={onToggleWorldRail}
          >
            {isWorldRailCollapsed ? 'Show world rail' : 'Hide world rail'}
          </button>
          <button
            className="rpg-secondary-button rpg-live-data-toggle"
            type="button"
            aria-controls="rpg-live-data-status-details"
            aria-expanded={isLiveDataExpanded}
            onClick={onToggleLiveData}
          >
            {isLiveDataExpanded ? 'Collapse live data' : 'Expand live data'}
          </button>
        </div>
      </div>

      {campaignLauncherHomeGrid ? createPortal(
        <button
          className="rpg-launcher-card"
          type="button"
          onClick={openWorldLibrary}
        >
          <strong>Worlds &amp; Campaigns</strong>
          <span>Create or import worlds, manage maps and images, and launch published scenarios.</span>
        </button>,
        campaignLauncherHomeGrid,
      ) : null}

      {campaignLauncherDialog && isWorldLibraryOpen ? createPortal(
        <div className="rpg-launcher-world-library-view" role="region" aria-label="Worlds and Campaigns view">
          <RpgWorldsCampaignsLibrary
            onBack={() => setIsWorldLibraryOpen(false)}
            onSessionLaunched={selectLaunchedSession}
          />
          <RpgWorldBundleTransfer />
          <RpgStarterBubblePromotionPanel />
        </div>,
        campaignLauncherDialog,
      ) : null}

      {isLoreOpen && typeof document !== 'undefined' ? createPortal(
        <div className="rpg-lore-overlay" role="dialog" aria-modal="true" aria-labelledby="rpg-lore-overlay-title">
          <div className="rpg-lore-overlay-shell">
            <header className="rpg-lore-overlay-heading">
              <div>
                <p className="eyebrow">Campaign bible</p>
                <h2 id="rpg-lore-overlay-title">{selectedSessionSummary.title}</h2>
                <p>{selectedSessionSummary.location} · known world lore and discovered dossiers</p>
              </div>
              <button className="rpg-secondary-button" type="button" onClick={() => setIsLoreOpen(false)}>
                Back to Play
              </button>
            </header>
            <div className="rpg-lore-overlay-content">
              <RpgLorePanel
                labelledById="rpg-lore-overlay-title"
                panelId="rpg-lore-overlay-panel"
                role="region"
              />
            </div>
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
