import { describe, expect, it } from 'vitest';
import { buildRpgFight } from './rpgCombatState';

const session = (combat: Record<string, unknown>) => ({ simulation_state: { combat_state: combat } });

const FIGHT = {
  active: true,
  round: 2,
  current_actor_id: 'enemy:creature-echo-wolf:1',
  initiative_order: [{ actor_id: 'enemy:creature-echo-wolf:1' }, { actor_id: 'player' }, { actor_id: 'npc:liora-fen' }],
  participants: {
    player: { side: 'party', name: 'You', hp: 80, max_hp: 100, status_effects: [] },
    'npc:liora-fen': { side: 'party', name: 'Liora Fen', hp: 0, max_hp: 16, status: 'defeated' },
    'enemy:creature-echo-wolf:1': { side: 'enemy', name: 'Echo Wolf', hp: 4, max_hp: 10, status_effects: [{ kind: 'hindered' }] },
  },
};

describe('the fight on the play screen', () => {
  it('reads the fight as the campaign holds it: its turn order, health and whose turn it is', () => {
    const fight = buildRpgFight(session(FIGHT), 'Wren');

    expect(fight).toMatchObject({ round: 2, yourTurn: false, currentName: 'Echo Wolf' });
    expect(fight?.fighters.map((fighter) => [fighter.name, fighter.side, fighter.hp, fighter.maxHp, fighter.down])).toEqual([
      ['Echo Wolf', 'enemy', 4, 10, false],
      ['Wren', 'party', 80, 100, false],
      ['Liora Fen', 'party', 0, 16, true],
    ]);
    expect(fight?.fighters[0]).toMatchObject({ current: true, percent: 40, conditions: ['hindered'] });
  });

  it('shows no fight when none is on', () => {
    expect(buildRpgFight(session({ ...FIGHT, active: false }), 'Wren')).toBeNull();
    expect(buildRpgFight(undefined, 'Wren')).toBeNull();
  });
});
