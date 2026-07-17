import { useEffect, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { createOmnixModePreview } from '../../app/omnixModePreview';
import { OmnixStatusPill } from '../../design/primitives';
import { RpgStarterBubblePromotionPanel } from './RpgStarterBubblePromotionPanel';
import { RpgWorldBundleTransfer } from './RpgWorldBundleTransfer';
import { RpgWorldsCampaignsLibrary } from './RpgWorldsCampaignsLibrary';
import type { RpgSessionSummaryPreview } from './rpgUiState';
import './RpgPlayFocus.css';
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

const RPG_PLAY_FOCUS_CLASS = 'rpg-play-focus-mode';
const RPG_SELECTED_SESSION_STORAGE_KEY = 'omnix:rpg:selected-session-id';

export function RpgWorkspaceHeader({
  isLiveDataExpanded,
  isPlayerRailCollapsed,
  isWorldRailCollapsed,
  module,
  onToggleLiveData,
  onTogglePlayerRail,
  onToggleWorldRail,
  selectedSessionSummary,
  submitStatus,
}: RpgWorkspaceHeaderProps) {
  const [isHidden, setIsHidden] = useState(false);
  const [isWorldLibraryOpen, setIsWorldLibraryOpen] = useState(false);
  const routePreview = createOmnixModePreview('rpg');

  useEffect(() => {
    document.documentElement.classList.toggle(RPG_PLAY_FOCUS_CLASS, isHidden);

    return () => {
      document.documentElement.classList.remove(RPG_PLAY_FOCUS_CLASS);
    };
  }, [isHidden]);

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
        {isHidden ? null : (
          <div className="rpg-header-pills" aria-label="RPG runtime status">
            <OmnixStatusPill>Engine: {submitStatus}</OmnixStatusPill>
            <OmnixStatusPill>Session: {selectedSessionSummary.title}</OmnixStatusPill>
            <OmnixStatusPill>Replay-preserving</OmnixStatusPill>
            <OmnixStatusPill>Route: {routePreview.path}</OmnixStatusPill>
            <code>{module.route}</code>
          </div>
        )}
        <button
          className="rpg-secondary-button rpg-world-library-entry-control"
          type="button"
          onClick={() => setIsWorldLibraryOpen(true)}
        >
          Worlds &amp; Campaigns
        </button>
        <div className="rpg-unified-header-controls" aria-label="Workspace layout controls">
          <button className="rpg-secondary-button rpg-header-toggle" type="button" onClick={() => setIsHidden((value) => !value)}>
            {isHidden ? 'Show header' : 'Hide header'}
          </button>
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

      {isWorldLibraryOpen ? (
        <div className="rpg-world-library-overlay" role="dialog" aria-modal="true" aria-label="Worlds and Campaigns">
          <RpgStarterBubblePromotionPanel />
          <RpgWorldBundleTransfer />
          <RpgWorldsCampaignsLibrary
            onBack={() => setIsWorldLibraryOpen(false)}
            onSessionLaunched={selectLaunchedSession}
          />
        </div>
      ) : null}
    </>
  );
}
