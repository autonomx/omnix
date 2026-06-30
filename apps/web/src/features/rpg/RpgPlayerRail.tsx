import type { HermesRpgSuggestion } from '../../api/hermesClient';
import type {
  RpgGearPreview,
  RpgHeroSummaryPreview,
  RpgPartyMemberPreview,
  RpgQuestPreview,
  RpgStatPreview,
  RpgSurvivalPreview,
} from './rpgUiState';
import './RpgVisualAssets.css';

const HERO_ART_SRC = '/rpg/hero-alyndra.svg';

type RpgRailPanelState = 'idle' | 'loading' | 'ready' | 'error' | 'empty';

interface RpgTurnReadoutPreview {
  category?: string;
  systems?: string[];
  effectCount?: number;
  groundingStatus?: string;
}

interface RpgRouteDecisionPreview {
  mode: string;
  hermesRole: string;
  owner: string;
  reviewRequired: boolean;
  boundary: string;
}

const DEFAULT_RPG_ROUTE_DECISION: RpgRouteDecisionPreview = {
  mode: 'rpg',
  hermesRole: 'suggest',
  owner: 'rpg_sim',
  reviewRequired: false,
  boundary: 'RPG simulation validates truth before state is accepted.',
};

interface RpgPlayerRailProps {
  activeQuests: RpgQuestPreview[];
  className?: string;
  equippedGear: RpgGearPreview[];
  heroStats: RpgStatPreview[];
  heroSummary: RpgHeroSummaryPreview;
  hermesRouteDecision?: RpgRouteDecisionPreview;
  hermesRouteDecisionState?: RpgRailPanelState;
  hermesSuggestionState?: RpgRailPanelState;
  hermesSuggestions?: HermesRpgSuggestion[];
  hermesTurnReadout?: RpgTurnReadoutPreview;
  hermesTurnReadoutState?: RpgRailPanelState;
  onSelectCommand?: (command: string) => void;
  partyMembers: RpgPartyMemberPreview[];
  survival: RpgSurvivalPreview;
}

function panelStatusLabel(state: RpgRailPanelState, readyLabel = 'ready') {
  return state === 'ready' ? readyLabel : state;
}

