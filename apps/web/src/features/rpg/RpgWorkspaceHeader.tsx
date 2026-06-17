import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill } from '../../design/primitives';
import type { RpgSessionSummaryPreview } from './rpgUiState';

interface RpgWorkspaceHeaderProps {
  module: OmnixModuleDefinition;
  selectedSessionSummary: RpgSessionSummaryPreview;
  submitStatus: string;
}

export function RpgWorkspaceHeader({ module, selectedSessionSummary, submitStatus }: RpgWorkspaceHeaderProps) {
  return (
    <header className="rpg-workstation-header">
      <div>
        <p className="eyebrow">Feature module</p>
        <h2 id="module-title">{module.label} mode</h2>
        <p>{module.summary}</p>
      </div>
      <div className="rpg-header-pills" aria-label="RPG runtime status">
        <OmnixStatusPill>Engine: {submitStatus}</OmnixStatusPill>
        <OmnixStatusPill>Session: {selectedSessionSummary.title}</OmnixStatusPill>
        <OmnixStatusPill>Replay-preserving</OmnixStatusPill>
        <code>{module.route}</code>
      </div>
    </header>
  );
}
