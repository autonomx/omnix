/**
 * The tactical grid of a local map (settlement, dungeon, interior, encounter), as an observer's projection shows it
 * (GET/POST /api/rpg/map-instances/{id}/observers/{actor}/...). Movement mirrors the backend's pathfinder
 * (map_instance_runtime._find_path): eight directions, no cutting corners past a blocked side, a diagonal step costs
 * ceil(1.4 x the terrain cost), and the highest terrain cost under a footprint counts. The server still decides.
 */

export type RpgGridPoint = [number, number];

export interface RpgGridTerrainRule {
  code: string;
  terrain_id: string;
  walkable: boolean;
  movement_cost: number;
  blocks_sight: boolean;
}

export interface RpgGridActor {
  actor_id: string;
  cell: RpgGridPoint;
  facing?: string;
  footprint_width?: number;
  footprint_height?: number;
  hidden?: boolean;
}

export interface RpgGridPortal {
  portal_id: string;
  source: { map_id: string; cell: RpgGridPoint };
  target: { map_id: string; cell: RpgGridPoint };
  state?: string;
}

export interface RpgGridZone {
  zone_id: string;
  name: string;
  cells: RpgGridPoint[];
}

export interface RpgGridProjection {
  map_instance_id: string;
  map_id: string;
  map_state_revision: number;
  observer_actor_id: string;
  visible_cells: RpgGridPoint[];
  known_cells: RpgGridPoint[];
  grid: {
    width: number;
    height: number;
    terrain_rows: string[];
    terrain_palette: RpgGridTerrainRule[];
    unknown_code: string;
  };
  portals: RpgGridPortal[];
  zones: RpgGridZone[];
  actors: RpgGridActor[];
}

/** The observer's turn in combat (read-only; the tactical commands check it again). */
export interface RpgGridTactical {
  combat_active: boolean;
  round?: number;
  current_actor_id?: string;
  your_turn?: boolean;
  movement_remaining?: number;
  actions_remaining?: number;
  hostile_actor_ids?: string[];
}

export interface RpgGridView {
  projection: RpgGridProjection;
  campaign_revision: number | null;
  tactical: RpgGridTactical;
}

export interface RpgGridCell {
  point: RpgGridPoint;
  /** Null where the observer has never seen the cell. */
  terrain: RpgGridTerrainRule | null;
  visible: boolean;
  zone: RpgGridZone | null;
  portal: RpgGridPortal | null;
}

export const cellKey = ([column, row]: RpgGridPoint): string => `${column},${row}`;

export function gridCells(projection: RpgGridProjection): RpgGridCell[][] {
  const palette = new Map(projection.grid.terrain_palette.map((rule) => [rule.code, rule]));
  const visible = new Set(projection.visible_cells.map(cellKey));
  const zones = new Map<string, RpgGridZone>();
  for (const zone of projection.zones) for (const cell of zone.cells) zones.set(cellKey(cell), zone);
  const portals = new Map(projection.portals.map((portal) => [cellKey(portal.source.cell), portal]));
  return Array.from({ length: projection.grid.height }, (_row, row) => Array.from({ length: projection.grid.width }, (_column, column) => {
    const point: RpgGridPoint = [column, row];
    const code = projection.grid.terrain_rows[row]?.[column] ?? projection.grid.unknown_code;
    const key = cellKey(point);
    return {
      point,
      terrain: code === projection.grid.unknown_code ? null : palette.get(code) ?? null,
      visible: visible.has(key),
      zone: zones.get(key) ?? null,
      portal: portals.get(key) ?? null,
    };
  }));
}

function footprint(actor: RpgGridActor, anchor: RpgGridPoint = actor.cell): RpgGridPoint[] {
  const cells: RpgGridPoint[] = [];
  for (let dy = 0; dy < (actor.footprint_height ?? 1); dy += 1) {
    for (let dx = 0; dx < (actor.footprint_width ?? 1); dx += 1) cells.push([anchor[0] + dx, anchor[1] + dy]);
  }
  return cells;
}

const OFFSETS = [[-1, -1], [0, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [0, 1], [1, 1]] as const;

/** The backend's A* heuristic (map_instance_runtime._octile_distance): it assumes 10 per step and 14 per diagonal. */
function octile([leftColumn, leftRow]: RpgGridPoint, [rightColumn, rightRow]: RpgGridPoint): number {
  const dx = Math.abs(leftColumn - rightColumn);
  const dy = Math.abs(leftRow - rightRow);
  const diagonal = Math.min(dx, dy);
  return diagonal * 14 + (Math.max(dx, dy) - diagonal) * 10;
}

type Entry = [number, number, number, RpgGridPoint];

/** A min-heap of (priority, cost, insertion, cell), ordered like Python's heapq on the same tuples. */
class Frontier {
  private items: Entry[] = [];

  get size(): number {
    return this.items.length;
  }

  private static less(left: Entry, right: Entry): boolean {
    return left[0] !== right[0] ? left[0] < right[0] : left[1] !== right[1] ? left[1] < right[1] : left[2] < right[2];
  }

  push(entry: Entry): void {
    const items = this.items;
    items.push(entry);
    let index = items.length - 1;
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if (!Frontier.less(items[index]!, items[parent]!)) break;
      [items[index], items[parent]] = [items[parent]!, items[index]!];
      index = parent;
    }
  }

  pop(): Entry {
    const items = this.items;
    const top = items[0]!;
    const last = items.pop()!;
    if (items.length) {
      items[0] = last;
      let index = 0;
      for (;;) {
        const left = index * 2 + 1;
        const right = left + 1;
        let smallest = index;
        if (left < items.length && Frontier.less(items[left]!, items[smallest]!)) smallest = left;
        if (right < items.length && Frontier.less(items[right]!, items[smallest]!)) smallest = right;
        if (smallest === index) break;
        [items[index], items[smallest]] = [items[smallest]!, items[index]!];
        index = smallest;
      }
    }
    return top;
  }
}

