"""
AI Role-Playing System — Multi-Agent RPG Engine

A persistent, multi-agent AI role-playing system that generates unique worlds,
maintains long-term memory and consistency, enforces rules and lore, prevents
exploitation, and supports dynamic storytelling with structured output.

Pipeline architecture:
  Input → Risk Score → Rules → Dice (seeded) → Event → Canon Guard →
  Diff Apply → NPC Simulation → Memory → Compression → Narrative → Narrate

Features:
- World Time system with hour/day/season tracking and time-aware rules
- NPC Autonomy with schedules, goals, background simulation, and economy shifts
- Dice/Probability system with soft failure (5-tier outcomes)
- Narrative Director agent for story pacing and 3-act structure
- Economy system with item catalog, pricing modifiers, and shop hours
- Agent Identity profiles for consistent narrative tone
- Memory importance scoring with structured tagging (npc:/location:/quest:)
- Memory compression agent for long-session scalability
- Canon Consistency Guard to prevent lore/personality drift
- WorldStateDiff for safe, auditable state mutations
- Player Intent Risk Scoring for difficulty-aware gameplay
- Per-faction reputation system with pricing/hostility effects
- Anti-prompt-injection firewall with expanded pattern detection
- Session seed-based deterministic randomness for replayability
- Enhanced anti-exploitation: trust gating, meta-gaming prevention, fail states
- Quest stages with branching paths and failure conditions
"""
