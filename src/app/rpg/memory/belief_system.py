"""Belief System - Derived truth layer built from memories.

This module converts raw episodic memories into stable beliefs that
influence GOAP planning, emotional responses, and story direction.

Architecture:
    EVENTS → MEMORIES → BELIEFS → GOAP/EMOTION/STORY

Key Design Principles:
- Incremental updates: beliefs update from individual events, not full rescan
- Temporal decay: beliefs fade over time to allow narrative evolution
- Weighted events: recent and severe events have more impact
- Conflict resolution: contradictory beliefs are resolved deterministically
- Observed vs Experienced: direct harm vs witnessed danger are tracked separately

Example Emergent Behavior:
    Player attacks NPC 3 times
    → event: damage(source=player, target=npc)
    → belief update: _counts["damage_taken"][player] += 1
    → recompute: hostile_targets = ["player"]
    → relationship: anger += weight
    → GOAP: attack_target(player)

    No hardcoding. Fully emergent.
"""

from typing import Any, Dict, List, Optional, Set

# Default decay rate per tick (0.95 = 5% decay per tick)
DEFAULT_DECAY_RATE = 0.95

# Minimum count threshold before belief is formed
MIN_BELIEF_THRESHOLD = 0.5

# Thresholds for belief formation
HOSTILE_THRESHOLD = 1.5
TRUSTED_THRESHOLD = 1.5