/**
 * Each cell the actor can reach within its movement budget, at the cost the server will charge. The server's A*
 * (map_instance_runtime._find_path) stops at the destination with a heuristic that can overestimate on cheap terrain,
 * so its cost is not always the cheapest path: this runs the same search for each destination.
 */
export function reachableCells(projection: RpgGridProjection, actorId: string, budget: number): Map<string, number> {
  const actor = projection.actors.find((item) => item.actor_id === actorId);
  const reached = new Map<string, number>();
  if (!actor || budget <= 0) return reached;
  const cells = gridCells(projection);
  const occupied = new Set(projection.actors.filter((item) => item.actor_id !== actorId).flatMap((item) => footprint(item).map(cellKey)));
  const terrainAt = ([column, row]: RpgGridPoint) => cells[row]?.[column]?.terrain ?? null;
  const open = (anchor: RpgGridPoint) => footprint(actor, anchor).every((cell) => {
    const terrain = terrainAt(cell);
    return Boolean(terrain?.walkable) && !occupied.has(cellKey(cell));
  });
  const cost = (anchor: RpgGridPoint) => Math.max(...footprint(actor, anchor).map((cell) => terrainAt(cell)?.movement_cost ?? 0));
  const cheapest = Math.min(...projection.grid.terrain_palette.filter((rule) => rule.walkable).map((rule) => rule.movement_cost));

  const pathCost = (destination: RpgGridPoint): number | null => {
    const frontier = new Frontier();
    frontier.push([0, 0, 0, actor.cell]);
    const best = new Map<string, number>([[cellKey(actor.cell), 0]]);
    let insertion = 0;
    const goal = cellKey(destination);
    while (frontier.size) {
      const [, spent, , current] = frontier.pop();
      const currentKey = cellKey(current);
      if (currentKey === goal) break;
      if (spent !== best.get(currentKey)) continue;
      for (const [dx, dy] of OFFSETS) {
        const target: RpgGridPoint = [current[0] + dx, current[1] + dy];
        if (!open(target)) continue;
        const diagonal = dx !== 0 && dy !== 0;
        if (diagonal && (!open([current[0] + dx, current[1]]) || !open([current[0], current[1] + dy]))) continue;
        const terrainCost = cost(target);
        const total = spent + (diagonal ? Math.floor((terrainCost * 14 + 9) / 10) : terrainCost);
        const key = cellKey(target);
        const previous = best.get(key);
        if (previous !== undefined && total >= previous) continue;
        best.set(key, total);
        insertion += 1;
        frontier.push([total + octile(target, destination), total, insertion, target]);
      }
    }
    return best.get(goal) ?? null;
  };

  for (const row of cells) {
    for (const cell of row) {
      const key = cellKey(cell.point);
      if (key === cellKey(actor.cell) || !open(cell.point)) continue;
      // No path can cost less than a straight run over the cheapest terrain.
      if (Math.max(Math.abs(cell.point[0] - actor.cell[0]), Math.abs(cell.point[1] - actor.cell[1])) * cheapest > budget) continue;
      const total = pathCost(cell.point);
      if (total !== null && total <= budget) reached.set(key, total);
    }
  }
  return reached;
}

/** The actors next to the given one (touching its footprint, diagonals included). */
export function adjacentActors(projection: RpgGridProjection, actorId: string): RpgGridActor[] {
  const actor = projection.actors.find((item) => item.actor_id === actorId);
  if (!actor) return [];
  const around = new Set(footprint(actor).flatMap(([column, row]) => [-1, 0, 1].flatMap((dx) => [-1, 0, 1].map((dy) => cellKey([column + dx, row + dy])))));
  return projection.actors.filter((item) => item.actor_id !== actorId && !item.hidden && footprint(item).some((cell) => around.has(cellKey(cell))));
}

/** A readable name for an actor id ("npc:liora-fen" is "Liora Fen"). */
export function actorLabel(actorId: string, playerActorId: string, heroName: string): string {
  if (actorId === playerActorId) return heroName || 'You';
  const name = actorId.includes(':') ? actorId.slice(actorId.lastIndexOf(':') + 1) : actorId;
  return name.split(/[-_]/).filter(Boolean).map((part) => part[0]!.toUpperCase() + part.slice(1)).join(' ') || actorId;
}

/** The colour family a terrain is drawn in, from its id and its rules. */
export function terrainFamily(rule: RpgGridTerrainRule | null): string {
  if (!rule) return 'unknown';
  const id = rule.terrain_id.toLowerCase();
  if (/water|river|lake|sea/.test(id)) return 'water';
  if (/void|chasm|pit|abyss/.test(id)) return 'void';
  if (/wall|cliff|rock|collapsed/.test(id)) return 'wall';
  if (/door|gate|portal/.test(id)) return 'door';
  if (/road|path|bridge|cobble/.test(id)) return 'road';
  if (/forest|tree|wood(?!-floor)|thicket/.test(id)) return 'forest';
  if (/moss|vine|root/.test(id)) return 'moss';
  if (/floor|stone|tile|plank/.test(id)) return 'floor';
  if (/counter|table|furniture|crate/.test(id)) return 'furniture';
  if (/grass|meadow|field|dirt/.test(id)) return 'grass';
  return rule.walkable ? 'grass' : 'wall';
}
