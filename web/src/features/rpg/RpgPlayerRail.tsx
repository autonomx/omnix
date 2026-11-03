import { RpgSurvivalCard, survivalIsPressing } from './RpgSurvivalCard';
import type { RpgHeroSummaryPreview, RpgPartyMemberPreview, RpgQuestPreview, RpgStatPreview, RpgSurvivalPreview } from './rpgUiTypes';
import './RpgVisualAssets.css';
import './RpgPlayerRail.css';

const HERO_ART_SRC = '/rpg/hero-alyndra.svg';

interface RpgPlayerRailProps {
  activeQuests: RpgQuestPreview[];
  className?: string;
  heroStats: RpgStatPreview[];
  heroSummary: RpgHeroSummaryPreview;
  onOpenQuests?: () => void;
  onSelectCommand?: (command: string) => void;
  partyMembers: RpgPartyMemberPreview[];
  survival: RpgSurvivalPreview;
}

/** The quest to name beside the story: the first one under way, else the first still open. */
export function currentGoal(quests: RpgQuestPreview[]): RpgQuestPreview | undefined {
  const open = quests.filter((quest) => !['completed', 'failed', 'abandoned'].includes(quest.status?.toLowerCase() ?? ''));
  return open.find((quest) => quest.status?.toLowerCase() === 'active') ?? open[0];
}

/** The hero at a glance: how they stand, what they are after, and what needs attention now. The rest is on the bar. */
export function RpgPlayerRail({
  activeQuests,
  className,
  heroStats,
  heroSummary,
  onOpenQuests,
  onSelectCommand,
  partyMembers,
  survival,
}: RpgPlayerRailProps) {
  const railClassName = className ? `rpg-left-rail ${className}` : 'rpg-left-rail';
  const heroAvatarClassName = heroSummary.source === 'preview'
    ? 'rpg-avatar rpg-hero-avatar rpg-hero-avatar-art'
    : 'rpg-avatar rpg-hero-avatar';
  const goal = currentGoal(activeQuests);

  return (
    <aside className={railClassName} aria-label="Player, party, and quests">
      <section className="rpg-card rpg-hero-card" aria-label="Your hero">
        <div className="rpg-hero-summary">
          <div className={heroAvatarClassName} aria-hidden="true">
            {heroSummary.source === 'preview' ? <img src={HERO_ART_SRC} alt="" loading="lazy" /> : heroSummary.avatar}
          </div>
          <div>
            <h3>{heroSummary.name}</h3>
            <p>{heroSummary.subtitle}</p>
          </div>
        </div>
        <div className="rpg-stat-stack">
          {heroStats.map((stat) => (
            <div className="rpg-stat-row" key={stat.label}>
              <span>{stat.label}</span>
              <strong>{stat.value}</strong>
              <span className={`rpg-meter rpg-meter-${stat.tone}`} role="img" aria-label={`${stat.label} ${stat.value}`}>
                <span style={{ width: `${stat.percent}%` }} />
              </span>
            </div>
          ))}
          <div className="rpg-stat-row rpg-stat-row-xp">
            <span>XP</span>
            <strong>{heroSummary.xpLabel}</strong>
            <span className="rpg-meter rpg-meter-xp" role="img" aria-label={`XP ${heroSummary.xpLabel}`}>
              <span style={{ width: `${heroSummary.xpPercent}%` }} />
            </span>
          </div>
        </div>
        <p className="rpg-hero-coin"><span>Gold</span> <strong>{heroSummary.gold}</strong></p>
      </section>

      {survivalIsPressing(survival) ? <RpgSurvivalCard onSelectCommand={onSelectCommand} survival={survival} /> : null}

      {goal ? (
        <section className="rpg-card rpg-goal-card" aria-label="Current goal">
          <p className="eyebrow">Goal</p>
          <button className="rpg-goal-button" onClick={onOpenQuests} type="button">
            <strong>{goal.title}</strong>
            {goal.detail ? <span>{goal.detail}</span> : null}
          </button>
        </section>
      ) : null}

      {partyMembers.length ? (
        <section className="rpg-card rpg-party-card" aria-label="Party members">
          <p className="eyebrow">Party</p>
          <div className="rpg-list-stack">
            {partyMembers.map((member) => (
              <article className="rpg-party-line" key={member.name}>
                <strong>{member.name}</strong>
                <span>{member.hp}</span>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </aside>
  );
}
