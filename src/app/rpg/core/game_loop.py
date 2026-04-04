"""Game Loop — Single authority for game tick execution.

PHASE 1 — STABILIZE Step 1:
This module creates the single GameLoop authority as specified in rpg-design.txt.

PHASE 1.5 — ENFORCEMENT PATCH:
- Replaced _active_loop class variable with contextvars for async/multiplayer safety
- Inject tick ID into EventBus before collecting events
- Future-proof for async and multiple sessions

PHASE 2.5 — SNAPSHOT INTEGRATION:
- SnapshotManager integrated for periodic state serialization
- Automatic snapshots every N ticks (configurable, default 50)
- Enables hybrid replay (snapshot + events) for O(1) state recovery
- Time-travel debugging now uses snapshots for fast seeking

ARCHITECTURE RULE:
This system must NOT directly call other systems.
Use EventBus for all cross-system communication.

Before this refactor:
    - player_loop.py had its own while True loop
    - world_loop.py had its own while True loop
    - Multiple tick() methods existed across systems

After this refactor:
    - ONLY GameLoop.tick() controls execution
    - All other loops are removed/deprecated

Tick Pipeline:
    1. Parse player intent
    2. Advance world simulation
    3. Update NPCs
    4. Collect events from the bus
    5. Process narrative via Director
    6. Render scene
    7. Save snapshot at interval
"""

import contextvars
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol
import inspect

from .event_bus import Event, EventBus
from .snapshot_manager import SnapshotManager
from .effects import EffectManager, EffectPolicy
from .tool_runtime_boundary import ToolRuntimeRecorder
from ..recovery.manager import RecoveryManager
from ..execution.resolver import ActionResolver
from ..social_state.core import SocialStateCore
from ..memory.core import CampaignMemoryCore
from ..memory.presenters import MemoryPresenter
from ..arc_control.controller import ArcControlController
from ..arc_control.presenters import ArcControlPresenter
from ..packs.registry import PackRegistry
from ..packs.validator import PackValidator
from ..packs.loader import PackLoader
from ..packs.merger import PackMerger
from ..packs.exporter import PackExporter
from ..packs.presenters import PackPresenter
from ..packs.models import AdventurePack
from ..ux.core import UXCore
from ..dialogue.core import DialogueCore
from ..encounter.controller import EncounterController
from ..encounter.resolver import EncounterResolver
from ..encounter.presenter import EncounterPresenter
from ..world_sim.controller import WorldSimController
from ..world_sim.presenter import WorldSimPresenter


class TickPhase(Enum):
    """Enumeration of tick phases for ordered execution phases."""
    PRE_WORLD = "pre_world"
    POST_WORLD = "post_world"
    PRE_NPC = "pre_npc"
    POST_NPC = "post_npc"


class IntentParser(Protocol):
    """Protocol for intent parser implementations."""
    def parse(self, player_input: str) -> Dict[str, Any]:
        """Parse player input into structured intent."""
        ...


class WorldSystem(Protocol):
    """Protocol for world simulation systems."""
    def tick(self, event_bus: EventBus) -> None:
        """Advance world state by one tick.

        Args:
            event_bus: The shared EventBus for emitting world events.
        """
        ...


class NPCSystem(Protocol):
    """Protocol for NPC update systems."""
    def update(self, intent: Dict[str, Any], event_bus: EventBus) -> None:
        """Update NPC states based on the parsed player intent.

        Args:
            intent: The parsed player intent dictionary.
            event_bus: The shared EventBus for emitting NPC events.
        """
        ...


class StoryDirector(Protocol):
    """Protocol for story director implementations."""
    def process(
        self,
        events: List[Event],
        intent: Dict[str, Any],
        event_bus: EventBus,
        coherence_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process events and intent into narrative output.

        Args:
            events: Events collected from the EventBus.
            intent: The parsed player intent dictionary.
            event_bus: The shared EventBus for emitting narrative events.
            coherence_context: Optional coherence context from CoherenceCore.

        Returns:
            Narrative data for scene rendering.
        """
        ...


class SceneRenderer(Protocol):
    """Protocol for scene rendering implementations."""
    def render(
        self, narrative: Dict[str, Any], coherence_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Render a scene from narrative data.

        Args:
            narrative: Narrative data from the StoryDirector.
            coherence_context: Optional coherence context from CoherenceCore.

        Returns:
            Final scene data to present to the player.
        """
        ...


@dataclass
class TickContext:
    """Context data passed to tick hooks.

    Attributes:
        tick_number: The current tick number (1-based).
        player_input: Raw player input string.
        intent: Parsed intent dictionary.
        events: Events emitted during this tick.
        scene: The rendered scene output.
    """
    tick_number: int = 0
    player_input: str = ""
    intent: Dict[str, Any] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)
    scene: Dict[str, Any] = field(default_factory=dict)


# Context-local storage for active game loop - future-proof for async/multiplayer
_active_loop_ctx = contextvars.ContextVar("active_game_loop", default=None)


