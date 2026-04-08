"""Player Loop — STEP 5 of RPG Design Implementation.

This module implements the PlayerLoop, which ties together all narrative
systems into the main game loop for player-driven gameplay.

Purpose:
    Implement the "missing link" — the main game loop that connects
    player input, world simulation, and narrative generation into
    a coherent play experience.

Architecture:
    Player Input → World Tick → Event Conversion → Scene Update → Narration

Pipeline:
    1. Inject player action into world
    2. Run world_simulation.tick()
    3. Convert raw events to NarrativeEvents
    4. Select focus events (most important)
    5. Update scene with focus events
    6. Generate narrative from scene + events

Usage:
    loop = PlayerLoop(world, director, scene_manager, narrator)
    result = loop.step("I attack the guard")
    print(result["narration"])

Design Compliance:
    - STEP 5: Player Loop from rpg-design.txt
    - Orchestrates all other narrative systems
    - Pure function: input → output, no side effects beyond world state
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# TIER 10: Autonomous NPC Agent System
from rpg.agent.agent_system import AgentSystem
from rpg.character.character_engine import CharacterEngine
from rpg.memory.narrative_memory import NarrativeMemory
from rpg.narrative.ai_director import AIDirector
from rpg.narrative.narrative_event import NarrativeEvent
from rpg.narrative.pacing_controller import PacingController
from rpg.player.agency_system import AgencySystem
from rpg.story.dynamic_quest_generator import DynamicQuestGenerator
from rpg.story.narrative_renderer import NarrativeRenderer

# TIER 6: Narrative Intelligence Systems
from rpg.story.plot_engine import PlotEngine

# TIER 9: Narrative Intelligence Layer
from rpg.story.scene_engine import SceneEngine
from rpg.story.story_arc_engine import StoryArcEngine

# TIER 8: World Complexity Layer
from rpg.world.economy_system import EconomySystem

# TIER 7: Faction Simulation + Reputation Economy
from rpg.world.faction_system import FactionSystem
from rpg.world.political_system import PoliticalSystem
from rpg.world.reputation_engine import ReputationEngine


class PlayerLoop:
    """Main game loop connecting player input to narrative output.
    
    The PlayerLoop orchestrates:
    1. Player action injection
    2. World simulation
    3. Event-to-narrative conversion
    4. Scene management
    5. Narrative generation
    
    It bridges the gap between the simulation engine and the
    storytelling layer, providing the core play experience.
    
    Attributes:
        world: World simulation or state object.
        director: NarrativeDirector for event conversion and scoring.
        scene_manager: SceneManager for scene tracking.
        narrator: Callable for narrative generation. Can be a
                  NarrativeGenerator, NarratorAgent, or any callable
                  that takes events and context and returns text.
    """
    
    def __init__(
        self,
        world: Any = None,
        director: Any = None,
        scene_manager: Any = None,
        narrator: Any = None,
        simulate_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        ai_director: Any = None,
        dialogue_engine: Any = None,
        pacing_controller: Any = None,
        plot_engine: Any = None,
        agency_system: Any = None,
        # TIER 7: Faction Simulation + Reputation Economy
        faction_system: Any = None,
        reputation_engine: Any = None,
        # TIER 8: World Complexity Layer
        economy_system: Any = None,
        political_system: Any = None,
        quest_generator: Any = None,
        # TIER 9: Narrative Intelligence Layer
        scene_engine: Any = None,
        character_engine: Any = None,
        narrative_memory: Any = None,
        story_arc_engine: Any = None,
        narrative_renderer: Any = None,
        # TIER 10: Autonomous NPC Agent System
        agent_system: Any = None,
    ):
        """Initialize the PlayerLoop.
        
        Args:
            world: WorldState or simulation object. If None, simulate_fn
                   must be provided.
            director: NarrativeDirector or equivalent with convert_events()
                      and select_focus_events() methods.
            scene_manager: SceneManager for tracking scene context.
            narrator: Callable or object with generate(event_list, context)
                      method. If callable, should take events+context.
            simulate_fn: Optional custom world tick function. Signature:
                         simulate_fn() -> list_of_event_dicts.
            ai_director: AIDirector for tension-based event shaping.
            dialogue_engine: DialogueEngine for belief-driven dialogue.
            pacing_controller: PacingController for output length control.
            plot_engine: PlotEngine for long-term narrative structure.
            agency_system: AgencySystem for player choice tracking.
            faction_system: FactionSystem for faction simulation.
            reputation_engine: ReputationEngine for faction reputation.
            agent_system: AgentSystem for autonomous NPC actions.
        """
        self.world = world
        self.director = director
        self.scene_manager = scene_manager
        self.narrator = narrator
        self.simulate_fn = simulate_fn
        self._last_result: Dict[str, Any] = {}
        
        # TIER 5: Experience Orchestration
        self.ai_director = ai_director or AIDirector()
        self.dialogue_engine = dialogue_engine
        self.pacing_controller = pacing_controller or PacingController()
        
        # TIER 6: Narrative Intelligence Systems
        self.plot_engine = plot_engine or PlotEngine()
        self.agency = agency_system or AgencySystem()
        
        # TIER 7: Faction Simulation + Reputation Economy
        self.factions = faction_system or FactionSystem()
        self.reputation = reputation_engine or ReputationEngine()
        
        # TIER 8: World Complexity Layer
        self.economy = economy_system or EconomySystem()
        self.politics = political_system or PoliticalSystem()
        self.quest_gen = quest_generator or DynamicQuestGenerator()
        
        # TIER 9: Narrative Intelligence Layer
        self.scenes = scene_engine or SceneEngine()
        self.characters = character_engine or CharacterEngine()
        self.memory = narrative_memory or NarrativeMemory()
        self.story_arcs = story_arc_engine or StoryArcEngine()
        self.renderer = narrative_renderer or NarrativeRenderer()
        
        # TIER 10: Autonomous NPC Agent System
        self.agents = agent_system or AgentSystem()
        
        self._tick = 0
        
    def step(self, player_input: str) -> Dict[str, Any]:
        """Execute one complete game loop step.
        
        This is the main entry point. Takes player input and returns
        narrative output.
        
        Pipeline:
        1. Convert player input to world event
        2. Inject player event into world
        3. Run world simulation tick
        4. Convert raw events to narrative events
        5. Select focus events for narration
        6. TIER 5: AI Director shapes events based on tension
        7. Update scene
        8. Generate narrative
        9. TIER 5: Pacing Controller adjusts output length
        
        Args:
            player_input: Raw text input from the player (e.g., "I attack").
            
        Returns:
            Result dict with keys:
            - narration: Generated narrative text
            - events: List of focus NarrativeEvents
            - scene_context: Current scene context
            - raw_events: Raw world events from simulation
        """
        # 1. Convert player input to world event
        player_event = self._convert_input(player_input)
        
        # 2. Inject player action into world
        if self.world:
            self._inject_player_event(player_event)
        
        # 3. Run world simulation tick
        world_events = self._simulate_tick()
        
        # Add player event to world events for context
        world_events.insert(0, player_event)
        
        # TIER 6: Record player agency (after world tick for result)
        result = {"effects": {}, "weight": 0.5}
        self.agency.record(player_input, result, timestamp=self._tick)
        
        # TIER 7: Apply reputation changes from action
        self.reputation.apply_action(player_input, result, tick=self._tick)
        
        self._tick += 1
        
        # TIER 6: Update plot engine with world events and agency flags
        plot_update = self.plot_engine.update(world_events, self.agency.flags)
        
        # TIER 6: Inject arc-driven events into the event stream
        arc_events = plot_update.get("injected_events", [])
        world_events.extend(arc_events)
        
        # TIER 7: Faction simulation tick (world evolves without player)
        faction_events = self.factions.update()
        world_events.extend(faction_events)
        
        # TIER 7: Update faction relations based on player reputation
        self._update_faction_relations()
        
        # TIER 8: Economy simulation tick
        economy_events = self.economy.update()
        world_events.extend(economy_events)
        
        # TIER 8: Political simulation tick
        political_events = self.politics.update(self.factions)
        world_events.extend(political_events)
        
        # TIER 8: Generate dynamic quests from world state
        new_quests = self.quest_gen.generate(
            self.factions,
            self.economy,
            political_events,
        )
        for quest in new_quests:
            quest_type = quest.get("type", "unknown")
            objectives = self._quest_to_objectives(quest)
            self.plot_engine.add_quest(quest["id"], quest_type, objectives)
        
        # TIER 9: Generate scenes from all events
        scenes = self.scenes.generate_from_events(world_events)
        
        # TIER 9: Update character beliefs from events
        self.characters.update_from_events(world_events)
        
        # TIER 9: Store events in narrative memory
        self.memory.add_events(world_events)
        
        # TIER 9: Check story arcs for completion
        completed_arcs = self.story_arcs.update({"tick": self._tick})
        world_events.extend(completed_arcs)
        
        # TIER 10: Autonomous NPC Agent System
        # NPCs act on their own goals, generating events that enrich the world
        agent_events = self.agents.update(
            characters=self.characters.characters,
            world_state=self._get_world_state_for_agents(),
        )
        world_events.extend(agent_events)
        
        # 4. Convert to narrative events
        if self.director:
            narrative_events = self.director.convert_events(world_events)
        else:
            # Fallback: create minimal narrative events
            narrative_events = [
                NarrativeEvent(
                    id=str(i),
                    type=e.get("type", "unknown"),
                    description=e.get("description", e.get("type", "event")),
                    actors=e.get("actors", []),
                    raw_event=e,
                )
                for i, e in enumerate(world_events)
            ]
        
        # 5. Select important ones
        if self.director:
            focus_events = self.director.select_focus_events(narrative_events)
        else:
            focus_events = narrative_events  # All events if no director
        
        # 6. TIER 5: AI Director shapes events based on tension (event-driven)
        self.ai_director.update(focus_events)
        focus_events = self.ai_director.filter_events(focus_events)
        
        # 7. Update scene
        if self.scene_manager:
            self.scene_manager.update_scene([e.raw_event for e in focus_events])
        
        scene_context = (
            self.scene_manager.get_scene_context()
            if self.scene_manager
            else {}
        )
        
        # 8. Generate narration
        narration = self._generate_narration(focus_events, scene_context)
        
        # 9. TIER 5: Pacing Controller adjusts output length
        narration = self.pacing_controller.adjust(
            narration, self.ai_director.tension
        )
        
        # TIER 9: Render narrative output
        narrative = self.renderer.render(
            scenes=self.scenes.get_active_scenes(),
            memory=self.memory,
            characters=self.characters.characters,
            world_state=self._get_world_state_for_renderer(),
        )
        
        # Build result
        result = {
            "narration": narration,
            "events": focus_events,
            "scene_context": scene_context,
            "raw_events": world_events,
            "scenes": scenes,
            "narrative": narrative,
            "completed_arcs": completed_arcs,
        }
        self._last_result = result
        return result
    
    def step_no_narration(self, player_input: str) -> Dict[str, Any]:
        """Execute game loop step without narrative generation.
        
        Useful for testing or when narration is handled externally.
        
        Args:
            player_input: Raw player input text.
            
        Returns:
            Result dict with events but no narration.
        """
        player_event = self._convert_input(player_input)
        world_events = self._simulate_tick()
        world_events.insert(0, player_event)
        
        if self.director:
            narrative_events = self.director.convert_events(world_events)
            focus_events = self.director.select_focus_events(narrative_events)
        else:
            focus_events = [
                NarrativeEvent(
                    id=str(i),
                    type=e.get("type", "unknown"),
                    description=e.get("description", ""),
                    actors=e.get("actors", []),
                    raw_event=e,
                )
                for i, e in enumerate(world_events)
            ]
        
        if self.scene_manager:
            self.scene_manager.update_scene([e.raw_event for e in focus_events])
        
        return {
            "narration": "",
            "events": focus_events,
            "scene_context": (
                self.scene_manager.get_scene_context()
                if self.scene_manager
                else {}
            ),
            "raw_events": world_events,
        }
        
    def _convert_input(self, text: str) -> Dict[str, Any]:
        """Convert player text input to world event dict.
        
        Args:
            text: Raw player input.
            
        Returns:
            Event dict representing the player action.
        """
        return {
            "type": "player_action",
            "description": text,
            "actors": ["player"],
        }
    
    def _inject_player_event(self, event: Dict[str, Any]) -> None:
        """Inject player event into the world simulation.
        
        Args:
            event: Player event dict to inject.
        """
        if hasattr(self.world, "inject_event"):
            self.world.inject_event(event)
        elif hasattr(self.world, "add_event"):
            self.world.add_event(event)
        # If world has no injection method, the event will still
        # be included in the result for narrative purposes
        
    def _simulate_tick(self) -> List[Dict[str, Any]]:
        """Run the world simulation tick.
        
        Returns:
            List of event dicts from the tick.
        """
        if self.simulate_fn:
            return self.simulate_fn()
        elif self.world and hasattr(self.world, "world_tick"):
            return self.world.world_tick()
        elif self.world and hasattr(self.world, "tick"):
            result = self.world.tick()
            if isinstance(result, list):
                return result
            return result.get("events", []) if isinstance(result, dict) else []
        else:
            return []
    
    def _generate_narration(
        self,
        focus_events: List[NarrativeEvent],
        scene_context: Dict[str, Any],
    ) -> str:
        """Generate narrative text from focus events and scene context.
        
        Args:
            focus_events: Selected narrative events for narration.
            scene_context: Scene context dict from the scene manager.
            
        Returns:
            Generated narrative text, or empty string if no narrator.
        """
        if not focus_events:
            return "Nothing of note happens."
        
        if self.narrator is None:
            return self._template_fallback(focus_events)
        
        # Try to use NarrativeGenerator style (generate method with events+context)
        if hasattr(self.narrator, "generate"):
            try:
                return self.narrator.generate(focus_events, scene_context)
            except TypeError:
                # Might be a different generator interface
                pass
        
        # Try generate_from_dicts for raw events
        if hasattr(self.narrator, "generate_from_dicts"):
            raw_events = [e.raw_event for e in focus_events]
            try:
                return self.narrator.generate_from_dicts(raw_events, scene_context)
            except Exception:
                pass
        
        # Try as a simple callable
        if callable(self.narrator):
            try:
                return self.narrator(focus_events)
            except TypeError:
                pass
        
        return self._template_fallback(focus_events)
    
    @staticmethod
    def _template_fallback(events: List[NarrativeEvent]) -> str:
        """Generate template fallback narrative when narrator is unavailable.
        
        Args:
            events: Narrative events to narrate.
            
        Returns:
            Template narrative text.
        """
        if not events:
            return "Nothing of note happens."
        
        sentences = []
        for event in events:
            sentences.append(event.description)
        
        return " ".join(sentences) if sentences else "Time passes."
    
    def get_last_result(self) -> Dict[str, Any]:
        """Get the result of the last step.
        
        Returns:
            Last step result dict, or empty dict if no step executed.
        """
        return self._last_result
        
    def reset(self) -> None:
        """Reset the player loop state."""
        self._last_result = {}
        self._tick = 0
        if self.scene_manager and hasattr(self.scene_manager, "end_scene"):
            self.scene_manager.end_scene()
        if self.director and hasattr(self.director, "clear_buffer"):
            self.director.clear_buffer()
        
        # TIER 5: Reset new systems
        self.ai_director.reset()
        
        # TIER 6: Reset Narrative Intelligence Systems
        self.plot_engine.reset()
        self.agency.reset()
        
        # TIER 7: Reset Faction Simulation + Reputation Economy
        self.factions.reset()
        self.reputation.reset()
        
        # TIER 8: Reset World Complexity Layer
        self.economy.reset()
        self.politics.reset()
        self.quest_gen.clear_generated()
        
        # TIER 9: Reset Narrative Intelligence Layer
        self.scenes.reset()
        self.characters.reset()
        self.memory.reset()
        self.story_arcs.reset()
        self.renderer.reset()
        
        # TIER 10: Reset Autonomous NPC Agent System
        self.agents.reset()
        
    def _quest_to_objectives(self, quest: Dict[str, Any]) -> List[str]:
        """Convert a quest dict to objectives list for PlotEngine.
        
        Args:
            quest: Quest dict from DynamicQuestGenerator.
            
        Returns:
            List of objective strings.
        """
        quest_type = quest.get("type", "unknown")
        
        if quest_type == "war":
            return [
                f"Assist {quest.get('faction_name', quest.get('faction', 'ally'))} against {quest.get('target_name', quest.get('target', 'enemy'))}",
                "Prepare for battle",
            ]
        elif quest_type == "supply":
            return [
                f"Gather {quest.get('good', 'supplies')} for {quest.get('location', 'the settlement')}",
                "Deliver supplies to the location",
            ]
        elif quest_type == "crisis":
            return [
                f"URGENT: {quest.get('location', 'Location')} is critically low on {quest.get('good', 'supplies')}",
                "Find immediate supply sources",
            ]
        elif quest_type == "trade":
            return [
                f"Transport {quest.get('good', 'goods')} from {quest.get('from', 'source')} to {quest.get('to', 'destination')}",
                "Complete the trade for profit",
            ]
        elif quest_type == "rebellion":
            return [
                f"Investigate leadership change in {quest.get('faction', 'faction')}",
                "Determine your stance on the new leadership",
            ]
        elif quest_type == "diplomacy":
            return [
                f"Facilitate alliance between {quest.get('faction', 'faction')} and {quest.get('target', 'target')}",
                "Negotiate terms",
            ]
        else:
            return ["Investigate the situation"]
        
    def _update_faction_relations(self) -> None:
        """Update faction relations based on player reputation.
        
        High reputation with a faction improves relations with its allies
        and worsens relations with its enemies. Low reputation has the
        opposite effect.
        """
        for faction_id, faction in self.factions.factions.items():
            rep = self.reputation.get(faction_id)
            
            # Reputation affects faction's view of player's allies/enemies
            if rep > 0.5:
                # Player is ally - improve relations with player's allies
                for ally in self.reputation.reputation:
                    if self.reputation.get(ally) > 0.5 and ally != faction_id:
                        faction.adjust_relation(ally, 0.05)
                        
            elif rep < -0.5:
                # Player is enemy - worsen relations
                faction.morale *= 0.98  # Low reputation hurts faction morale
    
    def _get_world_state_for_renderer(self) -> Dict[str, Any]:
        """Get world state summary for the narrative renderer.
        
        Returns:
            Dict with relevant world state data.
        """
        state: Dict[str, Any] = {
            "tick": self._tick,
            "faction_conflicts": 0,
            "shortages": {},
            "economy_state": "stable",
        }
        
        # Count active faction conflicts
        for faction in self.factions.factions.values():
            for relation in faction.relations.values():
                if relation < -0.6:
                    state["faction_conflicts"] += 1
        
        # Get economy state
        if hasattr(self.economy, "get_summary"):
            econ = self.economy.get_summary()
            state["economy_state"] = econ.get("state", "stable")
        
        # Get shortage info from plot engine
        quests = self.plot_engine.quest_manager.get_active_quests()
        for quest in quests:
            if quest.get("type") == "crisis":
                loc = quest.get("objectives", ["unknown"])[0]
                state["shortages"][loc] = {"severity": 0.8}
        
        return state
    
    def _get_world_state_for_agents(self) -> Dict[str, Any]:
        """Get world state summary for the agent system.
        
        Returns:
            Dict with relevant world state data for NPC decision-making.
        """
        return {
            "factions": {
                fid: f.to_dict()
                for fid, f in self.factions.factions.items()
            },
            "economy": self.economy.get_summary() if hasattr(self.economy, "get_summary") else {},
            "tick": self._tick,
        }
