"""Dynamic Quest Generation System - TIER 8: World Complexity Layer.

This module implements PART 2 of Tier 8 from the RPG design specification:
the Dynamic Quest Generator.

Purpose:
    Generate quests from world pressure rather than static pre-authored
    content. Economic shortages, faction conflicts, and political
    instability all create quest opportunities that feel organic and
    responsive to the evolving world state.

The Problem:
    - Current quests are static / pre-authored
    - No connection between world events and quest availability
    - Player actions don't create new quest lines
    - World feels scripted instead of alive

The Solution:
    DynamicQuestGenerator observes faction relations, economic conditions,
    and political events to generate quests automatically. Faction
    conflicts become war quests, economic shortages become supply quests,
    and political instability becomes rebellion quests.

Architecture:
    DynamicQuestGenerator:
        - Observes FactionSystem for conflicts (relations < -0.7)
        - Observes EconomySystem for shortages (supply < 0.2)
        - Generates quest dicts with id, type, and context
        
    Generated Quest Types:
        - "war": Faction conflict quests
        - "supply": Economic shortage quests
        - "rebellion": Political instability quests
        - "trade": Economic opportunity quests

Key Features:
    - Faction conflict detection → war quests
    - Economic shortage detection → supply quests
    - Quest deduplication (tracks generated IDs)
    - Quest type classification
    - Integration with PlotEngine
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


class DynamicQuestGenerator:
    """Generates quests dynamically from world state.
    
    The DynamicQuestGenerator observes economy and faction systems to
    create quests that feel organic and responsive. Unlike static quest
    lists, these quests emerge from the simulation itself - a food
    shortage creates a supply quest, faction hostilities create conflict
    quests, etc.
    
    Quest Types Generated:
        - "war": Faction A is at war with Faction B
        - "supply": Location X needs more of good Y
        - "trade": Trade opportunity between locations
        - "crisis": Severe shortage requiring urgent action
    
    Integration Points:
        - FactionSystem: Conflict detection (relations < -0.7)
        - EconomySystem: Shortage detection (supply < 0.2)
        - PlotEngine: Quests injected as story arcs
        - PlayerLoop: Generator called each tick to discover new quests
    
    Usage:
        generator = DynamicQuestGenerator()
        
        # Setup factions with hostile relations
        faction_a.relations["faction_b"] = -0.8
        
        # Setup market with shortage
        market.goods["food"]["supply"] = 0.1
        
        # Generate quests from world state
        quests = generator.generate(faction_system, economy_system)
        for quest in quests:
            plot_engine.add_quest(quest["id"], quest["type"], quest.get("objectives", []))
    """
    
    # Threshold for faction conflict quests
    CONFLICT_THRESHOLD = -0.7
    
    # Threshold for supply shortage quests
    SUPPLY_THRESHOLD = 0.2
    
    # Threshold for crisis-level shortage
    CRISIS_THRESHOLD = 0.1
    
    def __init__(self):
        """Initialize the DynamicQuestGenerator."""
        self.generated_ids: Set[str] = set()
        
    def generate(
        self,
        faction_system: Any = None,
        economy_system: Any = None,
        political_events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate quests from current world state.
        
        Examines faction relations and economic conditions to create
        appropriate quests for the player.
        
        Args:
            faction_system: FactionSystem to check for conflicts.
            economy_system: EconomySystem to check for shortages.
            political_events: List of political events (e.g., coups)
                             that might generate quests.
            
        Returns:
            List of quest dicts ready for PlotEngine integration.
            Each quest dict contains:
            - "id": Unique quest identifier
            - "type": Quest type ("war", "supply", "trade", "crisis", "rebellion")
            - Additional context fields based on type
        """
        quests: List[Dict[str, Any]] = []
        
        # Generate faction conflict quests
        if faction_system is not None:
            quests.extend(self._generate_conflict_quests(faction_system))
            quests.extend(self._generate_alliance_quests(faction_system))
        
        # Generate economic quests
        if economy_system is not None:
            quests.extend(self._generate_supply_quests(economy_system))
            quests.extend(self._generate_trade_quests(economy_system))
        
        # Generate political quests
        if political_events:
            quests.extend(self._generate_political_quests(political_events))
        
        return quests
    
    def _generate_conflict_quests(self, faction_system: Any) -> List[Dict[str, Any]]:
        """Generate war quests from hostile faction relations.
        
        When two factions have relations below CONFLICT_THRESHOLD,
        a war quest is generated.
        
        Args:
            faction_system: FactionSystem to examine.
            
        Returns:
            List of war quest dicts.
        """
        quests: List[Dict[str, Any]] = []
        processed_pairs: Set[tuple] = set()
        
        for faction in faction_system.factions.values():
            for target_id, relation in faction.relations.items():
                if relation < self.CONFLICT_THRESHOLD:
                    # Avoid duplicate pairs (A,B) and (B,A)
                    pair_key = tuple(sorted([faction.id, target_id]))
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)
                    
                    quest_id = f"conflict_{faction.id}_{target_id}"
                    if quest_id not in self.generated_ids:
                        hostility = abs(relation)
                        urgency = hostility  # More hostile = more urgent
                        
                        quests.append({
                            "id": quest_id,
                            "type": "war",
                            "faction": faction.id,
                            "faction_name": faction.name,
                            "target": target_id,
                            "target_name": faction_system.factions.get(target_id, type("F", (), {"name": target_id})()).name if hasattr(faction_system.factions.get(target_id), 'name') else target_id,
                            "urgency": urgency,
                            "description": f"{faction.name} and {faction_system.factions.get(target_id, type('F', (), {'name': target_id})()).name} are on the verge of war",
                        })
                        self.generated_ids.add(quest_id)
        
        return quests
    
    def _generate_alliance_quests(self, faction_system: Any) -> List[Dict[str, Any]]:
        """Generate diplomacy quests from positive faction relations.
        
        When two factions have relations above 0.6, they may request
        diplomatic support.
        
        Args:
            faction_system: FactionSystem to examine.
            
        Returns:
            List of alliance quest dicts.
        """
        quests: List[Dict[str, Any]] = []
        processed_pairs: Set[tuple] = set()
        ALLIANCE_THRESHOLD = 0.6
        
        for faction in faction_system.factions.values():
            for target_id, relation in faction.relations.items():
                if relation > ALLIANCE_THRESHOLD:
                    pair_key = tuple(sorted([faction.id, target_id]))
                    if pair_key in processed_pairs:
                        continue
                    processed_pairs.add(pair_key)
                    
                    quest_id = f"alliance_{faction.id}_{target_id}"
                    if quest_id not in self.generated_ids:
                        quests.append({
                            "id": quest_id,
                            "type": "diplomacy",
                            "faction": faction.id,
                            "target": target_id,
                            "strength": relation,
                            "description": f"{faction.name} and {faction_system.factions.get(target_id, type('F', (), {'name': target_id})()).name} seek closer alliance",
                        })
                        self.generated_ids.add(quest_id)
        
        return quests
    
    def _generate_supply_quests(self, economy_system: Any) -> List[Dict[str, Any]]:
        """Generate supply quests from economic shortages.
        
        When a market good has supply below SUPPLY_THRESHOLD,
        a supply quest is generated.
        
        Args:
            economy_system: EconomySystem to examine.
            
        Returns:
            List of supply quest dicts.
        """
        quests: List[Dict[str, Any]] = []
        
        for market in economy_system.markets.values():
            for good, data in market.goods.items():
                supply = data["supply"]
                
                if supply < self.SUPPLY_THRESHOLD:
                    # Determine urgency based on severity
                    if supply < self.CRISIS_THRESHOLD:
                        quest_type = "crisis"
                        urgency = 0.9
                    else:
                        quest_type = "supply"
                        urgency = 0.5 + (self.SUPPLY_THRESHOLD - supply) * 2.0
                    
                    quest_id = f"supply_{market.location_id}_{good}"
                    if quest_id not in self.generated_ids:
                        quests.append({
                            "id": quest_id,
                            "type": quest_type,
                            "location": market.location_id,
                            "good": good,
                            "supply": supply,
                            "price": data["price"],
                            "urgency": urgency,
                            "description": f"{market.location_id} needs {good} (supply: {supply:.2f})",
                        })
                        self.generated_ids.add(quest_id)
        
        return quests
    
    def _generate_trade_quests(self, economy_system: Any) -> List[Dict[str, Any]]:
        """Generate trade quests from profitable trade opportunities.
        
        When there's a significant price difference between markets,
        a trade quest is generated.
        
        Args:
            economy_system: EconomySystem to examine.
            
        Returns:
            List of trade quest dicts.
        """
        quests: List[Dict[str, Any]] = []
        trade_routes = getattr(economy_system, 'trade_routes', [])
        
        for src_id, dst_id, good in trade_routes:
            src_market = economy_system.markets.get(src_id)
            dst_market = economy_system.markets.get(dst_id)
            
            if not src_market or not dst_market:
                continue
            
            src_good = src_market.goods.get(good)
            dst_good = dst_market.goods.get(good)
            
            if not src_good or not dst_good:
                continue
            
            # Price difference creates trade opportunity
            price_diff = dst_good["price"] - src_good["price"]
            
            if price_diff > 0.3:  # Significant profit opportunity
                quest_id = f"trade_{src_id}_{dst_id}_{good}"
                if quest_id not in self.generated_ids:
                    quests.append({
                        "id": quest_id,
                        "type": "trade",
                        "from": src_id,
                        "to": dst_id,
                        "good": good,
                        "profit_margin": price_diff,
                        "description": f"Trade {good} from {src_id} to {dst_id} for profit",
                    })
                    self.generated_ids.add(quest_id)
        
        return quests
    
    def _generate_political_quests(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate quests from political events like coups.
        
        Args:
            events: List of political events from PoliticalSystem.
            
        Returns:
            List of political quest dicts.
        """
        quests: List[Dict[str, Any]] = []
        
        for event in events:
            event_type = event.get("type", "")
            
            if event_type == "coup":
                faction_id = event.get("faction", "unknown")
                quest_id = f"rebellion_{faction_id}"
                
                if quest_id not in self.generated_ids:
                    quests.append({
                        "id": quest_id,
                        "type": "rebellion",
                        "faction": faction_id,
                        "old_leader": event.get("old_leader"),
                        "new_leader": event.get("new_leader"),
                        "urgency": 0.8,
                        "description": f"Power struggle in {faction_id} - new leader has taken control",
                    })
                    self.generated_ids.add(quest_id)
        
        return quests
    
    def clear_generated(self) -> None:
        """Clear all generated quest IDs, allowing regeneration."""
        self.generated_ids.clear()
    
    def clear_by_type(self, quest_type: str) -> None:
        """Clear generated quests of a specific type.
        
        Args:
            quest_type: Quest type prefix to clear (e.g., "conflict", "supply").
        """
        to_remove = {qid for qid in self.generated_ids if qid.startswith(quest_type)}
        self.generated_ids -= to_remove