class GameLoop:
    """The single authority for game tick execution.

    This class enforces a clean, deterministic game loop:
        1. Parse player intent
        2. Advance world simulation
        3. Update NPCs
        4. Collect events
        5. Narrative processing
        6. Render scene

    It also provides hooks for pre/post tick callbacks and event processing
    callbacks to allow extension without modification.

    Uses contextvars for the active loop guard, making it safe for:
    - async/multithreading environments
    - multiple sessions in the same process

    Example:
        loop = GameLoop(
            intent_parser=MyParser(),
            world=MyWorld(),
            npc_system=MyNPCs(),
            event_bus=EventBus(),
            story_director=MyDirector(),
            scene_renderer=MyRenderer(),
        )
        scene = loop.tick("look around")
    """

    # Kept for backwards compatibility - redirects to contextvar
    @classmethod
    def _get_active_loop(cls):
        """Get active loop from context (backwards compat)."""
        return _active_loop_ctx.get()

    @classmethod
    def _set_active_loop(cls, value):
        """Set active loop in context (backwards compat)."""
        _active_loop_ctx.set(value)

    _active_loop = property(_get_active_loop.__func__, _set_active_loop.__func__)

    def __init__(
        self,
        intent_parser: IntentParser,
        world: WorldSystem,
        npc_system: NPCSystem,
        event_bus: EventBus,
        story_director: StoryDirector,
        scene_renderer: SceneRenderer,
        snapshot_manager: Optional[SnapshotManager] = None,
        effect_manager: Optional[EffectManager] = None,
        tool_runtime_recorder: Optional[ToolRuntimeRecorder] = None,
    ):
        """Initialize the GameLoop with all required subsystems.

        Args:
            intent_parser: Converts player input to structured intents.
            world: World simulation system.
            npc_system: NPC management system.
            event_bus: Central event bus for cross-system communication.
            story_director: Narrative/story director.
            scene_renderer: Renders final scene output.
            snapshot_manager: Optional SnapshotManager for periodic state
                            serialization. If None, a default manager is created
                            with snapshot interval of 50 ticks.
            effect_manager: Optional EffectManager for controlling side effects.
                            If None, a default manager is created.
        """
        self.intent_parser = intent_parser
        self.world = world
        self.npc_system = npc_system
        self.event_bus = event_bus
        self.story_director = story_director
        self.scene_renderer = scene_renderer
        # PHASE 2.5: SnapshotManager for periodic state serialization
        self.snapshot_manager = snapshot_manager or SnapshotManager()
        # PHASE 5.5: EffectManager for side-effect isolation
        self.effect_manager = effect_manager or EffectManager()
        # PHASE 5.7: ToolRuntimeRecorder for deterministic tool/runtime replay
        self.tool_runtime_recorder = tool_runtime_recorder or ToolRuntimeRecorder()

        # PHASE 5.2 — REPLAY/LIVE MODE
        self.mode: str = "live"

        self._tick_count = 0
        self._on_pre_tick: Optional[Callable[[TickContext], None]] = None
        self._on_post_tick: Optional[Callable[[TickContext], None]] = None
        self._on_event: Optional[Callable[[Event], None]] = None

        # PHASE 3 — ACTIVE TIMELINE CONTEXT: Track current event for parent linking
        self.current_event_id: Optional[str] = None

        # PHASE 4.5 — NPC PLANNER: Simulation-based NPC decision making
        self.npc_planner: Optional[Any] = None
        self.npc_system_protocol: Optional[Any] = None  # get_npcs() method
        self.npc_method = None  # PHASE 5.2: Override for planner path

        # PHASE 5.3 — LLM RECORD/REPLAY: Deterministic LLM response caching
        self.llm_recorder: Optional[Any] = None

        # PHASE 5.5 — Inject effect manager into subsystems that support it
        for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
            system = getattr(self, system_name, None)
            if system is not None and hasattr(system, "set_effect_manager"):
                system.set_effect_manager(self.effect_manager)
        # PHASE 5.7 — Inject tool runtime recorder into subsystems that support it
        for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
            system = getattr(self, system_name, None)
            if system is not None and hasattr(system, "set_tool_runtime_recorder"):
                system.set_tool_runtime_recorder(self.tool_runtime_recorder)

        # PHASE 6.0 — CANONICAL COHERENCE CORE
        from ..coherence.core import CoherenceCore
        self.coherence_core = CoherenceCore()
        self._snapshot_systems: List[str] = list(getattr(self, "_snapshot_systems", []))
        if "coherence_core" not in self._snapshot_systems:
            self._snapshot_systems.append("coherence_core")

        # PHASE 6.0 — Inject coherence core into systems that can consume it
        if hasattr(self.story_director, "set_coherence_core"):
            self.story_director.set_coherence_core(self.coherence_core)
        elif hasattr(self.story_director, "coherence_core"):
            self.story_director.coherence_core = self.coherence_core

        # PHASE 7.0 — CREATOR / GM LAYER
        self._init_creator_systems()

        # PHASE 7.3 — SCENE EXECUTION LAYER
        self._init_execution_systems()

        # PHASE 7.6 — PERSISTENT SOCIAL STATE
        self.social_state_core = SocialStateCore()
        if "social_state_core" not in self._snapshot_systems:
            self._snapshot_systems.append("social_state_core")

        # PHASE 7.7 — CAMPAIGN MEMORY (derived read-model layer)
        self.campaign_memory_core = CampaignMemoryCore()
        self.memory_presenter = MemoryPresenter()
        if "campaign_memory_core" not in self._snapshot_systems:
            self._snapshot_systems.append("campaign_memory_core")

        # PHASE 7.8 — ARC CONTROL (steering layer)
        self.arc_control_controller = ArcControlController()
        self.arc_control_presenter = ArcControlPresenter()
        if "arc_control_controller" not in self._snapshot_systems:
            self._snapshot_systems.append("arc_control_controller")

        # PHASE 7.9 — ADVENTURE PACKS (content/config modules)
        self.pack_registry = PackRegistry()
        self.pack_validator = PackValidator()
        self.pack_loader = PackLoader()
        self.pack_merger = PackMerger()
        self.pack_exporter = PackExporter()
        self.pack_presenter = PackPresenter()
        self._applied_pack_ids: set[str] = set()
        if "pack_registry" not in self._snapshot_systems:
            self._snapshot_systems.append("pack_registry")

        # PHASE 8.0 — PLAYER-FACING UX LAYER (stateless presentation/orchestration)
        self.ux_core = UXCore()

        # PHASE 8.2 — ENCOUNTER SYSTEM (tactical mode overlay)
        self.encounter_controller = EncounterController()
        self.encounter_resolver = EncounterResolver()
        self.encounter_presenter = EncounterPresenter()
        self.last_encounter_resolution: dict | None = None
        if "encounter_controller" not in self._snapshot_systems:
            self._snapshot_systems.append("encounter_controller")

        # PHASE 8.3 — WORLD SIMULATION (deterministic background pressure engine)
        self.world_sim_controller = WorldSimController()
        self.world_sim_presenter = WorldSimPresenter()
        self.last_world_sim_result: dict | None = None
        if "world_sim_controller" not in self._snapshot_systems:
            self._snapshot_systems.append("world_sim_controller")

        # PHASE 6.5 — RECOVERY MANAGER
        self._init_recovery_manager()

    # ------------------------------------------------------------------
    # Phase 8.0 — UX Layer Delegates
    # ------------------------------------------------------------------

    def get_scene_payload(self) -> dict:
        """Return a unified scene payload via UXCore."""
        if not hasattr(self, "ux_core"):
            return {"scene": {}, "choices": [], "panels": []}
        return self.ux_core.build_scene_payload(self)

    def get_action_result_payload(self, action_result: dict) -> dict:
        """Return an action-result payload via UXCore."""
        return self.ux_core.build_action_result_payload(self, action_result)

    def open_panel(self, panel_id: str) -> dict:
        """Open a named panel via UXCore."""
        return self.ux_core.open_panel(self, panel_id)

    def select_choice_via_ux(self, choice_id: str) -> dict:
        """Select a choice via the UX action-flow layer."""
        if not hasattr(self, "ux_core"):
            return {"ok": False, "reason": "ux_core_not_available"}
        return self.ux_core.select_choice(self, choice_id)

    def request_recap_via_ux(self) -> dict:
        """Request a recap via the UX action-flow layer."""
        if not hasattr(self, "ux_core"):
            return {"title": "Recap", "summary": "", "scene_summary": {}}
        return self.ux_core.request_recap(self)

    def set_llm_recorder(self, recorder: Any) -> None:
        """
        Attach an LLM recorder for deterministic model replay.

        Args:
            recorder: LLMRecorder instance for recording/replaying LLM responses.
        """
        self.llm_recorder = recorder
        for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
            system = getattr(self, system_name, None)
            if system is not None and hasattr(system, "set_llm_recorder"):
                system.set_llm_recorder(recorder)

    def set_tool_runtime_recorder(self, recorder: Any) -> None:
        """Attach a tool/runtime recorder for deterministic runtime replay."""
        self.tool_runtime_recorder = recorder
        for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
            system = getattr(self, system_name, None)
            if system is not None and hasattr(system, "set_tool_runtime_recorder"):
                system.set_tool_runtime_recorder(recorder)

    def set_mode(self, mode: str) -> None:
        """
        Propagate replay/live mode to subsystems that support it.

        Args:
            mode: Either "replay" or "live".

        Replay mode contract:
        - no fresh LLM calls unless using recorded outputs
        - no fresh randomness outside seeded RNG
        - no external side effects
        - no time-based generation outside deterministic clock
        """
        self.mode = mode
        for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
            system = getattr(self, system_name, None)
            if system is not None and hasattr(system, "set_mode"):
                system.set_mode(mode)
        if hasattr(self, "coherence_core") and self.coherence_core is not None:
            self.coherence_core.set_mode(mode)
        if hasattr(self, "story_director") and hasattr(self.story_director, "set_coherence_core"):
            self.story_director.set_coherence_core(self.coherence_core)
        # PHASE 6.5 — Propagate mode to recovery manager
        if hasattr(self, "recovery_manager") and self.recovery_manager is not None:
            self.recovery_manager.set_mode(mode)

        # PHASE 7.6 — Propagate mode to social state core
        if hasattr(self, "social_state_core") and self.social_state_core is not None:
            self.social_state_core.set_mode(mode)

        # PHASE 7.7 — Propagate mode to campaign memory core
        if hasattr(self, "campaign_memory_core") and self.campaign_memory_core is not None:
            self.campaign_memory_core.set_mode(mode)

        # PHASE 7.8 — Propagate mode to arc control controller
        if hasattr(self, "arc_control_controller") and self.arc_control_controller is not None:
            self.arc_control_controller.set_mode(mode)

        # PHASE 7.0 — propagate creator/GM aware state
        if hasattr(self, "story_director"):
            if hasattr(self.story_director, "set_creator_canon_state"):
                self.story_director.set_creator_canon_state(self.creator_canon_state)
            if hasattr(self.story_director, "set_gm_directive_state"):
                self.story_director.set_gm_directive_state(self.gm_directive_state)

        # Primary mode propagation happens via system.set_mode() above.
        # The direct determinism mutation below is only a fallback for
        # systems that expose a determinism object but do not fully
        # implement their own mode switching.
        # PHASE 5.3 — Propagate replay/live LLM behavior to systems with determinism config
        for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
            system = getattr(self, system_name, None)
            if system is not None and hasattr(system, "determinism"):
                system.determinism.replay_mode = (mode in ("replay", "simulation"))
                if mode in ("replay", "simulation"):
                    system.determinism.use_recorded_llm = True
                    system.determinism.use_recorded_tools = True
                else:
                    system.determinism.use_recorded_llm = False
                    system.determinism.use_recorded_tools = False

        # PHASE 5.5 — Apply effect policy by mode
        if mode == "live":
            self.effect_manager.set_policy(
                EffectPolicy(
                    allow_logs=True,
                    allow_metrics=True,
                    allow_network=True,
                    allow_disk_write=True,
                    allow_live_llm=True,
                    allow_tool_calls=True,
                )
            )
        elif mode in ("replay", "simulation"):
            self.effect_manager.set_policy(
                EffectPolicy(
                    allow_logs=True,
                    allow_metrics=True,
                    allow_network=False,
                    allow_disk_write=False,
                    allow_live_llm=False,
                    allow_tool_calls=False,
                )
            )

    def tick(self, player_input: str) -> Dict[str, Any]:
        """Execute one game tick.

        This is the ONLY tick method that should drive game execution.
        All other loop-like mechanisms have been deprecated.

        Pipeline:
            1. Parse player intent
            2. Pre-tick hooks
            3. Advance world
            4. Update NPCs
            5. Collect and process events
            6. Narrative processing
            7. Render scene
            8. Post-tick hooks

        Uses contextvars for loop tracking, making it safe for:
        - async/multithreading environments
        - multiple sessions in the same process

        Args:
            player_input: Raw player input string.

        Returns:
            The rendered scene dictionary.

        Raises:
            RuntimeError: If multiple GameLoop instances are detected in same context.
        """
        # Check for multiple loops in same context using contextvars
        current = _active_loop_ctx.get()
        if current and current is not self:
            raise RuntimeError("Multiple GameLoop instances detected in same context")

        # Set this loop as active in context
        token = _active_loop_ctx.set(self)

        self._tick_count += 1

        # 1. Parse player intent (with recovery)
        intent, parser_recovery = self._handle_parser_stage(player_input)

        # Build tick context
        ctx = TickContext(
            tick_number=self._tick_count,
            player_input=player_input,
            intent=intent,
        )

        # Pre-tick callback
        if self._on_pre_tick:
            self._on_pre_tick(ctx)

        # Set current tick on event bus for temporal debugging (Fix #4)
        self.event_bus.set_tick(self._tick_count)

        try:
            # PHASE 6.5 FIX: If parser failed, route recovery through renderer + normalizer
            if parser_recovery is not None:
                coherence_context = self._build_director_context()
                rendered = self._handle_renderer_stage(parser_recovery, coherence_context)
                scene = self._finalize_scene_output(rendered, coherence_context)
                ctx.scene = scene
                # Do NOT update last-good anchor from recovery scenes (handled in _is_strong_scene)
                self._maybe_record_last_good_anchor(scene, coherence_context)
                if self._on_post_tick:
                    self._on_post_tick(ctx)
                return scene

            # 2. Advance world simulation
            self.world.tick(self.event_bus)

            # 3. Update NPCs
            if getattr(self, "npc_method", None) is not None:
                self.npc_method(intent)
            else:
                self.npc_system.update(intent, self.event_bus)

            # 4.5 PHASE 7.0 — Emit pending GM inject-event directives BEFORE
            # the tick event list is finalized so coherence sees them in the
            # same reduction pass.
            self._emit_pending_gm_events()

            # 4. Collect events (now with tick IDs injected)
            events = self.event_bus.collect()
            ctx.events = events

            # Process event callbacks
            if self._on_event:
                for event in events:
                    self._on_event(event)

            # 5. Canonical coherence updates
            coherence_result = self._apply_coherence_updates(events)
            coherence_context = self._build_director_context()
            ctx.scene["coherence"] = coherence_result

            # PHASE 7.8: Refresh arc control from coherence + GM state, then
            # merge arc steering context into the director context.
            if hasattr(self, "arc_control_controller") and self.arc_control_controller is not None:
                self.arc_control_controller.refresh_from_state(
                    self.coherence_core, self.gm_directive_state
                )
                arc_ctx = self.arc_control_controller.build_director_context(
                    self.coherence_core
                )
                # Phase 7.8 tightening — defensive copy to avoid shared mutation
                coherence_context = dict(coherence_context)
                coherence_context["arc_control"] = arc_ctx
                # Also push context to story director for guidance
                if hasattr(self.story_director, "set_arc_control_context"):
                    self.story_director.set_arc_control_context(arc_ctx)

            # PHASE 6.5: Check for high-severity contradictions only
            contradiction_scene = self._handle_high_severity_contradictions(
                coherence_result, coherence_context
            )
            if contradiction_scene is not None:
                ctx.scene = contradiction_scene
                if self._on_post_tick:
                    self._on_post_tick(ctx)
                return contradiction_scene

            # 6. Narrative processing (with recovery)
            narrative = self._handle_director_stage(
                events, intent, coherence_context
            )
            if isinstance(narrative, dict) and narrative.get("meta", {}).get("recovered"):
                # PHASE 6.5: Route recovery through renderer + normalization
                rendered = self._handle_renderer_stage(narrative, coherence_context)
                scene = self._finalize_scene_output(rendered, coherence_context)
                ctx.scene = scene
                if self._on_post_tick:
                    self._on_post_tick(ctx)
                return scene

            # 7. Render scene (with recovery)
            scene = self._handle_renderer_stage(narrative, coherence_context)
            scene = self._finalize_scene_output(scene, coherence_context)
            ctx.scene = scene

            # PHASE 6.5: Update last good anchor only for strong (non-recovered) scenes
            self._maybe_record_last_good_anchor(scene, coherence_context)

            # PHASE 2.5: Save snapshot at interval
            if self.snapshot_manager.should_snapshot(self._tick_count):
                self.snapshot_manager.save_snapshot(self)

            # Post-tick callback
            if self._on_post_tick:
                self._on_post_tick(ctx)

            return scene
        finally:
            # PHASE 3 — Advance timeline pointer after successful tick
            # The last event emitted becomes the parent for the next tick
            # (This is handled automatically by EventBus, but we track for API clarity)
            pass

            # Always reset the context to avoid stale references
            _active_loop_ctx.reset(token)

    @property
    def tick_count(self) -> int:
        """Number of ticks processed so far."""
        return self._tick_count

    def on_pre_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a pre-tick callback.

        Args:
            callback: Function called before the tick pipeline runs.
        """
        self._on_pre_tick = callback

    def on_post_tick(self, callback: Callable[[TickContext], None]) -> None:
        """Register a post-tick callback.

        Args:
            callback: Function called after the tick pipeline completes.
        """
        self._on_post_tick = callback

    def on_event(self, callback: Callable[[Event], None]) -> None:
        """Register an event callback.

        This is called for each event during the tick,
        after events are collected but before narrative processing.

        Args:
            callback: Function called for each event.
        """
        self._on_event = callback

    def reset(self) -> None:
        """Reset the loop state (tick count, event bus, callbacks).

        Fix #6: Don't touch context vars here - that breaks nested contexts.
        Context var management is handled by the tick() method's finally block.
        """
        self._tick_count = 0
        self.event_bus.reset()
        self._on_pre_tick = None
        self._on_post_tick = None
        self._on_event = None

    # -------------------------
    # PHASE 4.5 — NPC PLANNER INTEGRATION
    # -------------------------

    def set_npc_planner(
        self,
        npc_planner: Any,
        npc_system: Optional[Any] = None,
    ) -> None:
        """Hook simulation-based NPC planner into the game loop.

        PHASE 4.5: Integrates NPCPlanner for forward-looking NPC decisions.
        NPCs simulate 3-5 futures, score them, and choose the best.

        Args:
            npc_planner: NPCPlanner instance with choose_action() method.
            npc_system: Optional NPC system with get_npcs() method.
                       If None, uses the npc_system passed to __init__.
        """
        self.npc_planner = npc_planner
        self.npc_system_protocol = npc_system

    def get_npc_phase_base_events(self) -> List[Event]:
        """Get event history available for NPC planning decisions.

        PHASE 4.5: Returns events up to the current tick for use as
        base_events in NPC simulation planning.

        Returns:
            List of events up to current tick.
        """
        return self.event_bus.history()

    def enable_planning_phase(
        self,
        npc_planner: Any,
        npc_system: Optional[Any] = None,
    ) -> None:
        """Enable Phase 4.5 NPC planning mode.

        Convenience method that sets up the planner and switches NPC
        phase to use simulation-based decisions.

        Args:
            npc_planner: NPCPlanner instance.
            npc_system: Optional NPC system override.
        """
        self.set_npc_planner(npc_planner, npc_system)
        # Override npc_method to use planner-based NPC phase
        self.npc_method = self._npc_phase_planner

    def _npc_phase_planner(self, intent: Dict[str, Any]) -> None:
        """NPC phase using simulation-based planner.

        Instead of calling npc_system.update(), this method:
        1. Gets base events from history
        2. For each NPC, generates candidate actions
        3. Uses NPCPlanner to choose best action
        4. Emits chosen actions via event bus

        Args:
            intent: Current parsed player intent (passed through for context).
        """
        base_events = self.event_bus.history()
        npc_sys = self.npc_system_protocol or self.npc_system

        # Get all NPCs that support planning
        npcs = []
        if hasattr(npc_sys, "get_npcs"):
            npcs = npc_sys.get_npcs()
        elif hasattr(npc_sys, "npcs"):
            npcs = npc_sys.npcs
        else:
            # Fall back to standard update
            npc_sys.update(intent, self.event_bus)
            return

        for npc in npcs:
            npc_id = getattr(npc, "id", getattr(npc, "npc_id", None))
            if npc_id is None:
                continue

            # Generate candidate actions
            candidate_actions = self._generate_candidates_for_npc(npc, intent)
            if not candidate_actions:
                continue

            # Choose best via planner
            if self.npc_planner:
                context = {
                    "npc": npc_id,
                    "npc_id": npc_id,
                    "intent": intent,
                    "tick": self._tick_count,
                }
                best = self.npc_planner.choose_action(
                    base_events=base_events,
                    candidates=candidate_actions,
                    context=context,
                )
            else:
                best = candidate_actions[0] if candidate_actions else None

            # Emit chosen action
            if best:
                for event in best:
                    self.event_bus.emit(event)

    def _generate_candidates_for_npc(
        self,
        npc: Any,
        intent: Dict[str, Any],
    ) -> List[List[Event]]:
        """Generate candidate action lists for an NPC.

        Uses CandidateGenerator if available, falls back to NPC's own
        generate_candidate_actions() method.

        Args:
            npc: The NPC instance.
            intent: Current player intent.

        Returns:
            List of candidate event lists.
        """
        npc_id = getattr(npc, "id", getattr(npc, "npc_id", "unknown"))

        # Try NPC's own candidate generation first
        if hasattr(npc, "generate_candidate_actions"):
            return npc.generate_candidate_actions()

        # Try using CandidateGenerator from planner module
        try:
            from ..ai.planner import CandidateGenerator

            # Build NPC context
            hp = getattr(npc, "hp", 100)
            npc_context = {
                "npc_id": npc_id,
                "hp": hp,
                "hp_low": hp < 30,
                "has_target": hasattr(npc, "target") and npc.target is not None,
                "can_reach": getattr(npc, "can_reach", False),
                "position": getattr(npc, "position", None),
            }

            generator = CandidateGenerator()
            return generator.generate(npc_context=npc_context)
        except Exception:
            # Fallback: create a simple idle/wander candidate
            return [[Event(
                type="idle",
                payload={"actor": npc_id, "reason": "no_planner_available"},
            )]]

    # -------------------------
    # PHASE 2 — REPLAY / TIME-TRAVEL (PATCHED)
    # -------------------------

    def replay_to_tick(
        self,
        events: List["Event"],
        tick: int,
        loop_factory: Optional[Callable[[], "GameLoop"]] = None,
    ) -> "GameLoop":
        """Replay events up to a specific tick (time-travel debug).

        PHASE 2 — REPLAY ENGINE:
        Creates a fresh GameLoop instance and replays events up to the
        specified tick, enabling time-travel debugging.

        PHASE 2 FIX #2: Accepts a factory for creating fresh system instances.
        If no factory is provided, falls back to reusing current systems
        (this maintains backward compat but is NOT recommended for production).

        Args:
            events: Full event history to replay from.
            tick: Target tick number to replay up to.
            loop_factory: Optional factory that returns a fresh GameLoop.
                         If None, creates loop with current system instances
                         (backward compat only — NOT recommended).

        Returns:
            A new GameLoop instance with state reconstructed from events.
        """
        from .replay_engine import ReplayEngine

        if loop_factory is not None:
            engine = ReplayEngine(loop_factory)
        else:
            raise RuntimeError(
                "replay_to_tick() requires loop_factory for deterministic replay. "
                "Refusing to reuse live systems."
            )

        return engine.replay(events, up_to_tick=tick)

    # -------------------------
    # PHASE 6.0 — COHERENCE CORE
    # -------------------------

    def _apply_coherence_updates(self, events: List[Event]) -> Dict[str, Any]:
        """Reduce tick events into canonical coherence state."""
        if self.coherence_core is None:
            return {"events_applied": 0, "mutations": [], "contradictions": []}
        result = self.coherence_core.apply_events(events)
        return result.to_dict()

    def _callable_accepts_kwarg(self, fn: Any, kwarg_name: str) -> bool:
        """Return True if callable explicitly accepts kwarg or **kwargs.

        This avoids using TypeError fallbacks, which can hide real runtime bugs
        thrown inside the target implementation.
        """
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            return False

        for param in signature.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True

        return kwarg_name in signature.parameters

    def _build_director_context(self) -> Dict[str, Any]:
        """Build coherence-aware context for director/renderer consumers."""
        if self.coherence_core is None:
            return {}
        return {
            "scene_summary": self.coherence_core.get_scene_summary(),
            "active_tensions": self.coherence_core.get_active_tensions(),
            "unresolved_threads": self.coherence_core.get_unresolved_threads(),
            "recent_consequences": self.coherence_core.get_recent_consequences(limit=5),
            "last_good_anchor": self.coherence_core.get_last_good_anchor(),
            "contradictions": [c.to_dict() for c in self.coherence_core.get_state().contradictions[-10:]],
        }

    # -------------------------
    # PHASE 6.5 — RECOVERY LAYER
    # -------------------------

    def _init_recovery_manager(self) -> None:
        """Initialize the recovery manager and register for snapshots."""
        self.recovery_manager = RecoveryManager()
        if "recovery_manager" not in self._snapshot_systems:
            self._snapshot_systems.append("recovery_manager")
        # Inject into story director if it supports it
        if hasattr(self.story_director, "set_recovery_manager"):
            self.story_director.set_recovery_manager(self.recovery_manager)

    def _normalize_scene(self, scene: dict | None) -> dict:
        """Normalize a scene dict to a consistent shape.

        Ensures all scenes have canonical keys regardless of source.

        Precedence rules are intentional:
        - root-level keys from the renderer/output scene are authoritative
        - nested narrative keys only backfill missing values
        - `meta` is canonical; `metadata` is kept as a compatibility mirror
        """
        scene = scene or {}
        if not isinstance(scene, dict):
            return {
                "scene": str(scene),
                "options": [],
                "meta": {},
            }

        # If the scene is wrapped in a 'narrative' key (e.g., by renderer),
        # extract the nested payload for backfill only. Root scene keys remain
        # authoritative wherever present.
        narrative_wrapper = scene.get("narrative")
        payload = narrative_wrapper if isinstance(narrative_wrapper, dict) else scene

        # Root scene keys are authoritative; nested narrative only backfills.
        body = (
            scene.get("body")
            or scene.get("scene")
            or scene.get("text")
            or scene.get("description")
            or payload.get("body")
            or payload.get("scene")
            or payload.get("text")
            or payload.get("description")
            or ""
        )

        # Root meta is canonical; nested payload only fills missing keys.
        payload_meta = payload.get("meta", {}) or {}
        payload_metadata = payload.get("metadata", {}) or {}
        scene_meta = scene.get("meta", {}) or {}
        scene_metadata = scene.get("metadata", {}) or {}

        meta = {**payload_meta, **scene_meta}
        metadata = {**payload_metadata, **scene_metadata}

        # Keep metadata synchronized for compatibility, but `meta` remains
        # the canonical place to read recovery flags.
        if "recovered" in meta and "recovered" not in metadata:
            metadata["recovered"] = meta["recovered"]
        if "recovery_reason" in meta and "recovery_reason" not in metadata:
            metadata["recovery_reason"] = meta["recovery_reason"]
        if "recovery_policy" in meta and "recovery_policy" not in metadata:
            metadata["recovery_policy"] = meta["recovery_policy"]

        # Extract options
        options = scene.get("options", []) or payload.get("options", []) or []

        normalized = {
            "scene": body,
            "body": body,
            "options": options,
            "meta": meta,
            "metadata": metadata,
        }

        # Preserve other keys from both payload and scene
        for key in ("title", "summary", "status", "prompt", "scene_data"):
            if key in payload and key not in normalized:
                normalized[key] = payload[key]
            elif key in scene and key not in normalized:
                normalized[key] = scene[key]

        # Keep narrative key if present
        if "narrative" in scene:
            normalized["narrative"] = scene["narrative"]

        return normalized

    def _finalize_scene_output(self, scene: dict, coherence_context: dict | None = None) -> dict:
        """Normalize and finalize a scene for output.

        Single final step applied to all scene outputs regardless of source.
        """
        scene = self._normalize_scene(scene)
        if coherence_context:
            scene.setdefault("meta", {})
            scene["meta"].setdefault("coherence_available", True)
        return scene

    def _is_strong_scene(self, scene: dict) -> bool:
        """Determine if a scene is strong enough to become a last-good anchor.

        Recovered or degraded scenes are NOT considered strong.
        """
        if not isinstance(scene, dict):
            return False
        meta = scene.get("meta", {})
        # Check both meta and metadata keys for backwards compatibility
        if meta.get("recovered") or meta.get("degraded"):
            return False
        metadata = scene.get("metadata", {})
        if metadata.get("recovered") or metadata.get("degraded"):
            return False
        return bool(scene.get("scene") or scene.get("body"))

    def _handle_parser_stage(self, player_input: str) -> tuple:
        """Parse player input with recovery on failure.

        Returns:
            (intent_dict, recovery_scene_or_None)
        """
        coherence_context = self._build_director_context()
        try:
            intent = self.intent_parser.parse(player_input)
        except Exception as exc:
            result = self.recovery_manager.handle_parser_failure(
                player_input=player_input,
                error=exc,
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return {}, result.scene

        # Check for ambiguity signal in parser result
        if isinstance(intent, dict) and intent.get("ambiguous"):
            result = self.recovery_manager.handle_ambiguity(
                player_input=player_input,
                parser_result=intent,
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return intent, result.scene

        return intent, None

    def _handle_director_stage(
        self,
        events: List[Event],
        intent: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run the director stage with recovery on failure."""
        try:
            if self._callable_accepts_kwarg(self.story_director.process, "coherence_context"):
                narrative = self.story_director.process(
                    events, intent, self.event_bus, coherence_context=coherence_context
                )
            else:
                narrative = self.story_director.process(events, intent, self.event_bus)
        except Exception as exc:
            result = self.recovery_manager.handle_director_failure(
                player_input=intent.get("text", ""),
                error=exc,
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return result.scene

        # Guard against empty / malformed director output
        if not narrative or (isinstance(narrative, dict) and not narrative):
            result = self.recovery_manager.handle_director_failure(
                player_input=intent.get("text", ""),
                error="Director returned empty output",
                coherence_summary=coherence_context,
                tick=self._tick_count,
            )
            return result.scene

        return narrative

    def _handle_renderer_stage(
        self,
        narrative: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run the renderer stage with recovery on failure."""
        try:
            if self._callable_accepts_kwarg(self.scene_renderer.render, "coherence_context"):
                scene = self.scene_renderer.render(narrative, coherence_context=coherence_context)
            else:
                scene = self.scene_renderer.render(narrative)
        except Exception as exc:
            result = self.recovery_manager.handle_renderer_failure(
                player_input="",
                error=exc,
                coherence_summary=coherence_context,
                partial_narrative=narrative if isinstance(narrative, dict) else None,
                tick=self._tick_count,
            )
            return result.scene
        return scene

    def _handle_high_severity_contradictions(
        self,
        coherence_result: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """If high-severity contradictions exist, produce a recovery scene.

        Only triggers recovery for high/critical severity contradictions.
        Info and warning contradictions remain visible in state but are
        not player-facing by default.
        """
        contradictions = coherence_result.get("contradictions", [])
        if not contradictions:
            return None
        if not self.recovery_manager._has_high_severity_contradiction(contradictions):
            return None
        result = self.recovery_manager.handle_contradiction(
            contradictions=contradictions,
            coherence_summary=coherence_context,
            tick=self._tick_count,
        )
        return self._finalize_scene_output(result.scene, coherence_context)

    def _maybe_record_last_good_anchor(
        self,
        scene: Dict[str, Any],
        coherence_context: Dict[str, Any],
    ) -> None:
        """After a successful render, update the last-good anchor.

        Only strong (non-recovered, non-degraded) scenes qualify as anchors.
        """
        if not self._is_strong_scene(scene):
            return
        anchor = coherence_context.get("last_good_anchor")
        if not anchor:
            scene_summary = coherence_context.get("scene_summary")
            if (
                isinstance(scene_summary, dict)
                and (
                    scene_summary.get("location")
                    or scene_summary.get("summary")
                    or scene_summary.get("present_actors")
                )
            ):
                anchor = scene_summary
        if anchor:
            self.recovery_manager.record_last_good_anchor(anchor)

    # -------------------------
    # PHASE 7.0 — CREATOR / GM
    # -------------------------

    def _init_creator_systems(self) -> None:
        from ..creator import (
            CreatorCanonState,
            GMDirectiveState,
            RecapBuilder,
            StartupGenerationPipeline,
            GMCommandProcessor,
        )
        from ..creator.presenters import CreatorStatePresenter

        self.creator_canon_state = CreatorCanonState()
        self.gm_directive_state = GMDirectiveState()
        self.recap_builder = RecapBuilder()
        self.gm_command_processor = GMCommandProcessor()
        self.creator_presenter = CreatorStatePresenter()
        self.startup_generation_pipeline = StartupGenerationPipeline(
            llm_gateway=self.llm_gateway if hasattr(self, "llm_gateway") else None,
            coherence_core=self.coherence_core,
            creator_canon_state=self.creator_canon_state,
        )

        for system_name in ("creator_canon_state", "gm_directive_state"):
            if system_name not in self._snapshot_systems:
                self._snapshot_systems.append(system_name)

        if hasattr(self.story_director, "set_creator_canon_state"):
            self.story_director.set_creator_canon_state(self.creator_canon_state)
        if hasattr(self.story_director, "set_gm_directive_state"):
            self.story_director.set_gm_directive_state(self.gm_directive_state)

    def _emit_pending_gm_events(self) -> None:
        """Emit active GM inject-event directives into the EventBus deterministically.

        This pass is intentionally simple:
        - only inject-event directives are emitted
        - scene-scoped directives are cleared only after successful emission
        - emission happens through the normal EventBus path so downstream
          coherence/director consumers see standard events
        """
        if not hasattr(self, "gm_directive_state") or self.gm_directive_state is None:
            return

        pending = self.gm_directive_state.get_pending_injected_events()
        if not pending:
            return

        emitted_scene_scoped_ids: list[str] = []

        for item in pending:
            directive_id = item.get("directive_id")
            scope = item.get("scope")
            event_type = item.get("event_type")
            payload = dict(item.get("payload", {}) or {})

            if not event_type:
                continue

            self.event_bus.emit(
                Event(
                    event_type,
                    payload,
                    source="gm_directive",
                )
            )

            if scope == "scene" and directive_id:
                emitted_scene_scoped_ids.append(directive_id)

        # Remove only those scene-scoped directives that were actually emitted.
        if emitted_scene_scoped_ids:
            self.gm_directive_state.remove_directives(emitted_scene_scoped_ids)

    def start_new_adventure(self, setup_data: dict) -> dict:
        from ..creator import AdventureSetup

        setup = AdventureSetup.from_dict(setup_data)
        setup.validate()

        generated = self.startup_generation_pipeline.generate(setup)
        # Canon is applied once here after the pipeline has populated creator state.
        self.apply_creator_canon()
        self.apply_gm_directives()
        return {
            "ok": True,
            "setup": setup.to_dict(),
            "generated": generated,
            "canon_summary": self.get_canon_summary(),
        }

    def apply_creator_canon(self) -> None:
        self.creator_canon_state.apply_to_coherence(self.coherence_core)

    def apply_gm_directives(self) -> None:
        self.gm_directive_state.apply_to_coherence(self.coherence_core)

    def build_creator_context(self) -> dict:
        return {
            "canon": self.creator_canon_state.serialize_state(),
            "gm": self.gm_directive_state.build_director_context(),
        }

    def get_recap(self) -> dict:
        return self.recap_builder.build_session_recap(self.coherence_core, self.gm_directive_state)

    def get_canon_summary(self) -> dict:
        return self.recap_builder.build_canon_summary(self.coherence_core, self.creator_canon_state)

    def get_unresolved_threads_summary(self) -> dict:
        return self.recap_builder.build_unresolved_threads_summary(self.coherence_core)

    # ------------------------------------------------------------------
    # Phase 7.1 — validation / preview helpers
    # ------------------------------------------------------------------

    def validate_new_adventure(self, setup_data: dict) -> dict:
        from ..creator.validation import validate_adventure_setup_payload
        result = validate_adventure_setup_payload(setup_data)
        return result.to_dict()

    def prepare_new_adventure(self, setup_data: dict) -> dict:
        from ..creator import AdventureSetup
        from ..creator.defaults import apply_adventure_defaults
        from ..creator.validation import validate_adventure_setup_payload

        data = apply_adventure_defaults(dict(setup_data))
        validation = validate_adventure_setup_payload(data)
        if validation.is_blocking():
            return {
                "ok": False,
                "validation": validation.to_dict(),
            }

        setup = AdventureSetup.from_dict(data).normalize().with_defaults()
        return {
            "ok": True,
            "validation": validation.to_dict(),
            "preview": self.creator_presenter.present_setup_summary(setup),
        }

    # ------------------------------------------------------------------
    # Phase 7.3 — Scene Execution Layer
    # ------------------------------------------------------------------

    def _init_execution_systems(self) -> None:
        """Initialize the action resolver for scene execution."""
        from ..control.controller import GameplayControlController
        from ..group_dynamics.group_engine import GroupDynamicsEngine
        from ..npc_agency.agency_engine import NPCAgencyEngine
        agency_engine = NPCAgencyEngine(
            group_dynamics_engine=GroupDynamicsEngine(),
        )
        # Phase 8.1 — Dialogue planning layer
        self.dialogue_core = DialogueCore()
        self.action_resolver = ActionResolver(
            npc_agency_engine=agency_engine,
            dialogue_core=self.dialogue_core,
        )
        self.npc_agency_engine = agency_engine
        self.last_dialogue_response: dict | None = None
        # GameplayControlController is already initialized by _init_creator_systems
        # via build_control_output. We create one for direct option lookup.
        if not hasattr(self, "gameplay_control_controller"):
            self.gameplay_control_controller = GameplayControlController()

    def get_last_choice_set(self) -> dict | None:
        """Return the last presented choice set, if any."""
        if hasattr(self, "gameplay_control_controller"):
            return self.gameplay_control_controller.get_last_choice_set()
        return None

    def resolve_selected_option(self, option_id: str) -> dict:
        """Resolve a selected option into events and update coherence + social state.

        This is the main entry point for the scene execution layer.
        It resolves the option, emits events, and applies both coherence
        and social state updates through their respective event/reducer paths.

        Phase 8.2: Also handles encounter start, resolution, and journaling.
        """
        option = self.gameplay_control_controller.select_option(option_id)
        if option is None:
            return {"ok": False, "reason": "unknown_option", "option_id": option_id}

        # Capture scene_summary at resolution time to avoid drift during logging
        scene_summary = (
            self.coherence_core.get_scene_summary() if self.coherence_core else {}
        )

        # Phase 8.2 — explicit-only encounter start
        option_meta = (
            option.get("metadata", {})
            if isinstance(option, dict)
            else getattr(option, "metadata", {})
        ) or {}
        enc_start_mode = None
        if isinstance(option_meta, dict):
            raw_mode = option_meta.get("encounter_start")
            if isinstance(raw_mode, str) and raw_mode.strip():
                enc_start_mode = raw_mode.strip().lower()

        if enc_start_mode and not self.encounter_controller.has_active_encounter():
            participants = self._build_encounter_participants(scene_summary)
            self.encounter_controller.start_encounter(
                mode=enc_start_mode,
                scene_summary=scene_summary,
                participants=participants,
                active_entity_id="player",
                metadata={
                    "started_from_option_id": option.get("option_id")
                    if isinstance(option, dict)
                    else getattr(option, "option_id", None),
                },
                tick=self._tick_count,
            )

        result = self.action_resolver.resolve_choice(
            option=option,
            coherence_core=self.coherence_core,
            gm_state=self.gm_directive_state,
            social_state_core=self.social_state_core,
            arc_control_controller=getattr(self, "arc_control_controller", None),
            campaign_memory_core=getattr(self, "campaign_memory_core", None),
            scene_summary=scene_summary,
            tick=self._tick_count,
        )

        result_dict = result.to_dict()
        self._emit_action_resolution_events(result_dict)

        # Phase 7.6 tightening — ensure identical event ordering for coherence and social state
        raw_events = result_dict.get("events", [])
        if raw_events:
            if self.coherence_core is not None:
                self.coherence_core.apply_events(raw_events)
            if self.social_state_core is not None:
                self.social_state_core.apply_events(raw_events)

        # Phase 8.2 — encounter resolution
        self.last_encounter_resolution = None
        if self.encounter_controller.has_active_encounter():
            resolved_action = result_dict.get("resolved_action", {})
            enc_resolution = self.encounter_resolver.resolve_action(
                encounter_state=self.encounter_controller.get_active_encounter(),
                resolved_action=resolved_action,
                scene_summary=scene_summary,
                coherence_core=self.coherence_core,
                social_state_core=self.social_state_core,
                arc_control_controller=getattr(self, "arc_control_controller", None),
                tick=self._tick_count,
            )
            if enc_resolution is not None:
                self.encounter_controller.apply_resolution(enc_resolution)
                self.last_encounter_resolution = enc_resolution.to_dict()

                # Journal meaningful encounter events
                journal_payload = self.encounter_presenter.present_journal_payload(
                    enc_resolution,
                    self.encounter_controller.get_active_encounter(),
                )
                if (
                    journal_payload
                    and hasattr(self, "campaign_memory_core")
                    and self.campaign_memory_core is not None
                ):
                    self.campaign_memory_core.record_encounter_log_entry(
                        encounter_log=journal_payload,
                        tick=self._tick_count,
                        location=scene_summary.get("location"),
                    )

        # Phase 7.7 — record journal entries and refresh memory panels
        # Fix 6: only refresh recap/snapshot when there are meaningful events
        if hasattr(self, "campaign_memory_core") and self.campaign_memory_core is not None:
            self.campaign_memory_core.record_action_resolution(
                resolution=result_dict,
                coherence_core=self.coherence_core,
                social_state_core=self.social_state_core,
                tick=self._tick_count,
            )
            if result_dict.get("events"):
                self.campaign_memory_core.refresh_recap(
                    coherence_core=self.coherence_core,
                    social_state_core=self.social_state_core,
                    creator_canon_state=getattr(self, "creator_canon_state", None),
                    tick=self._tick_count,
                )
                self.campaign_memory_core.refresh_campaign_snapshot(
                    coherence_core=self.coherence_core,
                    social_state_core=self.social_state_core,
                    creator_canon_state=getattr(self, "creator_canon_state", None),
                    tick=self._tick_count,
                )

        # Phase 8.1 — Store latest dialogue response for UX surface
        resolved_meta = result_dict.get("resolved_action", {}).get("metadata", {})
        if resolved_meta.get("dialogue_response"):
            self.last_dialogue_response = resolved_meta["dialogue_response"]
        else:
            self.last_dialogue_response = None

        # Phase 8.1 — Record dialogue log entry into journal if meaningful
        # Use the same scene_summary captured at resolution time to avoid drift
        dialogue_log = resolved_meta.get("dialogue_log_entry")
        if (
            dialogue_log
            and hasattr(self, "campaign_memory_core")
            and self.campaign_memory_core is not None
        ):
            self.campaign_memory_core.record_dialogue_log_entry(
                dialogue_log=dialogue_log,
                tick=self._tick_count,
                location=scene_summary.get("location"),
            )

        # Phase 8.3 — Advance world simulation after all authoritative updates.
        # NOTE: world sim produces overlay summaries/effects only; it is not
        # a direct mutator of canonical coherence/social/memory truth.
        self.last_world_sim_result = None
        if hasattr(self, "world_sim_controller") and self.world_sim_controller is not None:
            world_result = self.world_sim_controller.advance(
                coherence_core=self.coherence_core,
                social_state_core=self.social_state_core,
                arc_control_controller=getattr(self, "arc_control_controller", None),
                campaign_memory_core=getattr(self, "campaign_memory_core", None),
                encounter_controller=getattr(self, "encounter_controller", None),
                tick=self._tick_count,
            )
            self.last_world_sim_result = world_result.to_dict()

            # Journal meaningful world simulation effects
            if (
                world_result.journal_payloads
                and hasattr(self, "campaign_memory_core")
                and self.campaign_memory_core is not None
            ):
                for journal_effect in world_result.journal_payloads:
                    self.campaign_memory_core.record_world_sim_log_entry(
                        world_effect=journal_effect,
                        tick=self._tick_count,
                        location=scene_summary.get("location"),
                    )

        return {
            "ok": True,
            "resolution": result_dict,
            "scene_summary": scene_summary,
        }

    def _build_encounter_participants(self, scene_summary: dict) -> list[dict]:
        """Build participant dicts from scene_summary for encounter start."""
        participants: list[dict] = [{"entity_id": "player", "role": "player"}]
        present_actors = scene_summary.get("present_actors", [])
        for actor in present_actors:
            if isinstance(actor, str) and actor != "player":
                participants.append({"entity_id": actor, "role": "neutral"})
            elif isinstance(actor, dict):
                eid = actor.get("entity_id", actor.get("id", ""))
                if eid and eid != "player":
                    participants.append({
                        "entity_id": eid,
                        "role": actor.get("role", "neutral"),
                    })
        return participants

    def _emit_action_resolution_events(self, result: dict) -> None:
        """Emit resolved action events into the EventBus."""
        from .event_bus import Event
        for event_data in result.get("events", []):
            self.event_bus.emit(
                Event(
                    type=event_data.get("type", "unknown"),
                    payload=dict(event_data.get("payload", {})),
                    source="action_resolver",
                )
            )


    # ------------------------------------------------------------------
    # Phase 7.6 — Social State Dashboard / Query
    # ------------------------------------------------------------------

    def get_social_dashboard(self) -> dict:
        """Return a presenter-shaped social state dashboard."""
        if self.social_state_core is None:
            return {"title": "Social State", "relationships": [], "rumors": [], "alliances": []}
        state = self.social_state_core.get_state()
        return {
            "title": "Social State",
            "relationships": [r.to_dict() for r in state.relationships.values()],
            "rumors": [r.to_dict() for r in state.rumors.values()],
            "alliances": [a.to_dict() for a in state.alliances.values()],
        }

    def get_npc_social_view(self, npc_id: str, target_id: str | None = None) -> dict:
        """Return a social view for a specific NPC."""
        if self.social_state_core is None:
            return {
                "npc_id": npc_id,
                "target_id": target_id,
                "relationship": None,
                "reputation": None,
                "active_rumors": [],
            }
        query = self.social_state_core.get_query()
        state = self.social_state_core.get_state()
        return query.build_npc_social_view(state, npc_id, target_id)

    # ------------------------------------------------------------------
    # Phase 7.7 — Memory / Read-Model Panels
    # ------------------------------------------------------------------

    def get_journal_panel(self) -> dict:
        """Return a presenter-shaped journal panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Journal", "items": [], "count": 0}
        entries = [e.to_dict() for e in self.campaign_memory_core.journal_entries]
        return self.memory_presenter.present_journal_entries(entries)

    def get_recap_panel(self) -> dict:
        """Return a presenter-shaped recap panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Recap", "summary": "", "scene_summary": {}, "active_threads": [], "recent_consequences": [], "social_highlights": []}
        recap = self.campaign_memory_core.last_recap
        if recap is None:
            return {"title": "Recap", "summary": "", "scene_summary": {}, "active_threads": [], "recent_consequences": [], "social_highlights": []}
        return self.memory_presenter.present_recap(recap.to_dict())

    def get_codex_panel(self) -> dict:
        """Return a presenter-shaped codex panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Codex", "items": [], "count": 0}
        entries = [e.to_dict() for e in self.campaign_memory_core.codex_entries.values()]
        return self.memory_presenter.present_codex(entries)

    def get_campaign_memory_panel(self) -> dict:
        """Return a presenter-shaped campaign memory panel."""
        if not hasattr(self, "campaign_memory_core") or self.campaign_memory_core is None:
            return {"title": "Campaign Memory", "current_scene": {}, "active_threads": [], "resolved_threads": [], "major_consequences": [], "social_summary": {}, "canon_summary": {}}
        snapshot = self.campaign_memory_core.last_campaign_snapshot
        if snapshot is None:
            return {"title": "Campaign Memory", "current_scene": {}, "active_threads": [], "resolved_threads": [], "major_consequences": [], "social_summary": {}, "canon_summary": {}}
        return self.memory_presenter.present_campaign_memory(snapshot.to_dict())

    # ------------------------------------------------------------------
    # Phase 7.8 — Arc Control Panels
    # ------------------------------------------------------------------

    def get_arc_panel(self) -> dict:
        """Return a presenter-shaped arc panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Arcs", "items": [], "count": 0}
        return self.arc_control_presenter.present_arc_panel(self.arc_control_controller)

    def get_reveal_panel(self) -> dict:
        """Return a presenter-shaped reveal panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Reveals", "items": [], "count": 0}
        return self.arc_control_presenter.present_reveal_panel(self.arc_control_controller)

    def get_pacing_plan_panel(self) -> dict:
        """Return a presenter-shaped pacing-plan panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Pacing Plan", "items": [], "count": 0}
        return self.arc_control_presenter.present_pacing_plan_panel(self.arc_control_controller)

    def get_scene_bias_panel(self) -> dict:
        """Return a presenter-shaped scene-bias panel."""
        if not hasattr(self, "arc_control_controller") or self.arc_control_controller is None:
            return {"title": "Scene Bias", "items": [], "count": 0}
        return self.arc_control_presenter.present_scene_bias_panel(self.arc_control_controller)

    # ------------------------------------------------------------------
    # Phase 7.9 — Adventure Pack Operations
    # ------------------------------------------------------------------

    def register_pack(self, pack_data: dict) -> dict:
        """Deserialize, validate, and register an adventure pack.

        Returns a presenter-shaped result with validation and pack info.
        """
        pack = AdventurePack.from_dict(pack_data)
        validation = self.pack_validator.validate(pack)
        validation_dict = validation.to_dict()
        presented_validation = self.pack_presenter.present_validation_result(validation_dict)

        if validation.is_blocking():
            return {
                "ok": False,
                "validation": presented_validation,
            }

        self.pack_registry.register(pack)
        return {
            "ok": True,
            "validation": presented_validation,
            "pack": self.pack_presenter.present_pack(pack.to_dict()),
        }

    def list_registered_packs(self) -> dict:
        """Return a presenter-shaped list of all registered packs."""
        packs = self.pack_registry.list_packs()
        return self.pack_presenter.present_pack_list([p.to_dict() for p in packs])

    def load_registered_packs(self, pack_ids: list[str]) -> dict:
        """Load specified registered packs and return a structured seed payload.

        Does not mutate game state — returns a translation payload only.
        """
        packs: list[AdventurePack] = []
        missing: list[str] = []
        for pack_id in pack_ids:
            pack = self.pack_registry.get(pack_id)
            if pack is None:
                missing.append(pack_id)
            else:
                packs.append(pack)

        if missing:
            return {"ok": False, "reason": "missing_packs", "missing": missing}

        payload = self.pack_loader.load_many(packs)
        return {
            "ok": True,
            "payload": payload,
            "presented": self.pack_presenter.present_load_result(payload),
        }

    def merge_registered_packs(self, pack_ids: list[str]) -> dict:
        """Merge specified registered packs and return the merged pack.

        Does not register the merged result — callers can register it
        separately if desired.
        """
        packs: list[AdventurePack] = []
        missing: list[str] = []
        for pack_id in pack_ids:
            pack = self.pack_registry.get(pack_id)
            if pack is None:
                missing.append(pack_id)
            else:
                packs.append(pack)

        if missing:
            return {"ok": False, "reason": "missing_packs", "missing": missing}

        try:
            merged = self.pack_merger.merge(packs)
        except Exception as exc:
            return {"ok": False, "reason": "merge_conflict", "error": str(exc)}

        return {
            "ok": True,
            "pack": self.pack_presenter.present_pack(merged.to_dict()),
            "pack_data": merged.to_dict(),
        }

    def export_current_setup_as_pack(self, title: str, version: str, pack_id: str) -> dict:
        """Export current creator/GM state as an adventure pack."""
        creator_state = getattr(self, "creator_canon_state", None)
        pack = self.pack_exporter.export_from_creator_state(
            creator_canon_state=creator_state,
            title=title,
            version=version,
            pack_id=pack_id,
        )
        return {
            "ok": True,
            "pack": self.pack_presenter.present_pack(pack.to_dict()),
            "pack_data": pack.to_dict(),
        }

    def apply_pack_seed(self, payload: dict) -> dict:
        """Apply a seed payload from pack loading into existing systems.

        Seeds flow through the canonical systems:
        - creator canon (creator_seed)
        - arc control (arc_seed)
        - social state (social_seed)
        - memory/codex (memory_seed)
        """
        pack_id = payload.get("pack_id")
        if pack_id and pack_id in self._applied_pack_ids:
            return {"ok": True, "skipped": True}

        applied: list[str] = []

        # Creator seed — apply facts and content to creator canon
        creator_seed = payload.get("creator_seed", {})
        if creator_seed and hasattr(self, "creator_canon_state"):
            canon = self.creator_canon_state
            if hasattr(canon, "load_pack_seed"):
                canon.load_pack_seed(creator_seed)
                applied.append("creator_seed")

        # Arc seed — apply arc/reveal/pacing seeds to arc control
        arc_seed = payload.get("arc_seed", {})
        if arc_seed and hasattr(self, "arc_control_controller"):
            controller = self.arc_control_controller
            if hasattr(controller, "load_arc_seed"):
                controller.load_arc_seed(arc_seed)
                applied.append("arc_seed")

        # Social seed — apply social seeds to social state
        social_seed = payload.get("social_seed", {})
        if social_seed and hasattr(self, "social_state_core"):
            core = self.social_state_core
            if hasattr(core, "load_social_seed"):
                core.load_social_seed(social_seed)
                applied.append("social_seed")

        # Memory seed — apply memory seeds to campaign memory
        memory_seed = payload.get("memory_seed", {})
        if memory_seed and hasattr(self, "campaign_memory_core"):
            core = self.campaign_memory_core
            if hasattr(core, "load_memory_seed"):
                core.load_memory_seed(memory_seed)
                applied.append("memory_seed")

        if pack_id:
            self._applied_pack_ids.add(pack_id)

        return {
            "ok": True,
            "applied": applied,
        }