class BeliefSystem:
    """Derived belief layer built from memories.

    Converts individual events into stable truths that persist beyond
    individual memory instances.

    Belief Categories:
    - hostile_targets: Entities that have DIRECTLY harmed the NPC
    - trusted_allies: Entities that have DIRECTLY helped the NPC
    - subjugated_targets: Entities the NPC has harmed
    - dangerous_entities: Entities observed being aggressive (not necessarily toward NPC)
    - helpful_entities: Entities observed being helpful (not necessarily toward NPC)
    - world_threat_level: Overall assessment of world danger

    Attributes:
        beliefs: Dict mapping belief keys to belief values
        _counts: Internal counter dicts for incremental updates
            - damage_taken: target_id -> weighted count
            - help_received: target_id -> weighted count
            - damage_dealt: target_id -> weighted count
            - observed_aggression: source_id -> count of witnessed aggression
            - observed_helpfulness: source_id -> count of witnessed helpfulness
        _decay_rate: Per-tick decay multiplier
    """

    def __init__(self, decay_rate: float = DEFAULT_DECAY_RATE):
        """Initialize belief system with empty beliefs.

        Args:
            decay_rate: Per-tick decay multiplier (0.95 = 5% decay per tick)
        """
        self.beliefs: Dict[str, Any] = {}
        self._decay_rate = decay_rate

        # Internal counters for incremental updates
        # Each maps entity_id -> float (weighted count)
        self._counts: Dict[str, Dict[str, float]] = {
            "damage_taken": {},       # Entities that damaged this NPC
            "help_received": {},      # Entities that helped this NPC
            "damage_dealt": {},       # Entities this NPC damaged
            "observed_aggression": {}, # Aggressive entities (observed)
            "observed_helpfulness": {}, # Helpful entities (observed)
        }

    def update_from_event(self, event: Dict[str, Any]):
        """Update beliefs incrementally from a single event.

        This is the PRIMARY entry point for belief updates.
        Called by the event bus when a relevant event occurs.

        Event types handled:
        - "damage": increments damage_taken for target, damage_dealt for source
        - "heal": increments help_received for target
        - "assist": increments help_received for target
        - "attack" (observed): increments observed_aggression for source

        Args:
            event: Event dict with "type", "source", "target", and optionally "amount"
        """
        src = event.get("source") or event.get("actor")
        tgt = event.get("target")
        etype = event.get("type", "")

        if not src:
            return

        # Get weight based on event severity
        weight = event.get("amount", 1.0) * 0.1

        # ---- Direct experience: NPC is the target ----
        if tgt == src:
            # Self-event, skip
            pass
        elif tgt is not None:
            # NPC was directly involved
            if etype == "damage":
                # Source damaged target
                if hasattr(self, '_npc_id') and tgt == self._npc_id:
                    # This NPC was damaged
                    self._increment("damage_taken", src, weight)
                elif hasattr(self, '_npc_id') and src == self._npc_id:
                    # This NPC dealt damage
                    self._increment("damage_dealt", tgt, weight)
                else:
                    # Witnessed damage - record observed aggression
                    self._increment("observed_aggression", src, weight * 0.5)

            elif etype in ("heal", "assist"):
                if hasattr(self, '_npc_id') and tgt == self._npc_id:
                    # This NPC received help
                    self._increment("help_received", src, weight)
                else:
                    # Witnessed helpfulness
                    self._increment("observed_helpfulness", src, weight * 0.5)

        # ---- For direct victims only: full weight ----
        # Also handle observed aggression when NPC witnesses violence
        if etype == "damage" and src != src:
            pass  # Already handled above

        # Recompute beliefs from updated counters
        self._recompute_fast()

    def _increment(self, counter_name: str, entity_id: str, weight: float):
        """Increment a counter for an entity.

        Args:
            counter_name: Which counter to increment
            entity_id: Entity identifier
            weight: Amount to add
        """
        if entity_id not in self._counts[counter_name]:
            self._counts[counter_name][entity_id] = 0.0
        self._counts[counter_name][entity_id] += weight

    def _recompute_fast(self):
        """Recompute all beliefs from current counters.

        This is O(c) where c = number of unique entities in counters.
        Much faster than O(n) full memory scan.

        Conflict resolution:
        - If hostility > trust for an entity → hostile
        - Otherwise → trusted or neutral
        """
        beliefs = {}

        damage_taken = self._counts["damage_taken"]
        help_received = self._counts["help_received"]
        damage_dealt = self._counts["damage_dealt"]
        observed_aggression = self._counts["observed_aggression"]
        observed_helpfulness = self._counts["observed_helpfulness"]

        # --- Resolve conflicts: hostility vs trust ---
        hostile_targets = []
        trusted_allies = []
        all_entities = set()
        all_entities.update(damage_taken.keys())
        all_entities.update(help_received.keys())

        for entity in all_entities:
            hostility = damage_taken.get(entity, 0.0)
            trust = help_received.get(entity, 0.0)

            if hostility > trust and hostility >= HOSTILE_THRESHOLD:
                hostile_targets.append(entity)
            elif trust > hostility and trust >= TRUSTED_THRESHOLD:
                trusted_allies.append(entity)
            # If equal or below threshold → neutral (no belief)

        beliefs["hostile_targets"] = hostile_targets
        beliefs["trusted_allies"] = trusted_allies

        # --- Direct damage targets ---
        beliefs["subjugated_targets"] = [
            k for k, v in damage_dealt.items() if v >= HOSTILE_THRESHOLD
        ]

        # --- Observed entities (separate from direct experience) ---
        beliefs["dangerous_entities"] = [
            k for k, v in observed_aggression.items()
            if v >= HOSTILE_THRESHOLD * 0.5  # Lower threshold for observed
        ]

        beliefs["helpful_entities"] = [
            k for k, v in observed_helpfulness.items()
            if v >= TRUSTED_THRESHOLD * 0.5
        ]

        # --- World threat level ---
        total_hostility = sum(damage_taken.values())
        if total_hostility >= 5.0:
            beliefs["world_threat_level"] = "very_high"
        elif total_hostility >= 3.0:
            beliefs["world_threat_level"] = "high"
        elif total_hostility >= 1.0:
            beliefs["world_threat_level"] = "moderate"
        else:
            beliefs["world_threat_level"] = "low"

        # --- Intensity maps (used for target scoring) ---
        beliefs["hostility_intensity"] = dict(damage_taken)
        beliefs["trust_intensity"] = dict(help_received)
        beliefs["aggression_intensity"] = dict(observed_aggression)

        self.beliefs = beliefs

    def decay(self, dt: float = 1.0):
        """Apply temporal decay to all belief counters.

        Counters below MIN_BELIEF_THRESHOLD are removed.
        This allows beliefs to fade and narratives to evolve.

        Should be called periodically (e.g., every 5-10 ticks).

        Args:
            dt: Time delta (number of ticks since last decay)
        """
        decay_factor = self._decay_rate ** dt

        for counter_name in self._counts:
            for key in list(self._counts[counter_name].keys()):
                self._counts[counter_name][key] *= decay_factor

                if self._counts[counter_name][key] < MIN_BELIEF_THRESHOLD:
                    del self._counts[counter_name][key]

        # Recompute beliefs after decay
        self._recompute_fast()

    def update_from_memories(self, npc):
        """Batch update beliefs from NPC's existing memories.

        BACKWARD COMPATIBILITY: This is used to bootstrap beliefs
        from existing memories when the NPC first loads.

        For ongoing updates, use update_from_event() instead.

        Args:
            npc: The NPC whose beliefs should be updated
        """
        # Store NPC ID for event routing
        self._npc_id = npc.id

        hostile_targets = []
        trusted_allies = []
        subjugated_targets = []
        aggressive_targets: Set[str] = set()
        helpful_targets: Set[str] = set()

        hostility: Dict[str, float] = {}
        trust: Dict[str, float] = {}
        subjugation: Dict[str, float] = {}

        memories = npc.memory.get("events", []) if isinstance(npc.memory, dict) else npc.memory

        for mem in memories:
            event = mem.get("event", mem) if isinstance(mem, dict) else {}
            src = event.get("source") or event.get("actor")
            tgt = event.get("target")
            mem_type = event.get("type", mem.get("type", ""))
            amount = event.get("amount", mem.get("amount", 1.0))

            if not src:
                continue

            weight = amount * 0.1

            # Track damage patterns
            if mem_type == "damage":
                if tgt == npc.id:
                    hostility[src] = hostility.get(src, 0) + weight
                    aggressive_targets.add(src)
                elif src == npc.id:
                    subjugation[tgt] = subjugation.get(tgt, 0) + weight
                else:
                    # Witnessed damage
                    aggressive_targets.add(src)

            # Track healing/assist patterns
            if mem_type in ("heal", "assist"):
                if tgt == npc.id:
                    trust[src] = trust.get(src, 0) + weight
                    helpful_targets.add(src)

            # Handle consolidated memories
            if mem.get("memory_type") == "episodic_consolidated":
                count = mem.get("count", 1)
                if "damage" in mem_type:
                    if tgt == npc.id:
                        hostility[src] = hostility.get(src, 0) + weight * count
                    elif src == npc.id:
                        subjugation[tgt] = subjugation.get(tgt, 0) + weight * count

        # Update internal counters
        self._counts["damage_taken"] = hostility
        self._counts["help_received"] = trust
        self._counts["damage_dealt"] = subjugation

        # Recompute beliefs
        self._recompute_fast()

        # Store legacy belief format for compatibility
        self.beliefs["hostile_targets"] = hostile_targets
        self.beliefs["trusted_allies"] = trusted_allies
        self.beliefs["subjugated_targets"] = subjugated_targets
        self.beliefs["aggressive_entities"] = list(aggressive_targets)
        self.beliefs["helpful_entities"] = list(helpful_targets)

        # Intensity maps
        self.beliefs["hostility_intensity"] = hostility
        self.beliefs["trust_intensity"] = trust

    def get(self, key: str, default: Any = None) -> Any:
        """Get a belief value by key.

        Args:
            key: The belief key to retrieve
            default: Default value if belief doesn't exist

        Returns:
            The belief value or default
        """
        return self.beliefs.get(key, default)

    def has_belief(self, key: str) -> bool:
        """Check if a belief exists and is non-empty.

        Args:
            key: The belief key to check

        Returns:
            True if belief exists and is non-empty
        """
        value = self.beliefs.get(key)
        if value is None:
            return False
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)

    def get_hostile_targets(self) -> List[str]:
        """Get list of entities the NPC considers hostile.

        Returns:
            List of entity IDs considered hostile
        """
        return self.beliefs.get("hostile_targets", [])

    def get_trusted_allies(self) -> List[str]:
        """Get list of entities the NPC trusts.

        Returns:
            List of entity IDs considered allies
        """
        return self.beliefs.get("trusted_allies", [])

    def get_dangerous_entities(self) -> List[str]:
        """Get entities observed being dangerous (not necessarily hostile to NPC).

        Returns:
            List of entity IDs observed as dangerous
        """
        return self.beliefs.get("dangerous_entities", [])

    def is_hostile_toward(self, target_id: str) -> bool:
        """Check if the NPC is hostile toward a specific entity.

        Args:
            target_id: The entity to check hostility against

        Returns:
            True if the NPC considers this entity hostile
        """
        return target_id in self.get_hostile_targets()

    def is_ally(self, target_id: str) -> bool:
        """Check if the NPC considers a specific entity an ally.

        Args:
            target_id: The entity to check alliance with

        Returns:
            True if the NPC considers this entity an ally
        """
        return target_id in self.get_trusted_allies()

    def get_summary(self) -> str:
        """Get human-readable summary of current beliefs.

        Returns:
            String summarizing the NPC's beliefs for LLM injection
        """
        parts = []

        hostile = self.get_hostile_targets()
        if hostile:
            parts.append(f"Hostile: {', '.join(hostile)}")

        allies = self.get_trusted_allies()
        if allies:
            parts.append(f"Allies: {', '.join(allies)}")

        dangerous = self.get_dangerous_entities()
        if dangerous:
            parts.append(f"Dangerous (observed): {', '.join(dangerous)}")

        threat = self.get("world_threat_level", "unknown")
        parts.append(f"World threat: {threat}")

        return "; ".join(parts) if parts else "No strong beliefs formed yet"

    def get_belief_weights(self, target_id: str) -> Dict[str, float]:
        """Get weighted scores for how beliefs should influence behavior toward target.

        Used for target scoring in GOAP and decision making.

        Args:
            target_id: The target to compute weights for

        Returns:
            Dict with attack, flee, assist, avoid weights
        """
        weights = {
            "attack": 0.0,
            "flee": 0.0,
            "assist": 0.0,
            "avoid": 0.0,
        }

        # Hostile target → attack urge
        if self.is_hostile_toward(target_id):
            intensity = self.beliefs.get("hostility_intensity", {}).get(target_id, 0)
            weights["attack"] = min(1.0, intensity * 0.3)

        # Trusted ally → assist urge
        if self.is_ally(target_id):
            intensity = self.beliefs.get("trust_intensity", {}).get(target_id, 0)
            weights["assist"] = min(1.0, intensity * 0.25)

        # Dangerous but not hostile → avoid
        if target_id in self.get_dangerous_entities():
            if not self.is_hostile_toward(target_id):
                weights["avoid"] = 0.3

        # World threat influences flee tendency
        threat_level = self.get("world_threat_level", "low")
        if threat_level == "high":
            weights["flee"] = 0.3
        elif threat_level == "very_high":
            weights["flee"] = 0.5

        return weights


