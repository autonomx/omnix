"""Quest Director for the Quest Emergence Engine.

This module provides the QuestDirector class that generates
narrative descriptions for quests based on their current stage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class QuestDirector:
    """Generates narrative descriptions for quests.

    The QuestDirector provides human-readable quest descriptions
    that update based on the current stage, including objectives
    and narrative context.

    Usage:
        director = QuestDirector()
        desc = director.generate_description(quest)
    """

    def generate_description(self, quest: Any) -> str:
        """Generate a narrative description for the quest.

        Creates a formatted description showing the quest title,
        current stage, stage description, and active objectives.

        Args:
            quest: Quest object to describe.

        Returns:
            Formatted quest description string.
        """
        if not quest.stages:
            return f"[{quest.title}] - A quest with no stages"

        stage = quest.stages[quest.current_stage_index] if quest.current_stage_index < len(quest.stages) else quest.stages[-1]

        active_objectives = [o for o in stage.objectives if not o.completed]

        description = f"""[{quest.title} — {stage.name.upper()}]

{stage.description}

Objectives:
- """ + "\n- ".join(o.description for o in active_objectives) if active_objectives else "Objectives:\n- Complete remaining tasks"

        return description

    def generate_summary(self, quest: Any) -> Dict[str, Any]:
        """Generate a structured summary dict for the quest.

        Args:
            quest: Quest object to summarize.

        Returns:
            Dict with quest summary information.
        """
        stage = quest.current_stage

        return {
            "id": quest.id,
            "title": quest.title,
            "type": quest.type,
            "stage": stage.name if stage else "none",
            "arc_progress": quest.arc_progress,
            "status": quest.status,
            "active_objectives": len(quest.active_objectives),
            "total_objectives": sum(len(s.objectives) for s in quest.stages),
            "description": self.generate_description(quest),
        }

    def generate_all_quests_description(
        self,
        active_quests: List[Any],
        completed_quests: Optional[List[Any]] = None,
    ) -> str:
        """Generate descriptions for multiple quests.

        Args:
            active_quests: List of active quest objects.
            completed_quests: Optional list of completed quests.

        Returns:
            Formatted string with all quest descriptions.
        """
        output = "=== ACTIVE QUESTS ===\n\n"

        if not active_quests:
            output += "No active quests.\n"
        else:
            for i, quest in enumerate(active_quests, 1):
                output += f"Quest {i}: {self.generate_description(quest)}\n\n"

        if completed_quests:
            output += "=== COMPLETED QUESTS ===\n\n"
            for quest in completed_quests:
                output += f"✓ {quest.title}\n"

        return output

    def generate_quest_briefing(self, quest: Any) -> str:
        """Generate a detailed quest briefing with full history.

        Args:
            quest: Quest object to brief.

        Returns:
            Detailed quest briefing string.
        """
        briefing = f"=== QUEST BRIEFING: {quest.title.upper()} ===\n\n"
        briefing += f"Type: {quest.type}\n"
        briefing += f"Status: {quest.status}\n"
        briefing += f"Progress: {quest.arc_progress:.0%}\n"
        briefing += f"Current Stage: {quest.arc_stage}\n\n"

        briefing += "--- STAGE PROGRESS ---\n"
        for i, stage in enumerate(quest.stages):
            marker = "✓" if i < quest.current_stage_index else ">" if i == quest.current_stage_index else "o"
            briefing += f"  {marker} {stage.name}: {stage.description}\n"

        if quest.history:
            briefing += "\n--- HISTORY ---\n"
            for entry in quest.history:
                briefing += f"  - {entry.get('stage', 'unknown')}: {'completed' if entry.get('completed') else 'failed'}\n"

        briefing += "\n--- CURRENT OBJECTIVES ---\n"
        for obj in quest.active_objectives:
            progress_bar = "█" * int(obj.progress * 10) + "░" * (10 - int(obj.progress * 10))
            briefing += f"  [{progress_bar}] {obj.description}\n"

        return briefing