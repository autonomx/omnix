import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type KeyboardEvent } from 'react';
import { rpgTacticalGridClient } from './api/rpgTacticalGridClient';
import {
  actorLabel,
  adjacentActors,
  cellKey,
  gridCells,
  reachableCells,
  terrainFamily,
  type RpgGridActor,
  type RpgGridCell,
  type RpgGridPoint,
} from './rpgTacticalGridModel';
import './RpgTacticalGrid.css';

const CELL = 56;

interface RpgTacticalGridProps {
  mapInstanceId: string;
  playerActorId: string;
  heroName: string;
  /** A small, read-only preview (the world rail's card). */
  compact?: boolean;
}

export const rpgTacticalGridQueryKey = (mapInstanceId: string, actorId: string) => ['feature', 'rpg', 'tactical-grid', mapInstanceId, actorId];

function initials(label: string): string {
  return label.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join('') || '?';
}

function titleCase(value: string): string {
  return value.split(/[-_]/).filter(Boolean).map((part) => part[0]!.toUpperCase() + part.slice(1)).join(' ');
}

function mapName(mapId: string): string {
  return titleCase(mapId.slice(mapId.lastIndexOf(':') + 1));
}

function errorText(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^.*?(tactical_[a-z_]+|destination_[a-z_]+|stale_[a-z_]+).*$/, '$1').replaceAll('_', ' ');
}

/**
 * The local map as a tactical grid: terrain, what the hero has seen (fog of war), portals, zones and who is where.
 * In combat, on the hero's turn, reachable cells light up: move there, or attack an adjacent enemy. Outside combat
 * the grid shows the place; moving around it happens through the story's turns.
 */
