"""What the GameLoop mixins read from the loop (for type checkers only).

``GameLoop.__init__`` sets these; the mixins in ``game_loop_*`` use them
through ``self``. The mixins inherit this class only under ``TYPE_CHECKING``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..arc_control.presenters import ArcControlPresenter
    from ..coherence.core import CoherenceCore
    from ..creator.gm_state import GMDirectiveState
    from ..debug.core import DebugCore
    from ..encounter.controller import EncounterController
    from ..encounter.presenter import EncounterPresenter
    from ..encounter.resolver import EncounterResolver
    from ..memory.presenters import MemoryPresenter
    from ..migration.pack_migrator import PackMigrator
    from ..packs.exporter import PackExporter
    from ..packs.loader import PackLoader
    from ..packs.merger import PackMerger
    from ..packs.presenters import PackPresenter
    from ..packs.registry import PackRegistry
    from ..packs.validator import PackValidator
    from ..social_state.core import SocialStateCore
    from .event_bus import EventBus
    from .game_loop import IntentParser, SceneRenderer, StoryDirector


class GameLoopState:
    intent_parser: IntentParser
    event_bus: EventBus
    story_director: StoryDirector
    scene_renderer: SceneRenderer
    _tick_count: int
    _snapshot_systems: list[str]
    coherence_core: CoherenceCore
    social_state_core: SocialStateCore
    gm_directive_state: GMDirectiveState
    debug_core: DebugCore
    encounter_controller: EncounterController
    encounter_resolver: EncounterResolver
    encounter_presenter: EncounterPresenter
    memory_presenter: MemoryPresenter
    arc_control_presenter: ArcControlPresenter
    pack_registry: PackRegistry
    pack_validator: PackValidator
    pack_loader: PackLoader
    pack_merger: PackMerger
    pack_exporter: PackExporter
    pack_presenter: PackPresenter
    pack_migrator: PackMigrator
    last_debug_bundle: dict[str, Any] | None
    last_dialogue_trace: dict[str, Any] | None
    last_control_output: dict[str, Any] | None
    last_action_result: dict[str, Any] | None
