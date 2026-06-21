import { useEffect, useState } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill } from '../../design/primitives';
import type { RpgSessionSummaryPreview } from './rpgUiState';
import './RpgPlayFocus.css';

interface RpgWorkspaceHeaderProps {
  module: OmnixModuleDefinition;
  selectedSessionSummary: RpgSessionSummaryPreview;
  submitStatus: string;
}

const RPG_PLAY_FOCUS_CLASS = 'rpg-play-focus-mode';

export function RpgWorkspaceHeader({ module, selectedSessionSummary, submitStatus }: RpgWorkspaceHeaderProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isHidden, setIsHidden] = useState(false);
  const headerDetailsId = 'rpg-workstation-header-details';
  const headerClassName = isExpanded ? 'rpg-workstation-header' : 'rpg-workstation-header rpg-workstation-header-collapsed';

  useEffect(() => {
    document.documentElement.classList.toggle(RPG_PLAY_FOCUS_CLASS, isHidden);

    return () => {
      document.documentElement.classList.remove(RPG_PLAY_FOCUS_CLASS);
    };
  }, [isHidden]);

  if (isHidden) {
    return (
      <div className="rpg-layout-controls rpg-header-visibility-controls" aria-label="RPG header visibility controls">
        <button className="rpg-secondary-button rpg-header-toggle" type="button" onClick={() => setIsHidden(false)}>
          Show RPG headers
        </button>
      </div>
    );
  }

  return (
    <header className={headerClassName}>
      <div className="rpg-header-title">
        {isExpanded ? <p className="eyebrow">Feature module</p> : null}
        <h2 id="module-title">{module.label} mode</h2>
        <p id={headerDetailsId} hidden={!isExpanded}>
          {module.summary}
        </p>
      </div>
      <div className="rpg-header-actions">
        <div className="rpg-header-pills" aria-label="RPG runtime status">
          <OmnixStatusPill>Engine: {submitStatus}</OmnixStatusPill>
          <OmnixStatusPill>Session: {selectedSessionSummary.title}</OmnixStatusPill>
          <OmnixStatusPill>Replay-preserving</OmnixStatusPill>
          <code>{module.route}</code>
        </div>
        <button
          className="rpg-secondary-button rpg-header-toggle"
          type="button"
          aria-controls={headerDetailsId}
          aria-expanded={isExpanded}
          onClick={() => setIsExpanded((value) => !value)}
        >
          {isExpanded ? 'Collapse header' : 'Expand header'}
        </button>
        <button className="rpg-secondary-button rpg-header-toggle" type="button" onClick={() => setIsHidden(true)}>
          Hide header
        </button>
      </div>
    </header>
  );
}
