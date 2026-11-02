"""The tactical grid's own rules: the hero's movement in a fight, cover and reach (RQ-2.6; docs/rpg/design/combat.md).

The fight itself is one rule (``rules/combat/fight.py``); the grid adds where everyone stands. A grid move spends the
hero's movement for their turn, a fresh allowance each time the turn comes round to them; a target behind cover is
harder to hit; a blocked line of sight cannot be attacked. ``session/turn/tactical.py`` turns grid commands into
turns with these rules.
"""
from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import Field

from app.apps.rpg.world.map_actor_footprints import actor_footprint_cells
from app.apps.rpg.world.map_effective_geometry import effective_is_walkable
from app.apps.rpg.world.map_grid_contracts import GridActorPlacement, GridMapDefinition, GridPoint
from app.apps.rpg.world.map_instance_runtime import CampaignMapInstanceSnapshot, FrozenRuntimeModel
from app.apps.rpg.world.map_observer_runtime import has_line_of_sight
from app.apps.rpg.foundation.state import access as _sections


class TacticalSpatialError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


class TacticalSpatialPolicy(FrozenRuntimeModel):
    default_movement_budget: int = Field(default=60, ge=1, le=10_000)
    half_cover_bonus: int = Field(default=2, ge=0, le=20)
    full_cover_bonus: int = Field(default=5, ge=0, le=20)


class CoverAssessment(FrozenRuntimeModel):
    attacker_id: str
    target_id: str
    level: Literal["none", "half", "full", "blocked"]
    defense_bonus: int = Field(ge=0)
    cover_cells: tuple[GridPoint, ...] = ()
    exposed_target_cells: tuple[GridPoint, ...] = ()
    line_of_sight: bool = True


def hero_on_map(campaign_id: str) -> str:
    """The hero's actor on the campaign's maps (the fight calls them ``player``)."""
    return f"player:{campaign_id}"


def movement_left(combat_state: Mapping[str, Any], policy: TacticalSpatialPolicy | None = None) -> tuple[dict[str, Any], int]:
    """The hero's movement this turn, and the record of it: a fresh allowance each time the turn comes round."""
    rules = policy or TacticalSpatialPolicy()
    tactical = dict(combat_state.get("tactical_state") or {}) if isinstance(combat_state.get("tactical_state"), Mapping) else {}
    turn = [int(combat_state.get("round") or 1), int(combat_state.get("turn_index") or 0)]
    if tactical.get("turn") != turn:
        tactical = {"turn": turn, "movement_remaining": rules.default_movement_budget}
    return tactical, int(tactical.get("movement_remaining") or 0)


def grid_turn_summary(simulation_state: Mapping[str, Any], campaign_id: str, observer_actor_id: str) -> dict[str, Any]:
    """What the player's grid shows of the fight: whose turn it is, the hero's movement left, who can be attacked."""
    combat = _sections.combat_state_of(simulation_state) if isinstance(_sections.combat_state_of(simulation_state), Mapping) else {}
    if not combat or combat.get("active") is not True:
        return {"combat_active": False}
    hero = hero_on_map(campaign_id)
    current = str(combat.get("current_actor_id") or "")
    _, left = movement_left(combat)
    participants = raw_participants if isinstance(raw_participants := combat.get("participants"), Mapping) else {}
    return {
        "combat_active": True,
        "round": int(combat.get("round") or 1),
        "current_actor_id": hero if current == "player" else current,
        "your_turn": current == "player" and observer_actor_id == hero,
        "movement_remaining": left if current == "player" else 0,
        "actions_remaining": 1 if current == "player" else 0,
        "hostile_actor_ids": sorted(
            str(actor_id) for actor_id, row in participants.items()
            if isinstance(row, Mapping) and row.get("side") == "enemy" and int(row.get("hp") or 0) > 0
        ),
        # The fight's foes by name: their ids are the fight's own ("enemy:creature-echo-wolf:1").
        "actor_names": {
            str(actor_id): str(row["name"]) for actor_id, row in participants.items()
            if isinstance(row, Mapping) and row.get("side") == "enemy" and row.get("name")
        },
    }


