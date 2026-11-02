"""TurnOutcome: the one result of a turn (RQ-1.3, roadmap §4.1 "One result").

A frozen model: what kind of turn it was, what the player meant, what it changed (in the closed vocabulary of
``foundation.state.changes``), what the world did, where its narration is, how the play screen should show it,
how long it took and how many model calls it made. The turn route serializes it once, as ``outcome`` beside
the transitional fields of ``rpg_turn_response_v2`` (``build_turn_response_v2`` is the adapter that keeps them
until the web client reads only the outcome).

Until the pipeline (RQ-1.4) plans and resolves turns itself, ``build_turn_outcome`` reads the outcome off the
turn's existing result and the documents before and after it: ``applied_changes`` comes from
``foundation.state.extract.changes_between``, or from the pipeline for a turn it ran (RQ-1.4), which also names
the ``planned_action``; ``dialogue_plan`` is empty.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.foundation.model_calls import used_calls
from app.apps.rpg.foundation.state.changes import StateChange
from app.apps.rpg.foundation.state.changes import parse_changes
from app.apps.rpg.foundation.state.extract import CHANGE_SECTIONS, changes_between
from app.apps.rpg.narration.presentation.outcome_facts import OutcomeFact, Suggestion, outcome_facts
from app.apps.rpg.foundation.state import access as _sections

TURN_OUTCOME_FORMAT: Final = "rpg_turn_outcome_v1"
TurnKind = Literal["player_text", "structured_action", "world_tick", "system"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TurnIntent(_Frozen):
    """What the turn took the player to mean, and who decided it (the game's own rules or a model)."""

    action_type: str = ""
    semantic_action_type: str = ""
    semantic_family: str = ""
    target_id: str = ""
    source: str = ""


class NarrationReference(_Frozen):
    response_id: str = ""
    status: str = ""
    speaker_ids: tuple[str, ...] = ()


class PresentationHints(_Frozen):
    """What the play screen needs to show the turn without reading the document."""

    changed_sections: tuple[str, ...] = ()
    location_name: str = ""
    refused: bool = False
    # What changed, as the outcome card states it: coin, items, health, quest steps, offers, the dice (RQ-7.2).
    facts: tuple[OutcomeFact, ...] = ()
    # What to do next (RQ-7.3): suggestions from the scene, and the answers to the game's question when it asked one.
    suggestions: tuple[Suggestion, ...] = ()
    choices: tuple[Suggestion, ...] = ()


class ModelCalls(_Frozen):
    total: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)


class TurnOutcome(_Frozen):
    format_version: Literal["rpg_turn_outcome_v1"] = TURN_OUTCOME_FORMAT
    kind: TurnKind = "player_text"
    turn_id: str = ""
    submission_id: str = ""
    revision: int | None = None
    document_version: int | None = None
    intent: TurnIntent = Field(default_factory=TurnIntent)
    planned_action: str | None = None
    applied_changes: tuple[StateChange, ...] = ()
    world_events: tuple[dict[str, Any], ...] = ()
    dialogue_plan: dict[str, Any] | None = None
    # A structured action's own answer, besides its changes: a grid move's cell and the map's revision.
    action_result: dict[str, Any] | None = None
    narration: NarrationReference = Field(default_factory=NarrationReference)
    presentation: PresentationHints = Field(default_factory=PresentationHints)
    timings: dict[str, float] = Field(default_factory=dict)
    model_calls: ModelCalls = Field(default_factory=ModelCalls)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(sources: tuple[dict[str, Any], ...], key: str) -> str:
    for source in sources:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _timings(value: Any) -> dict[str, float]:
    return {str(key): float(number) for key, number in _mapping(value).items()
            if isinstance(number, (int, float)) and not isinstance(number, bool)}


def build_turn_outcome(
    result: Mapping[str, Any],
    *,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    kind: TurnKind = "player_text",
    submission_id: str = "",
    model_calls: Mapping[str, int] | None = None,
    timings: Mapping[str, Any] | None = None,
) -> TurnOutcome:
    """The outcome of a turn from its result and the documents before and after it."""
    root = _mapping(result)
    sources = (root, _mapping(root.get("result")), _mapping(root.get("authoritative")))
    planned = _mapping(root.get("turn_pipeline"))
    if isinstance(planned.get("changes"), list):
        # A turn the pipeline ran says what it changed (RQ-1.4); no need to read it off the documents.
        changes = parse_changes(planned["changes"])
    else:
        changes = changes_between(before, after) if before is not None and after is not None else []
    canonical = _mapping(root.get("canonical_narrative_response"))
    speakers = tuple(dict.fromkeys(
        str(block.get("speaker_id")) for block in canonical.get("blocks") or ()
        if isinstance(block, Mapping) and block.get("speaker_id")
    ))
    after_doc = _mapping(after)
    manifest = _mapping(after_doc.get("manifest"))
    runtime = _mapping(_sections.runtime_state_of(after_doc))
    calls = {str(key): int(value) for key, value in sorted(_mapping(model_calls).items()) if value}
    outcome = _first(sources, "outcome")
    events = [event for event in root.get("world_events") or _mapping(root.get("authoritative")).get("world_events") or ()
              if isinstance(event, Mapping)]
    return TurnOutcome(
        kind=planned.get("kind") or kind,
        turn_id=_first(sources, "turn_id"),
        submission_id=submission_id or _first(sources, "submission_id"),
        revision=int(runtime["state_revision"]) if isinstance(runtime.get("state_revision"), int) else None,
        document_version=int(manifest["schema_version"]) if isinstance(manifest.get("schema_version"), int) else None,
        intent=TurnIntent(
            action_type=_first(sources, "action_type"),
            semantic_action_type=_first(sources, "semantic_action_type"),
            semantic_family=_first(sources, "semantic_family"),
            target_id=_first(sources, "target_id"),
            source=_first(sources, "source"),
        ),
        planned_action=str(planned["mechanic"]) if planned.get("mechanic") else None,
        applied_changes=tuple(changes),
        action_result=dict(planned["action_result"]) if isinstance(planned.get("action_result"), Mapping) else None,
        world_events=tuple(dict(event) for event in events[:12]),
        narration=NarrationReference(
            response_id=str(canonical.get("response_id") or ""),
            status=_first(sources, "narration_status"),
            speaker_ids=speakers,
        ),
        presentation=PresentationHints(
            changed_sections=tuple(dict.fromkeys(CHANGE_SECTIONS[change.type] for change in changes)),
            location_name=str(_mapping(after_doc.get("state")).get("current_location_name") or ""),
            refused=outcome in {"failure", "refused", "blocked"} or root.get("ok") is False,
            facts=outcome_facts(changes, after_doc),
            suggestions=tuple(Suggestion(**row) for row in _mapping(planned.get("presentation")).get("suggestions") or ()),
            choices=tuple(Suggestion(**row) for row in _mapping(planned.get("presentation")).get("choices") or ()),
        ),
        timings=_timings(timings),
        model_calls=ModelCalls(total=used_calls(calls), by_kind=calls),  # a discarded reply counted apart (EV-9)
    )
