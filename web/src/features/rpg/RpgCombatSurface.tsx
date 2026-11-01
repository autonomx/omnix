import type { RpgFightPreview } from './rpgCombatState';
import './RpgCombatSurface.css';

interface RpgCombatSurfaceProps {
  fight: RpgFightPreview | null;
}

/** The fight on: whose turn it is and how everyone stands. Its moves are the composer's suggestions. */
export function RpgCombatSurface({ fight }: RpgCombatSurfaceProps) {
  if (!fight) return null;
  return (
    <section className="rpg-card rpg-combat-surface" aria-labelledby="rpg-fight-title">
      <div className="rpg-section-heading">
        <div>
          <p className="eyebrow">Fight · round {fight.round}</p>
          <h2 id="rpg-fight-title">{fight.yourTurn ? 'Your turn' : `${fight.currentName}'s turn`}</h2>
        </div>
      </div>

      <ol className="rpg-combat-grid" aria-label="Turn order">
        {fight.fighters.map((fighter) => (
          <li
            aria-current={fighter.current ? 'step' : undefined}
            className={`rpg-combatant-card rpg-combatant-${fighter.side === 'enemy' ? 'enemy' : 'ally'}${fighter.down ? ' is-down' : ''}`}
            key={fighter.id}
          >
            <div>
              <strong>{fighter.name}</strong>
              <small>{fighter.side === 'enemy' ? 'Foe' : 'Your side'}</small>
            </div>
            <span
              aria-label={`${fighter.name}: ${fighter.hp} of ${fighter.maxHp} health`}
              className="rpg-party-health"
              role="img"
            >
              <span style={{ width: `${fighter.percent}%` }} />
            </span>
            <small>
              {fighter.down ? 'Out of the fight' : `${fighter.hp} / ${fighter.maxHp}`}
              {fighter.conditions.length ? ` • ${fighter.conditions.join(', ')}` : ''}
            </small>
          </li>
        ))}
      </ol>
    </section>
  );
}