def evaluate_cover(
    definition: GridMapDefinition,
    snapshot: CampaignMapInstanceSnapshot,
    *,
    attacker_id: str,
    target_id: str,
    policy: TacticalSpatialPolicy | None = None,
) -> CoverAssessment:
    """How well the target is covered from the attacker: blocked (no line of sight), full, half, or none."""
    rules = policy or TacticalSpatialPolicy()
    attacker_cells = actor_footprint_cells(snapshot.actor(attacker_id))
    target_cells = actor_footprint_cells(snapshot.actor(target_id))
    exposed = tuple(
        cell for cell in target_cells
        if any(has_line_of_sight(definition, source, cell, snapshot=snapshot) for source in attacker_cells)
    )
    if not exposed:
        return CoverAssessment(attacker_id=attacker_id, target_id=target_id, level="blocked", defense_bonus=0,
                               exposed_target_cells=(), line_of_sight=False)
    dx, dy = _direction_toward(attacker_cells, target_cells)
    cover_cells = tuple(sorted(
        {(cell[0] + dx, cell[1] + dy) for cell in target_cells
         if _inside(definition, (cell[0] + dx, cell[1] + dy))
         and not effective_is_walkable(definition, snapshot, (cell[0] + dx, cell[1] + dy))},
        key=lambda cell: (cell[1], cell[0]),
    ))
    if not cover_cells:
        level: Literal["none", "half", "full", "blocked"] = "none"
        bonus = 0
    elif len(cover_cells) >= len(target_cells):
        level, bonus = "full", rules.full_cover_bonus
    else:
        level, bonus = "half", rules.half_cover_bonus
    return CoverAssessment(attacker_id=attacker_id, target_id=target_id, level=level, defense_bonus=bonus,
                           cover_cells=cover_cells, exposed_target_cells=exposed, line_of_sight=True)


def footprint_distance(left: GridActorPlacement, right: GridActorPlacement) -> int:
    """Squares between two actors' footprints, diagonals counting one."""
    return min(max(abs(a[0] - b[0]), abs(a[1] - b[1]))
               for a in actor_footprint_cells(left) for b in actor_footprint_cells(right))


def _direction_toward(attacker_cells: tuple[GridPoint, ...], target_cells: tuple[GridPoint, ...]) -> GridPoint:
    attacker_x = sum(cell[0] for cell in attacker_cells) / len(attacker_cells)
    attacker_y = sum(cell[1] for cell in attacker_cells) / len(attacker_cells)
    target_x = sum(cell[0] for cell in target_cells) / len(target_cells)
    target_y = sum(cell[1] for cell in target_cells) / len(target_cells)
    dx, dy = _sign(attacker_x - target_x), _sign(attacker_y - target_y)
    if abs(attacker_x - target_x) > abs(attacker_y - target_y):
        dy = 0
    elif abs(attacker_y - target_y) > abs(attacker_x - target_x):
        dx = 0
    return dx, dy


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _inside(definition: GridMapDefinition, cell: GridPoint) -> bool:
    return 0 <= cell[0] < definition.width and 0 <= cell[1] < definition.height