export function RpgTacticalGrid({ mapInstanceId, playerActorId, heroName, compact = false }: RpgTacticalGridProps) {
  const queryClient = useQueryClient();
  const queryKey = rpgTacticalGridQueryKey(mapInstanceId, playerActorId);
  const viewQuery = useQuery({
    queryKey,
    queryFn: () => rpgTacticalGridClient.observe(mapInstanceId, playerActorId),
    retry: false,
  });
  const view = viewQuery.data;
  const [selected, setSelected] = useState<RpgGridPoint | null>(null);
  const [message, setMessage] = useState('');

  const cells = useMemo(() => (view ? gridCells(view.projection) : []), [view]);
  const tactical = view?.tactical ?? { combat_active: false };
  const yourTurn = Boolean(tactical.combat_active && tactical.your_turn);
  const reachable = useMemo(
    () => (view && yourTurn ? reachableCells(view.projection, playerActorId, tactical.movement_remaining ?? 0) : new Map<string, number>()),
    [view, yourTurn, playerActorId, tactical.movement_remaining],
  );
  const hostile = new Set(tactical.hostile_actor_ids ?? []);
  const actors = view?.projection.actors.filter((actor) => !actor.hidden) ?? [];
  const actorAt = new Map<string, RpgGridActor>();
  for (const actor of actors) actorAt.set(cellKey(actor.cell), actor);
  const player = actors.find((actor) => actor.actor_id === playerActorId);
  const attackable = view && yourTurn && (tactical.actions_remaining ?? 0) > 0
    ? adjacentActors(view.projection, playerActorId).filter((actor) => hostile.has(actor.actor_id))
    : [];

  const settle = (text: string) => {
    setMessage(text);
    void queryClient.invalidateQueries({ queryKey });
    void queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'session'] });
  };
  const move = useMutation({
    mutationFn: (destination: RpgGridPoint) => rpgTacticalGridClient.move(mapInstanceId, {
      actorId: playerActorId, destination, campaignRevision: view?.campaign_revision ?? 0,
      mapStateRevision: view?.projection.map_state_revision ?? 0,
    }),
    onSuccess: () => settle('Moved.'),
    onError: (error) => settle(`The move was refused: ${errorText(error)}.`),
  });
  const attack = useMutation({
    mutationFn: (target: RpgGridActor) => rpgTacticalGridClient.attack(mapInstanceId, {
      actorId: playerActorId, targetId: target.actor_id, campaignRevision: view?.campaign_revision ?? 0,
      mapStateRevision: view?.projection.map_state_revision ?? 0,
    }),
    onSuccess: (_result, target) => settle(`Attacked ${actorLabel(target.actor_id, playerActorId, heroName)}.`),
    onError: (error) => settle(`The attack was refused: ${errorText(error)}.`),
  });
  const busy = move.isPending || attack.isPending;

  if (viewQuery.isLoading) return <div className="rpg-grid-empty" role="status">Loading the local map…</div>;
  if (viewQuery.isError || !view) {
    return <div className="rpg-grid-empty" role="alert">The local map could not be loaded: {errorText(viewQuery.error)}.</div>;
  }

  const { width, height } = view.projection.grid;
  const selectedCell: RpgGridCell | null = selected ? cells[selected[1]]?.[selected[0]] ?? null : null;
  const selectedKey = selected ? cellKey(selected) : '';
  const selectedActor = selected ? actorAt.get(selectedKey) ?? null : null;
  const canMoveTo = (point: RpgGridPoint) => reachable.has(cellKey(point)) && !busy;
  const choose = (point: RpgGridPoint) => {
    setSelected(point);
    setMessage('');
  };
  const onBoardKey = (event: KeyboardEvent<SVGSVGElement>) => {
    const current = selected ?? player?.cell ?? [0, 0];
    const step: Record<string, RpgGridPoint> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const delta = step[event.key];
    if (delta) {
      event.preventDefault();
      choose([Math.min(width - 1, Math.max(0, current[0] + delta[0])), Math.min(height - 1, Math.max(0, current[1] + delta[1]))]);
    } else if (event.key === 'Enter' && selected && canMoveTo(selected)) {
      event.preventDefault();
      move.mutate(selected);
    }
  };
  const statusLabel = !tactical.combat_active
    ? 'Exploring'
    : yourTurn
      ? `Your turn · ${tactical.movement_remaining ?? 0} movement · ${tactical.actions_remaining ?? 0} action${tactical.actions_remaining === 1 ? '' : 's'}`
      : `${actorLabel(tactical.current_actor_id ?? '', playerActorId, heroName)}'s turn`;

  const board = (
    <svg
      aria-label={`${mapName(view.projection.map_id)} grid, ${width} by ${height} cells`}
      className="rpg-grid-board"
      onKeyDown={compact ? undefined : onBoardKey}
      role="img"
      tabIndex={compact ? -1 : 0}
      viewBox={`0 0 ${width * CELL} ${height * CELL}`}
    >
      <defs>
        <pattern id="rpg-grid-unknown" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="12" className="rpg-grid-hatch" />
        </pattern>
      </defs>
      {cells.flat().map((cell) => {
        const key = cellKey(cell.point);
        const family = terrainFamily(cell.terrain);
        return (
          <g key={key} transform={`translate(${cell.point[0] * CELL} ${cell.point[1] * CELL})`}
            className="rpg-grid-cell" data-cell={key}
            onClick={compact ? undefined : () => choose(cell.point)}
            onDoubleClick={compact || !canMoveTo(cell.point) ? undefined : () => move.mutate(cell.point)}>
            <rect width={CELL} height={CELL} className={`rpg-grid-terrain rpg-grid-terrain-${family}`}
              fill={family === 'unknown' ? 'url(#rpg-grid-unknown)' : undefined} />
            {cell.terrain && !cell.visible ? <rect width={CELL} height={CELL} className="rpg-grid-remembered" /> : null}
            {cell.zone ? <rect width={CELL} height={CELL} className="rpg-grid-zone" /> : null}
            {reachable.has(key) ? <rect x={3} y={3} width={CELL - 6} height={CELL - 6} rx={6} className="rpg-grid-reachable" /> : null}
            {cell.portal ? <text x={CELL / 2} y={CELL / 2 + 7} className="rpg-grid-portal" aria-hidden="true">⇲</text> : null}
            {key === selectedKey ? <rect x={1.5} y={1.5} width={CELL - 3} height={CELL - 3} rx={5} className="rpg-grid-selected" /> : null}
          </g>
        );
      })}
      {actors.map((actor) => {
        const label = actorLabel(actor.actor_id, playerActorId, heroName);
        const tone = actor.actor_id === playerActorId ? 'player' : hostile.has(actor.actor_id) ? 'hostile' : 'other';
        const sizeX = (actor.footprint_width ?? 1) * CELL;
        const sizeY = (actor.footprint_height ?? 1) * CELL;
        return (
          <g key={actor.actor_id} className={`rpg-grid-token rpg-grid-token-${tone}`} data-actor={actor.actor_id}
            transform={`translate(${actor.cell[0] * CELL + sizeX / 2} ${actor.cell[1] * CELL + sizeY / 2})`}
            onClick={compact ? undefined : () => choose(actor.cell)}>
            <title>{label}</title>
            <circle r={Math.min(sizeX, sizeY) * 0.36} className="rpg-grid-token-disc" />
            <text y={6} className="rpg-grid-token-label">{initials(label)}</text>
          </g>
        );
      })}
    </svg>
  );

  if (compact) return <div className="rpg-grid rpg-grid-compact">{board}</div>;

  return (
    <section className="rpg-grid" aria-label="Local tactical map">
      <header className="rpg-grid-status">
        <span className={`rpg-grid-mode${tactical.combat_active ? ' rpg-grid-mode-combat' : ''}`}>{tactical.combat_active ? `Combat · round ${tactical.round ?? 1}` : 'Exploration'}</span>
        <strong>{statusLabel}</strong>
        <small>{tactical.combat_active
          ? yourTurn ? 'Lit cells are within reach: double-click one, or select it and choose Move here.' : 'Waiting for the other side to act.'
          : 'This is what your character has seen. Move around it through your turns; in combat, you move here.'}</small>
      </header>
      <div className="rpg-grid-layout">
        <div className="rpg-grid-board-frame">{board}</div>
        <aside className="rpg-grid-side">
          <section className="rpg-grid-card" aria-label="Selected cell">
            {selectedCell ? (
              <>
                <h4>{selectedActor ? actorLabel(selectedActor.actor_id, playerActorId, heroName) : selectedCell.terrain ? titleCase(selectedCell.terrain.terrain_id) : 'Unexplored'}</h4>
                <dl>
                  <div><dt>Cell</dt><dd>{selectedCell.point[0] + 1}, {selectedCell.point[1] + 1}</dd></div>
                  {selectedCell.terrain ? <div><dt>Terrain</dt><dd>{titleCase(selectedCell.terrain.terrain_id)}{selectedCell.terrain.walkable ? ` · cost ${selectedCell.terrain.movement_cost}` : ' · impassable'}{selectedCell.terrain.blocks_sight ? ' · blocks sight' : ''}</dd></div> : null}
                  {selectedCell.zone ? <div><dt>Area</dt><dd>{selectedCell.zone.name}</dd></div> : null}
                  {selectedCell.portal ? <div><dt>Exit</dt><dd>To {mapName(selectedCell.portal.target.map_id)}{selectedCell.portal.state && selectedCell.portal.state !== 'open' ? ` (${selectedCell.portal.state})` : ''}</dd></div> : null}
                  {reachable.has(selectedKey) ? <div><dt>Move cost</dt><dd>{reachable.get(selectedKey)}</dd></div> : null}
                </dl>
                {canMoveTo(selectedCell.point) ? <button type="button" className="rpg-grid-action" onClick={() => move.mutate(selectedCell.point)}>Move here</button> : null}
              </>
            ) : <p className="rpg-grid-hint">Select a cell to see its terrain, area and exits.</p>}
            {attackable.map((target) => (
              <button key={target.actor_id} type="button" className="rpg-grid-action rpg-grid-action-danger" disabled={busy} onClick={() => attack.mutate(target)}>
                Attack {actorLabel(target.actor_id, playerActorId, heroName)}
              </button>
            ))}
            {message ? <p className="rpg-grid-message" role="status">{message}</p> : null}
          </section>
          <section className="rpg-grid-card" aria-label="Who is here">
            <h4>Who is here</h4>
            <ul className="rpg-grid-roster">
              {actors.map((actor) => {
                const label = actorLabel(actor.actor_id, playerActorId, heroName);
                const tone = actor.actor_id === playerActorId ? 'player' : hostile.has(actor.actor_id) ? 'hostile' : 'other';
                return (
                  <li key={actor.actor_id}>
                    <button type="button" onClick={() => choose(actor.cell)}>
                      <span className={`rpg-grid-roster-dot rpg-grid-token-${tone}`} aria-hidden="true">{initials(label)}</span>
                      <span>{label}{actor.actor_id === playerActorId ? ' (you)' : hostile.has(actor.actor_id) ? ' · hostile' : ''}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
          <section className="rpg-grid-card rpg-grid-legend" aria-label="Map key">
            <h4>Key</h4>
            <ul>
              {[...new Map(view.projection.grid.terrain_palette.map((rule) => [terrainFamily(rule), rule])).entries()].map(([family, rule]) => (
                <li key={family}><i className={`rpg-grid-swatch rpg-grid-terrain-${family}`} aria-hidden="true" />{titleCase(rule.terrain_id)}{rule.walkable ? '' : ' (blocked)'}</li>
              ))}
              <li><i className="rpg-grid-swatch rpg-grid-swatch-remembered" aria-hidden="true" />Seen before, not in view</li>
              <li><i className="rpg-grid-swatch rpg-grid-swatch-unknown" aria-hidden="true" />Unexplored</li>
              <li><span className="rpg-grid-portal-key" aria-hidden="true">⇲</span>Exit to another map</li>
            </ul>
          </section>
        </aside>
      </div>
    </section>
  );
}

