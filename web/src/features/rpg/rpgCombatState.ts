/** The fight as the campaign holds it (its combat state): who stands, at what health, and whose turn it is. */

export interface RpgFighterPreview {
  id: string;
  name: string;
  side: 'party' | 'enemy';
  hp: number;
  maxHp: number;
  /** Health left, 0-100. */
  percent: number;
  down: boolean;
  current: boolean;
  conditions: string[];
}

export interface RpgFightPreview {
  round: number;
  yourTurn: boolean;
  currentName: string;
  /** Everyone in the fight, in its turn order. */
  fighters: RpgFighterPreview[];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function number(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

/** The fight on, or ``null`` when there is none. ``heroName`` names the hero (the fight calls them "You"). */
export function buildRpgFight(session: unknown, heroName: string): RpgFightPreview | null {
  const combat = record(record(record(session).simulation_state).combat_state);
  if (combat.active !== true) return null;
  const participants = record(combat.participants);
  const current = typeof combat.current_actor_id === 'string' ? combat.current_actor_id : '';
  const order = (Array.isArray(combat.initiative_order) ? combat.initiative_order : [])
    .map((row) => String(record(row).actor_id ?? ''))
    .filter((id) => id in participants);
  const ids = [...order, ...Object.keys(participants).filter((id) => !order.includes(id))];
  const fighters = ids.map((id): RpgFighterPreview => {
    const row = record(participants[id]);
    const hp = Math.max(0, number(row.hp));
    const maxHp = Math.max(hp, number(row.max_hp), 1);
    const conditions = [
      ...(Array.isArray(row.status_effects) ? row.status_effects : []),
      ...(Array.isArray(row.conditions) ? row.conditions : []),
    ]
      .map((effect) => String(record(effect).kind ?? record(effect).name ?? (typeof effect === 'string' ? effect : '')))
      .filter(Boolean);
    return {
      id,
      name: id === 'player' ? heroName || 'You' : String(row.name ?? id),
      side: row.side === 'enemy' ? 'enemy' : 'party',
      hp,
      maxHp,
      percent: Math.round((hp / maxHp) * 100),
      down: hp <= 0 || row.status === 'defeated' || row.status === 'fled',
      current: id === current,
      conditions: [...new Set(conditions)],
    };
  });
  return {
    round: Math.max(1, number(combat.round)),
    yourTurn: current === 'player',
    currentName: fighters.find((fighter) => fighter.current)?.name ?? '',
    fighters,
  };
}
