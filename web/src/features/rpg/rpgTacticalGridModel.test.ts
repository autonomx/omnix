import { describe, expect, it } from 'vitest';
import fixture from './rpgTacticalGrid.fixture.json';
import { actorLabel, adjacentActors, gridCells, reachableCells, terrainFamily, type RpgGridProjection } from './rpgTacticalGridModel';

const observed = fixture.observe.projection as unknown as RpgGridProjection;
const revealed = fixture.parity.projection as unknown as RpgGridProjection;
const PLAYER = 'player:rpg_fixture';

describe('the tactical grid model', () => {
  it('reads terrain, fog of war, zones and exits from the projection', () => {
    const cells = gridCells(observed);
    expect(cells).toHaveLength(observed.grid.height);
    expect(cells[0]).toHaveLength(observed.grid.width);
    expect(cells[0]![0]!.terrain).toBeNull(); // unexplored
    expect(cells[3]![5]!.terrain?.terrain_id).toBe('road');
    expect(cells[6]![5]!.portal?.target.map_id).toBe('map:aurelia:starfall-village');
    expect(cells.flat().some((cell) => cell.zone?.name === 'Meridian Scar')).toBe(true);
  });

  it('finds the same reachable cells, at the same costs, as the backend pathfinder', () => {
    const budget = Math.max(...Object.values(fixture.parity.backend_costs));
    const reached = Object.fromEntries(reachableCells(revealed, PLAYER, budget));
    expect(reached).toEqual(fixture.parity.backend_costs);
    const short = reachableCells(revealed, PLAYER, 20);
    expect([...short.values()].every((cost) => cost <= 20)).toBe(true);
    expect(short.size).toBeGreaterThan(0);
  });

  it('never reaches into cells the hero has not seen, or onto another actor', () => {
    const reached = reachableCells(observed, PLAYER, 200);
    const cells = gridCells(observed);
    for (const key of reached.keys()) {
      const [column, row] = key.split(',').map(Number) as [number, number];
      expect(cells[row]![column]!.terrain?.walkable).toBe(true);
    }
    expect(reached.has('6,3')).toBe(false); // Liora Fen stands there
  });

  it('names actors and finds who is adjacent', () => {
    expect(actorLabel('npc:liora-fen', PLAYER, 'Alyndra')).toBe('Liora Fen');
    expect(actorLabel(PLAYER, PLAYER, 'Alyndra')).toBe('Alyndra');
    expect(adjacentActors(observed, PLAYER).map((actor) => actor.actor_id)).toEqual(['npc:liora-fen']);
  });

  it('draws each terrain in a colour family', () => {
    expect(terrainFamily({ code: 'w', terrain_id: 'water', walkable: false, movement_cost: 99, blocks_sight: false })).toBe('water');
    expect(terrainFamily({ code: '.', terrain_id: 'wood-floor', walkable: true, movement_cost: 10, blocks_sight: false })).toBe('floor');
    expect(terrainFamily({ code: 'f', terrain_id: 'forest', walkable: true, movement_cost: 15, blocks_sight: true })).toBe('forest');
    expect(terrainFamily(null)).toBe('unknown');
  });
});