export function RpgPlayerRail({
  activeQuests,
  className,
  equippedGear,
  heroStats,
  heroSummary,
  hermesRouteDecision = DEFAULT_RPG_ROUTE_DECISION,
  hermesRouteDecisionState = 'ready',
  hermesSuggestionState = 'idle',
  hermesSuggestions = [],
  hermesTurnReadout,
  hermesTurnReadoutState,
  onSelectCommand,
  partyMembers,
  survival,
}: RpgPlayerRailProps) {
  const railClassName = className ? `rpg-left-rail ${className}` : 'rpg-left-rail';
  const heroAvatarClassName = heroSummary.source === 'preview' ? 'rpg-avatar rpg-hero-avatar rpg-hero-avatar-art' : 'rpg-avatar rpg-hero-avatar';
  const turnReadoutState = hermesTurnReadoutState ?? (hermesTurnReadout ? 'ready' : 'empty');

  return (
    <aside className={railClassName} aria-label="Player, party, and quests">
      <section className="rpg-card rpg-hero-card">
        <p className="eyebrow">Your hero</p>
        <div className="rpg-hero-summary">
          <div className={heroAvatarClassName} aria-hidden="true">
            {heroSummary.source === 'preview' ? <img src={HERO_ART_SRC} alt="" loading="lazy" /> : heroSummary.avatar}
          </div>
          <div>
            <h3>{heroSummary.name}</h3>
            <p>{heroSummary.subtitle}</p>
            <p>{heroSummary.origin}</p>
          </div>
        </div>
        <div className="rpg-stat-stack">
          {heroStats.map((stat) => (
            <div className="rpg-stat-row" key={stat.label}>
              <span>{stat.label}</span>
              <strong>{stat.value}</strong>
              <span className={`rpg-meter rpg-meter-${stat.tone}`} aria-label={`${stat.label} ${stat.value}`}>
                <span style={{ width: `${stat.percent}%` }} />
              </span>
            </div>
          ))}
          <div className="rpg-stat-row">
            <span>XP</span>
            <strong>{heroSummary.xpLabel}</strong>
            <span className="rpg-meter rpg-meter-xp" aria-label={`XP ${heroSummary.xpLabel}`}>
              <span style={{ width: `${heroSummary.xpPercent}%` }} />
            </span>
          </div>
        </div>
        <div className="rpg-resource-grid">
          <div>
            <span>Gold</span>
            <strong>{heroSummary.gold}</strong>
          </div>
          <div>
            <span>Renown</span>
            <strong>{heroSummary.renown}</strong>
          </div>
        </div>
      </section>

      <section className="rpg-card" aria-label="Hermes route decision">
        <div className="rpg-section-heading">
          <p className="eyebrow">Hermes route</p>
          <span>{panelStatusLabel(hermesRouteDecisionState, hermesRouteDecision.mode)}</span>
        </div>
        {hermesRouteDecisionState === 'loading' ? <p className="rpg-empty-state">Loading Hermes route metadata.</p> : null}
        {hermesRouteDecisionState === 'error' ? <p className="rpg-empty-state">Hermes route metadata unavailable; using the safe RPG boundary.</p> : null}
        <div className="rpg-resource-grid">
          <div>
            <span>Role</span>
            <strong>{hermesRouteDecision.hermesRole}</strong>
          </div>
          <div>
            <span>Owner</span>
            <strong>{hermesRouteDecision.owner}</strong>
          </div>
          <div>
            <span>Review</span>
            <strong>{hermesRouteDecision.reviewRequired ? 'required' : 'not required'}</strong>
          </div>
          <div>
            <span>Mode</span>
            <strong>{hermesRouteDecision.mode}</strong>
          </div>
        </div>
        <small>{hermesRouteDecision.boundary}</small>
      </section>

      <section className="rpg-card" aria-label="Hermes suggested actions">
        <div className="rpg-section-heading">
          <p className="eyebrow">Hermes suggestions</p>
          <span>{hermesSuggestionState === 'loading' ? 'loading' : `${hermesSuggestions.length}`}</span>
        </div>
        {hermesSuggestionState === 'idle' ? <p className="rpg-empty-state">Select or create a live RPG session to get Hermes suggestions.</p> : null}
        {hermesSuggestionState === 'error' ? <p className="rpg-empty-state">Hermes suggestions unavailable.</p> : null}
        {hermesSuggestionState === 'empty' ? <p className="rpg-empty-state">No Hermes suggestions for this session yet.</p> : null}
        <div className="rpg-list-stack">
          {hermesSuggestions.map((suggestion) => {
            const command = suggestion.command?.trim() ?? '';
            return (
              <article className="rpg-list-row" key={suggestion.id ?? suggestion.label ?? command}>
                <span className="rpg-icon-tile" aria-hidden="true">✦</span>
                <div>
                  <strong>{suggestion.label ?? command}</strong>
                  <span>{suggestion.reason ?? suggestion.kind ?? 'Prepared by Hermes as a player command.'}</span>
                </div>
                <button
                  className="rpg-secondary-button"
                  disabled={!command || !onSelectCommand}
                  onClick={() => command && onSelectCommand?.(command)}
                  type="button"
                >
                  Use
                </button>
              </article>
            );
          })}
        </div>
        <small>Hermes only fills the command box; the RPG runtime still processes the turn after you submit.</small>
      </section>

      <section className="rpg-card" aria-label="Hermes turn readout">
        <div className="rpg-section-heading">
          <p className="eyebrow">Hermes turn readout</p>
          <span>{panelStatusLabel(turnReadoutState)}</span>
        </div>
        {turnReadoutState === 'loading' ? <p className="rpg-empty-state">Loading latest turn readout.</p> : null}
        {turnReadoutState === 'error' ? <p className="rpg-empty-state">Turn readout unavailable.</p> : null}
        {turnReadoutState === 'empty' ? <p className="rpg-empty-state">No turn readout has been reported for this session yet.</p> : null}
        <div className="rpg-resource-grid">
          <div>
            <span>Category</span>
            <strong>{hermesTurnReadout?.category ?? 'not selected'}</strong>
          </div>
          <div>
            <span>Effects</span>
            <strong>{hermesTurnReadout?.effectCount ?? 0}</strong>
          </div>
          <div>
            <span>Grounding</span>
            <strong>{hermesTurnReadout?.groundingStatus ?? 'not reported'}</strong>
          </div>
          <div>
            <span>Systems</span>
            <strong>{hermesTurnReadout?.systems?.length ?? 0}</strong>
          </div>
        </div>
        <small>{hermesTurnReadout?.systems?.join(', ') ?? 'Turn readout data is supplied by the Hermes RPG turn readout route.'}</small>
      </section>

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
                aria-label={`${need.label} pressure ${need.value}`}
                className={`rpg-survival-meter is-${need.severity}`}
              >
                <span style={{ width: `${need.percent}%` }} />
              </span>
            </div>
          ))}
        </div>
        {survival.warnings.length ? (
          <div className="rpg-survival-warnings" aria-label="Survival warnings">
            {survival.warnings.map((warning) => <span key={warning}>{warning}</span>)}
          </div>
        ) : null}
        <div className="rpg-survival-actions" aria-label="Survival actions">
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
        <small>Actions prepare a deterministic turn command.</small>
      </section>

      <section className="rpg-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">Equipped gear</p>
        </div>
        <div className="rpg-list-stack">
          {equippedGear.length ? (
            equippedGear.map((item) => (
              <article className="rpg-list-row" key={item.name}>
                <span className="rpg-icon-tile" aria-hidden="true">
                  {item.icon}
                </span>
                <div>
                  <strong>{item.name}</strong>
                  <span>{item.slot}</span>
                </div>
              </article>
            ))
          ) : (
            <p className="rpg-empty-state">No equipped gear.</p>
          )}
        </div>
      </section>

      <section className="rpg-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">Party</p>
          <span>{partyMembers.length} / 4</span>
        </div>
        <div className="rpg-list-stack">
          {partyMembers.length ? (
            partyMembers.map((member) => (
              <article className="rpg-party-row" key={member.name}>
                <span className="rpg-avatar rpg-avatar-small" aria-hidden="true">
                  {member.avatar}
                </span>
                <div className="rpg-party-member-copy">
                  <strong>{member.name}</strong>
                  <span>{member.role}</span>
                </div>
                <div className="rpg-party-member-status">
                  <span className="rpg-party-health">
                    <span style={{ width: `${member.percent}%` }} />
                  </span>
                  <small>{member.hp}</small>
                </div>
              </article>
            ))
          ) : (
            <p className="rpg-empty-state">No companions have joined this campaign.</p>
          )}
        </div>
        <button className="rpg-secondary-button" type="button">
          + Add companion
        </button>
      </section>

      <section className="rpg-card">
        <p className="eyebrow">Active quests</p>
        <div className="rpg-list-stack">
          {activeQuests.length ? (
            activeQuests.map((quest) => (
              <article className="rpg-quest-row" key={quest.title}>
                <span className="rpg-quest-icon" aria-hidden="true">
                  {quest.icon}
                </span>
                <div>
                  <strong>{quest.title}</strong>
                  <span>{quest.detail}</span>
                </div>
                <span aria-hidden="true">›</span>
              </article>
            ))
          ) : (
            <p className="rpg-empty-state">No active quests.</p>
          )}
        </div>
      </section>
    </aside>
  );
}
