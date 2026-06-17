import type {
  RpgGearPreview,
  RpgHeroSummaryPreview,
  RpgPartyMemberPreview,
  RpgQuestPreview,
  RpgStatPreview,
} from './rpgUiState';

interface RpgPlayerRailProps {
  activeQuests: RpgQuestPreview[];
  equippedGear: RpgGearPreview[];
  heroStats: RpgStatPreview[];
  heroSummary: RpgHeroSummaryPreview;
  partyMembers: RpgPartyMemberPreview[];
}

export function RpgPlayerRail({ activeQuests, equippedGear, heroStats, heroSummary, partyMembers }: RpgPlayerRailProps) {
  return (
    <aside className="rpg-left-rail" aria-label="Player, party, and quests">
      <section className="rpg-card rpg-hero-card">
        <p className="eyebrow">Your hero</p>
        <div className="rpg-hero-summary">
          <div className="rpg-avatar rpg-hero-avatar" aria-hidden="true">
            {heroSummary.avatar}
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
        </div>
        <div className="rpg-xp-row">
          <span>XP</span>
          <span className="rpg-meter rpg-meter-xp" aria-label={`XP ${heroSummary.xpLabel}`}>
            <span style={{ width: `${heroSummary.xpPercent}%` }} />
          </span>
          <strong>{heroSummary.xpLabel}</strong>
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

      <section className="rpg-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">Equipped gear</p>
        </div>
        <div className="rpg-list-stack">
          {equippedGear.map((item) => (
            <article className="rpg-list-row" key={item.name}>
              <span className="rpg-icon-tile" aria-hidden="true">
                {item.icon}
              </span>
              <div>
                <strong>{item.name}</strong>
                <span>{item.slot}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="rpg-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">Party</p>
          <span>{partyMembers.length} / 4</span>
        </div>
        <div className="rpg-list-stack">
          {partyMembers.map((member) => (
            <article className="rpg-party-row" key={member.name}>
              <span className="rpg-avatar rpg-avatar-small" aria-hidden="true">
                {member.avatar}
              </span>
              <div>
                <strong>{member.name}</strong>
                <span>{member.role}</span>
              </div>
              <span className="rpg-party-health">
                <span style={{ width: `${member.percent}%` }} />
              </span>
              <small>{member.hp}</small>
            </article>
          ))}
        </div>
        <button className="rpg-secondary-button" type="button">
          + Add companion
        </button>
      </section>

      <section className="rpg-card">
        <p className="eyebrow">Active quests</p>
        <div className="rpg-list-stack">
          {activeQuests.map((quest) => (
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
          ))}
        </div>
      </section>
    </aside>
  );
}