def _living_foes(combat_state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if combat_state.get("active") is not True or not isinstance(combat_state.get("participants"), Mapping):
        return {}
    return {str(actor_id): row for actor_id, row in combat_state["participants"].items()
            if isinstance(row, Mapping) and row.get("side") == "enemy" and int(row.get("hp") or 0) > 0}


def foes_on_grid(snapshot: CampaignMapInstanceSnapshot, combat_state: Mapping[str, Any]) -> CampaignMapInstanceSnapshot:
    """The map as the fight sees it: its living foes standing where the fight put them. The fight owns where its foes
    stand (``combat_state.participants[*].cell``), so this is never stored on the map."""
    on_map = {actor.actor_id for actor in snapshot.actors}
    standing = tuple(
        GridActorPlacement(actor_id=actor_id, cell=(int(row["cell"][0]), int(row["cell"][1])))
        for actor_id, row in sorted(_living_foes(combat_state).items())
        if isinstance(row.get("cell"), (list, tuple)) and len(row["cell"]) == 2 and actor_id not in on_map
    )
    return snapshot.model_copy(update={"actors": (*snapshot.actors, *standing)}) if standing else snapshot


def foes_take_the_field(
    definition: GridMapDefinition,
    snapshot: CampaignMapInstanceSnapshot,
    combat_state: Mapping[str, Any],
    *,
    hero_id: str,
    foes_act: bool,
) -> dict[str, Any] | None:
    """Where the fight's foes stand once its turn is played (combat.md): a foe new to the fight takes the nearest free
    square beside the hero, and when the foes have acted (any turn but the hero's grid move) a foe not beside the hero
    closes in, by the map's own paths. The fight with its foes' squares, or ``None`` when no one moved."""
    from app.apps.rpg.world.map_instance_runtime import MoveActorCommand, resolve_move_command

    foes = _living_foes(combat_state)
    if not foes or hero_id not in {actor.actor_id for actor in snapshot.actors}:
        return None
    hero = snapshot.actor(hero_id)
    participants = {str(key): dict(row) for key, row in dict(combat_state["participants"]).items()}
    changed = False

    def taken(exclude: str) -> set[GridPoint]:
        cells = {cell for actor in snapshot.actors for cell in actor_footprint_cells(actor)}
        return cells | {tuple(row["cell"]) for key, row in participants.items()
                        if key in foes and key != exclude and isinstance(row.get("cell"), list)}

    def beside_the_hero(exclude: str) -> list[GridPoint]:
        blocked = taken(exclude)
        return [cell for cell in ((hero.cell[0] + dx, hero.cell[1] + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                if cell != hero.cell and _inside(definition, cell) and cell not in blocked
                and effective_is_walkable(definition, snapshot, cell)]

    for actor_id in sorted(foes):
        row = participants[actor_id]
        cell = tuple(row["cell"]) if isinstance(row.get("cell"), list) else None
        if cell is None:
            for ring in range(1, max(definition.width, definition.height)):
                blocked = taken(actor_id)
                free = sorted((x, y) for y in range(hero.cell[1] - ring, hero.cell[1] + ring + 1)
                              for x in range(hero.cell[0] - ring, hero.cell[0] + ring + 1)
                              if max(abs(x - hero.cell[0]), abs(y - hero.cell[1])) == ring and _inside(definition, (x, y))
                              and (x, y) not in blocked and effective_is_walkable(definition, snapshot, (x, y)))
                if free:
                    row["cell"], changed = [free[0][0], free[0][1]], True
                    break
            continue
        if not foes_act or max(abs(cell[0] - hero.cell[0]), abs(cell[1] - hero.cell[1])) <= 1:
            continue
        seen = foes_on_grid(snapshot, {**combat_state, "participants": participants})
        def nearest(point: GridPoint, origin: GridPoint = cell) -> tuple[int, int, int, int]:
            dx, dy = abs(point[0] - origin[0]), abs(point[1] - origin[1])
            return max(dx, dy), dx + dy, point[1], point[0]

        for target in sorted(beside_the_hero(actor_id), key=nearest):
            try:
                resolve_move_command(definition, seen, MoveActorCommand(
                    command_id=f"close-in:{actor_id}:{target[0]}:{target[1]}", actor_id=actor_id, destination=target,
                    expected_map_state_revision=seen.map_state_revision))
            except ValueError:  # no way through to that square
                continue
            row["cell"], changed = [target[0], target[1]], True
            break
    return {**combat_state, "participants": participants} if changed else None


__all__ = [
    "CoverAssessment",
    "TacticalSpatialError",
    "TacticalSpatialPolicy",
    "evaluate_cover",
    "foes_on_grid",
    "foes_take_the_field",
    "footprint_distance",
    "grid_turn_summary",
    "hero_on_map",
    "movement_left",
]
