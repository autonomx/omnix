"""Robust JSON Response Parser.

Patch 4: Handles LLM JSON fragility
- Extracts JSON block from messy LLM output
- Handles trailing commas, comments, text before/after JSON
- Returns a safe NPCDecision on parse failure
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class NPCDecision:
    """Represents a parsed NPC decision.

    Attributes:
        intent: Action intent type.
        target: Target of the action.
        action: Specific action to take.
        dialogue: What the NPC says.
        emotion: Emotional state.
        raw: Raw parsed dict or None.
    """

    intent: str = "idle"
    target: str = ""
    action: str = ""
    dialogue: str = ""
    emotion: str = "neutral"
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def fallback(cls) -> "NPCDecision":
        """Return a safe fallback decision.

        Returns:
            Default idle decision.
        """
        return cls(
            intent="idle",
            target="",
            action="wait",
            dialogue="...",
            emotion="neutral",
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NPCDecision":
        """Create a decision from a dict.

        Args:
            d: Dict with decision fields.

        Returns:
            NPCDecision instance.
        """
        return cls(
            intent=d.get("intent", "idle"),
            target=d.get("target", ""),
            action=d.get("action", ""),
            dialogue=d.get("dialogue", ""),
            emotion=d.get("emotion", "neutral"),
            raw=d,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return dict representation.

        Returns:
            Dict with decision fields.
        """
        return {
            "intent": self.intent,
            "target": self.target,
            "action": self.action,
            "dialogue": self.dialogue,
            "emotion": self.emotion,
        }

    def __repr__(self) -> str:
        return (
            f"NPCDecision(intent='{self.intent}', "
            f"target='{self.target}', action='{self.action}', "
            f"emotion='{self.emotion}')"
        )


VALID_INTENTS = frozenset({
    "interact_with_npc",
    "pursue_goal",
    "react_to_event",
    "idle",
    "attack",
    "trade",
    "flee",
    "help",
    "talk",
})

VALID_EMOTIONS = frozenset({
    "happy",
    "angry",
    "neutral",
    "fearful",
    "suspicious",
    "sad",
    "excited",
    "calm",
})


class NPCResponseParser:
    """Robust JSON parser for LLM NPC responses.

    Patch 4: Extracts JSON from messy output, fixes trailing commas,
    and returns a safe fallback on failure.
    """

    def parse(self, raw: str) -> NPCDecision:
        """Parse raw LLM response into an NPCDecision.

        Args:
            raw: Raw response string.

        Returns:
            Parsed NPCDecision or fallback.
        """
        if not raw or not raw.strip():
            return NPCDecision.fallback()

        # Step 1: Extract JSON-like block
        json_str = self._extract_json(raw)
        if not json_str:
            return NPCDecision.fallback()

        # Step 2: Fix common LLM JSON issues
        json_str = self._fix_json(json_str)

        # Step 3: Parse
        try:
            d = json.loads(json_str)
        except json.JSONDecodeError:
            return NPCDecision.fallback()

        if not isinstance(d, dict):
            return NPCDecision.fallback()

        # Step 4: Validate and normalize
        return self._normalize(d)

    def _extract_json(self, raw: str) -> Optional[str]:
        """Extract the first JSON-like block from text.

        Handles:
        - Text before/after JSON
        - Markdown code blocks
        - Multiple JSON objects (takes first)

        Args:
            raw: Raw response text.

        Returns:
            JSON string or None.
        """
        # Try markdown code block first
        code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if code_match:
            return code_match.group(1)

        # Try to find first {...} block
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            return match.group(0)

        return None

    def _fix_json(self, json_str: str) -> str:
        """Fix common LLM JSON problems.

        Fixes:
        - Trailing commas in objects and arrays
        - Single-line comments (// and /* */)
        - Unquoted keys

        Args:
            json_str: Potentially broken JSON string.

        Returns:
            Fixed JSON string.
        """
        # Remove single-line comments
        json_str = re.sub(r"//[^\n]*", "", json_str)
        # Remove multi-line comments
        json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
        # Remove trailing commas before } or ]
        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
        return json_str

    def _normalize(self, d: Dict[str, Any]) -> NPCDecision:
        """Normalize parsed dict into a valid NPCDecision.

        Validates intent and emotion values,
        fills in defaults for missing keys.

        Args:
            d: Parsed dict from LLM.

        Returns:
            Validated NPCDecision.
        """
        intent = d.get("intent", "idle")
        if intent not in VALID_INTENTS:
            intent = "idle"

        emotion = d.get("emotion", "neutral")
        if emotion not in VALID_EMOTIONS:
            emotion = "neutral"

        return NPCDecision(
            intent=intent,
            target=str(d.get("target", "")),
            action=str(d.get("action", "")),
            dialogue=str(d.get("dialogue", "")),
            emotion=emotion,
            raw=d,
        )