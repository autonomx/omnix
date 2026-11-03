import type { RpgSurvivalPreview } from './rpgUiTypes';
import './RpgSurvivalCard.css';

interface RpgSurvivalCardProps {
  onSelectCommand?: (command: string) => void;
  survival: RpgSurvivalPreview;
}

/** Whether the hero's needs call for attention now: the rail shows them then, and the character sheet always. */
export function survivalIsPressing(survival: RpgSurvivalPreview): boolean {
  return survival.status !== 'Stable' || survival.warnings.length > 0;
}

/** Hunger, thirst and fatigue, and what eases them. */
export function RpgSurvivalCard({ onSelectCommand, survival }: RpgSurvivalCardProps) {
  return (
    <section className="rpg-card rpg-survival-card" aria-label="Survival status">
      <div className="rpg-section-heading">
        <p className="eyebrow">Survival</p>
        <span className={`rpg-survival-status is-${survival.status.toLowerCase()}`}>{survival.status}</span>
      </div>
      <p className="rpg-survival-detail">{survival.detail}</p>
      <div className="rpg-survival-needs">
        {survival.needs.map((need) => (
          <div className="rpg-survival-need" key={need.id}>
            <span>{need.label}</span>
            <strong>{need.value}</strong>
            <span
              role="img"
              aria-label={`${need.label} pressure ${need.value}`}
              className={`rpg-survival-meter is-${need.severity}`}
            >
              <span style={{ width: `${need.percent}%` }} />
            </span>
          </div>
        ))}
      </div>
      {survival.warnings.length ? (
        <div role="group" className="rpg-survival-warnings" aria-label="Survival warnings">
          {survival.warnings.map((warning) => <span key={warning}>{warning}</span>)}
        </div>
      ) : null}
      <div role="group" className="rpg-survival-actions" aria-label="Survival actions">
        {survival.actions.map((action) => (
          <button
            className="rpg-secondary-button"
            disabled={!onSelectCommand}
            key={action.command}
            onClick={() => onSelectCommand?.(action.command)}
            type="button"
          >
            {action.label}
          </button>
        ))}
      </div>
      <small>Each fills in your next turn; send it when you are ready.</small>
    </section>
  );
}