def compute_belief_influence(belief_system: BeliefSystem, target_id: str) -> Dict[str, float]:
    """Compute how beliefs influence behavior toward a target.

    Returns influence scores for different behavioral dimensions.

    Args:
        belief_system: The NPC's belief system
        target_id: The target entity to compute influence for

    Returns:
        Dict with influence scores for attack, flee, assist, avoid
    """
    weights = belief_system.get_belief_weights(target_id)

    # Legacy format for backward compatibility
    influence = {
        "attack": weights["attack"],
        "flee": weights["flee"],
        "assist": weights["assist"],
        "avoid": weights["avoid"],
    }

    # High overall threat increases flee tendency (legacy)
    threat_level = belief_system.get("world_threat_level", "low")
    if threat_level in ("high", "very_high"):
        influence["flee"] = max(influence["flee"], 0.3 if threat_level == "high" else 0.5)

    return influence


def pick_best_target(npc, candidates: List[str]) -> Optional[str]:
    """Pick the best attack target using belief-weighted scoring.

    Replaces simplistic hostile[0] selection with multi-factor scoring:
    - Anger/relationship score
    - Belief hostility intensity
    - Distance (closer targets preferred)
    - Recency (recent aggression weighted higher)

    Args:
        npc: The NPC selecting a target
        candidates: List of candidate target IDs

    Returns:
        Best target ID, or None if no candidates
    """
    if not candidates:
        return None

    # Fall back to first candidate if no belief system
    if not hasattr(npc, 'belief_system'):
        return candidates[0]

    best_target = None
    best_score = -999

    for target_id in candidates:
        # Belief-based hostility
        hostility = npc.belief_system.beliefs.get("hostility_intensity", {}).get(target_id, 0)

        # Relationship-based anger
        if hasattr(npc, 'relationships') and target_id in npc.relationships:
            anger = npc.relationships[target_id].get("anger", 0)
        elif hasattr(npc, 'emotional_state'):
            anger_map = npc.emotional_state.get("anger_map", {})
            anger = anger_map.get(target_id, 0)
        else:
            anger = 0

        # Distance (closer = higher score)
        if hasattr(npc, 'position') and hasattr(npc, '_get_pos'):
            try:
                from rpg.spatial import distance
                target_npc = None
                if hasattr(npc, '_session'):
                    from rpg.simulation import find_npc
                    target_npc = find_npc(npc._session, target_id)
                if target_npc and hasattr(target_npc, 'position'):
                    dist = distance(npc.position, target_npc.position)
                else:
                    dist = 5.0  # default distance
            except (ImportError, AttributeError):
                dist = 5.0
        else:
            dist = 5.0  # default

        # Combined score
        score = hostility * 2 + anger * 1.5 - dist * 0.1

        if score > best_score:
            best_score = score
            best_target = target_id

    return best_target or (candidates[0] if candidates else None)