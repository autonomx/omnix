import { useEffect, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill } from '../../design/primitives';
import type { RpgSessionSummaryPreview } from './rpgUiState';
import './RpgPlayFocus.css';

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

  useEffect(() => {
    document.documentElement.classList.toggle(RPG_PLAY_FOCUS_CLASS, isHidden);

    return () => {
      document.documentElement.classList.remove(RPG_PLAY_FOCUS_CLASS);
    };
  }, [isHidden]);

  return (
    <div className="rpg-workspace-header-content">
      {isHidden ? null : (
        <div className="rpg-header-pills" aria-label="RPG runtime status">
          <OmnixStatusPill>Engine: {submitStatus}</OmnixStatusPill>
          <OmnixStatusPill>Session: {selectedSessionSummary.title}</OmnixStatusPill>
          <OmnixStatusPill>Replay-preserving</OmnixStatusPill>
          <code>{module.route}</code>
        </div>
      )}
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
  );
}
